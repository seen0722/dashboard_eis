# EIS MCP Server — 設計文件

日期：2026-09-18
狀態：已與需求方逐段確認，待寫實作計畫
相依：`docs/superpowers/specs/2026-09-12-bu10-portfolio-dashboard-design.md`（portfolio 管線與快照格式以該文件與 `AGENTS.md` 為準，本文件不重複）

## 1. 目標與受眾

- **目的**：讓公司內部同仁透過 MCP client（Claude Desktop、Claude Code 等）把每月 EIS Excel 包送進來，並用自然語言查詢專案 EIS 狀態。
- **受眾**：uploader（PM 或 SW PM，負責每月送資料）與 viewer（主管、工程師，只查詢）。
- **真相來源**：EIS 匯出的 Excel 包。server 不接受任何人工填寫的狀態，所有回傳欄位都指回快照 `portfolio.json` 的某一格（AGENTS.md 第一守則）。
- **部署**：內網一台主機、一支 Python 服務、一個 port；Streamable HTTP MCP。第一版走 HTTP，TLS 若需要由前置 nginx 處理，不在範圍內。

### 明確不做

- 人工輸入專案狀態（stage、日期、風險文字）。
- SSO / OAuth；第一版用靜態 token。
- 把快照攤平成 SQL 表；快照 1.7 MB，直接載入記憶體查詢即可。
- 回傳原檔內容；只回快照，`input/` 原檔僅供重跑。

## 2. 架構

一支 Starlette app，兩個路徑：

| 路徑 | 用途 | 認證 |
|---|---|---|
| `/mcp` | Streamable HTTP MCP endpoint（官方 `mcp` SDK 2.x 的 `mcp.server.mcpserver.MCPServer`；1.x 的 `FastMCP` 已更名） | Bearer token，任一角色 |
| `POST /upload/{YYYYMM}` | multipart 收檔，落地到 `input/{YYYYMM}/` | Bearer token，僅 uploader |

Excel 包不走 MCP tool 參數：Control List 一份數 MB，base64 進 tool call 會撐爆 client context，且 Claude Desktop 無法讀本機檔。上傳走標準 HTTP，ingest 走 MCP，讓 Claude 能直接讀回健康度並解釋。

### 2.1 目錄

```
src/eis_mcp/
├── __init__.py
├── __main__.py     # python -m src.eis_mcp --data server_data --host 0.0.0.0 --port 8765
├── app.py          # Starlette 組裝：auth middleware + /upload + /mcp
├── auth.py         # tokens.yaml 載入、角色判定、audit 寫入
├── store.py        # 目錄佈局、上傳登錄、快照讀取（含記憶體快取）
├── ingest.py       # 檔案齊全檢查、process lock、呼叫 build_month()、寫結果
└── tools/
    ├── __init__.py # 註冊所有 tool 與 resource 到 MCPServer
    ├── project.py  # get_project、search_projects
    ├── overview.py # get_exceptions、get_health、get_upcoming_milestones
    ├── load.py     # get_dept_loads、get_capacity
    ├── diff.py     # diff_project、get_corrections
    └── admin.py    # ingest_month、list_months
src/portfolio/pipeline.py   # 新增：從 cli.main() 抽出的 build_month()
scripts/eis-upload.sh       # curl 包裝：eis-upload.sh <YYYYMM> <dir>
```

### 2.2 server 資料根目錄（`--data`，預設 `server_data/`，加進 `.gitignore`）

```
server_data/
├── tokens.yaml              # 手動維護，0600
├── audit.sqlite             # 稽核紀錄
├── input/{YYYYMM}/          # 原檔落地，0700
│   ├── Project List-YYYYMM.xlsx
│   ├── BU10_Project_Briefing_YYYYMMDD.xlsx
│   ├── 2026 EIS Resource Summary.xlsx
│   ├── 2026  EIS Resource Control List-*.xlsx|.xlsb
│   └── _upload.json         # [{name, size, sha256, uploaded_by, uploaded_at}]，同名覆蓋時追加一筆
└── snapshots/{YYYYMM}/
    ├── portfolio.json       # 與 CLI 產出格式相同（snapshot.VERSION）
    ├── report_en.html
    └── ingest.json          # 歷次 ingest：[{at, by, status, summary, issues_count, pii_hits}]
```

`snapshots/` 沿用 `model/snapshot.py` 的 `write_snapshot` / `read_previous`，跨月比較邏輯不變。

## 3. 對既有程式的唯一改動：抽出 `build_month()`

`src/portfolio/cli.py:main()` 目前把讀檔、正規化、規則、快照、render、PII 檢查全部串在函式內，server 無法重用。新增 `src/portfolio/pipeline.py`：

```python
@dataclass
class BuildResult:
    snap: dict            # build_snapshot() 的輸出，已含 meta.snap_rev
    html: str             # render_page() 的輸出
    issues: list[Issue]
    pii_hits: list[str]   # find_pii(html) + find_pii(json.dumps(snap))
    summary: dict         # {projects, control_lists, latest_month, snap_date}

class MissingInput(Exception):   # 帶 missing: list[str]，指出缺哪一類檔
class InputUnreadable(Exception) # 包裝 read_project_list / read_briefing 的 ValueError
class NoManpowerMonth(Exception) # Resource Summary 無任何非零月份

def build_month(input_dir: Path, report_month: str, today: str, snapshots_dir: Path,
                cfg: Config, lang: str = "en") -> BuildResult
```

- `build_month()` **不寫任何檔案**，只算。寫檔與結束碼由呼叫端決定。
- `cli.main()` 改為：呼叫 `build_month()` → 三種例外分別對應原本的 `return 1` 訊息 → `pii_hits` 非空 `return 2` → 否則寫快照與 HTML `return 0`。stdout / stderr 文字與現行完全相同，`tests/portfolio/test_cli.py` 不改即需通過。
- `_find_one()` 移到 `pipeline.py`，CLI 與 server 共用。

## 4. 認證、授權與稽核

### 4.1 token

`tokens.yaml`：

```yaml
tokens:
  - token: "<secrets.token_urlsafe(32)>"
    name: "Alice"
    role: uploader          # uploader | viewer
  - token: "..."
    name: "Bob"
    role: viewer
```

- 請求帶 `Authorization: Bearer <token>`；middleware 查表後把 `{name, role}` 放進 request state。
- 無 token 或不在表內：HTTP 401（upload 與 `/mcp` 皆同；MCP client 在建立連線時就會失敗，錯誤清楚）。
- 檔案啟動時載入；修改後重啟服務生效。第一版不做熱載。

### 4.2 授權

| 動作 | uploader | viewer |
|---|---|---|
| `POST /upload/{month}` | ✓ | HTTP 403 |
| `ingest_month` | ✓ | MCP error `forbidden` |
| 其他 tool 與 resource | ✓ | ✓ |

MCP 層授權在 tool 內判斷（`requires_role("uploader")` 輔助函式），回 MCP tool error 而非 HTTP 403，讓 Claude 能讀到訊息並轉述「你的 token 是 viewer，請找 uploader 上傳」。

### 4.3 稽核

`audit.sqlite` 單表：

```
audit(id, at, name, role, kind, action, args_json, status, duration_ms, detail)
  kind   : 'upload' | 'tool' | 'resource'
  action : 'upload:202610' | 'ingest_month' | 'get_project' | ...
  status : 'ok' | 'error' | 'forbidden' | 'rejected_pii'
```

- 每次 upload、tool 呼叫、template resource（`eis://{month}/report.html`）讀取各寫一列。`args_json` 只存參數，不存回傳。
- 靜態 resource `eis://months` 不進稽核：SDK 不允許靜態 URI 的 handler 注入 `Context`，拿不到呼叫者；同內容的 `list_months()` tool 有稽核。
- `list_months()` 的「誰何時上傳、ingest 狀態」從 `_upload.json` 與 `ingest.json` 讀，不查 SQLite；SQLite 僅供事後稽核。

### 4.4 原檔保護

- 服務以專用系統帳號執行；`input/` 0700、`tokens.yaml` 0600，啟動時檢查權限，不符則拒絕啟動並印出修正指令。
- 沒有任何 tool / resource 讀取 `input/`；`get_project` 的 tasks 沿用快照裡的 `description_masked`。
- 所有 tool 回傳序列化後再過一次 `render/pii.find_pii()`，命中則改回 error 並寫 audit `status='rejected_pii'`（快照本身在 ingest 時已過檢，這是出口保險）。
- 上傳檔名（含 PM 姓名）只出現在上傳者當下的 HTTP 回應與 server 端 `_upload.json`，不經 MCP 回傳。

## 5. 上傳與 ingest 流程

1. uploader 執行 `scripts/eis-upload.sh 202610 ./input-10`（內部 `curl -F` 逐檔 POST）。
2. server 端 `/upload/{month}`：
   - `month` 必須符合 `^\d{6}$`。
   - 檔名必須符合四類樣式之一（`Project List-*.xlsx`、`BU10_Project_Briefing_*.xlsx`、`*Resource Summary.xlsx`、`*Resource Control List-*.xlsx|.xlsb`），且不得含路徑分隔字元或 `~$` 前綴；不符 HTTP 400 列出原因。
   - 同名覆蓋，`_upload.json` 追加一筆（保留覆蓋歷史）。
   - 回 `{stored: name, size, sha256}`。
3. 在 Claude 裡呼叫 `ingest_month("202610", today?)`：
   - 取 `ingest_lock/{month}` 檔案鎖（`fcntl.flock`），同月份並發 ingest 第二個立即回 error `busy`。
   - 檔案齊全檢查：缺 master / briefing / summary 任一 → error，訊息列出缺哪一類與期望檔名樣式；Control List 為 0 份時允許但在回傳 `warnings` 提示。
   - 呼叫 `build_month()`。同步等待（實測數十秒，在 SDK 預設 timeout 內）。
   - `pii_hits` 非空 → 不寫快照、不寫 HTML；回 `{status: "rejected_pii", hits, hits_count}`，`hits` 為遮罩後片段（保留前 2 字元，其餘 `*`），`hits_count` 為總命中數；未遮罩的原始片段只留在 server 端的 `ingest.json`；`ingest.json` 記一筆；原檔保留。
   - 成功 → `write_snapshot()`、寫 `report_en.html`、`ingest.json` 追加；清除該月份的記憶體快取；回 `{status: "ok", summary, health: [level, check, count], issues_count}`。
4. 重跑同月份直接覆蓋快照，`ingest.json` 保留歷次紀錄。

`today` 預設為 server 當天；重跑歷史月份時可指定，語意同 CLI `--today`。

## 6. 查詢 tools

### 6.1 共同規則

- `month` 參數省略 → 用最新一個有成功快照的月份。回傳一律帶 `meta: {report_month, latest_month, snap_date, generated}`，Claude 才知道在看哪個月。
- 回傳只含快照既有欄位，每筆保留快照的 `source` 欄；server 不推算、不補值。
- 未知月份 → error `unknown_month`，訊息附 `list_months()` 的可用清單。
- 快照載入採記憶體快取（以檔案 mtime 為 key），ingest 成功後清除。
- 每個 tool 的 docstring 即 MCP description，用英文寫，說明參數與回傳欄位，因為 client 端的模型靠它決定何時呼叫。
- 例外：`diff_project` 比較兩個月份，回傳 `meta_a` 與 `meta_b` 而非單一 `meta`。

### 6.2 tool 清單

| tool | 參數 | 回傳 | 實作依據 |
|---|---|---|---|
| `get_project(query, month?)` | `query`：code、名稱或別名 | 命中一筆 → 完整 project dict（code、name、group、family、customer、product、stage、stage_cat、dates、in_briefing、in_control_list、has_plan、fte、ntd、pva、tasks、history）；多筆 → `{candidates: [{code, name}]}` 要求指定；零筆 → error `not_found` | 先精確比對 code；再 `config.normalize_name()` 對名稱與 `portfolio_aliases.yaml` |
| `search_projects(stage_cat?, group?, customer?, biz_type?, category?, text?, month?)` | 全部可選；`biz_type`（JDM/ODM/EMS）與 `category`（Tablet/NB/AI PC…）來自 2026-09 起 Briefing 的 Type/Category 欄，舊版面為空字串；`text` 對 name/customer/product 做正規化子字串 | `[{code, name, stage, stage_cat, customer, group, biz_type, category, panel_size, latest_fte}]` | 純過濾 `projects` |
| `get_exceptions(month?)` | | 快照 `exceptions` 原樣 | |
| `get_health(month?)` | | 快照 `health` 原樣 | |
| `get_upcoming_milestones(weeks=8, month?, today?)` | | `[{code, name, stage_cat, milestone, date, days_left}]`，`milestone` ∈ evt/dvt/pvt/mp；範圍為 `today - weeks*7` 到 `today + weeks*7`，已過期者 `days_left` 為負 | 新寫純函式，放 `tools/overview.py`：只看 `in_briefing` 且 `stage_cat != Suspended` 的專案（與 `rules._active()` 同條件），日期差用 `rules.days_between()`；不重用 `milestones_passed()`，它只回逾期的 MP/PVT |
| `get_dept_loads(month?, min_util?)` | `min_util` 為百分比（`util` 是整數百分比或 `null`；`null` 排最後且被 `min_util` 排除） | `loads` 過濾後，依 `util` 降冪 | |
| `get_capacity(month?)` | | 快照 `capacity` 全序列 | |
| `diff_project(code, month_a, month_b)` | | `{code, changed: {field: {a, b}}}`；只列有差異的欄位，巢狀欄位（dates、fte、pva）逐鍵比較 | 新寫的純函式，放 `tools/diff.py`；數值差異門檻沿用 `diff.cross_month_corrections` 的 `tol=0.05` |
| `get_corrections(month?)` | | `issues` 中 `check == "cross_month_correction"` 的列 | 名稱來自 `model/diff.py:cross_month_corrections()` |
| `list_months()` | | `{month, status, uploads: [{category, size, sha256, uploaded_by, uploaded_at}], last_ingest: {at, by, status, ...} \| null}`，含 `broken`（JSON 損壞）與 `uploaded_only`（有原檔未 ingest）；`uploads` 不含原始檔名（Control List 檔名內嵌 PM 姓名） | `_upload.json` + `ingest.json` |
| `ingest_month(report_month, today?)` | uploader 限定 | 見第 5 節 | |

### 6.3 resources

| URI | 內容 |
|---|---|
| `eis://months` | 同 `list_months()` 的 JSON |
| `eis://{month}/report.html` | 該月 `report_en.html`，mime `text/html` |

## 7. 錯誤處理

| 情境 | 行為 |
|---|---|
| 無 token / token 無效 | HTTP 401 |
| viewer 上傳 | HTTP 403 |
| viewer 呼叫 `ingest_month` | MCP error `forbidden`，訊息說明需 uploader |
| 上傳檔名不符 | HTTP 400，列出四類允許樣式 |
| ingest 缺檔 | MCP error `missing_input`，列出缺的類別 |
| ingest 檔案不可讀 | MCP error `input_unreadable`，附原 ValueError 訊息與檔名 |
| ingest 無非零月份 | MCP error `no_manpower_month` |
| ingest PII 命中 | 回 `status: rejected_pii`（非 error，讓 Claude 能解釋要改哪裡） |
| 同月份並發 ingest | MCP error `busy` |
| 查詢未知月份 | MCP error `unknown_month`，附可用月份 |
| 快照 JSON 損壞 | 該月份 `status: broken`；其他月份正常；`get_*` 指到它時 error `snapshot_broken` 並建議重跑 ingest |
| 回傳命中 PII | MCP error `rejected_pii`，audit 記錄 |
| 啟動時權限不符 | 拒絕啟動，印出 `chmod` 指令 |

所有 MCP error 訊息都包含「下一步該做什麼」，因為讀訊息的是 client 端模型，要能直接轉述給人。

## 8. 測試

- **`pipeline.build_month()`**：用 `tests/portfolio/conftest.py` 既有 fixture，驗證輸出與 CLI 產出的快照逐鍵相等；三種例外各一個測試；`test_cli.py` 不改。
- **auth**：Starlette `TestClient`，三態：無 token 401、viewer 上傳 403、viewer 呼叫 `ingest_month` 得 `forbidden`、uploader 全通。
- **upload**：合法四類檔名各一；非法檔名（路徑穿越、`~$`、`.exe`）400；同名覆蓋 `_upload.json` 累積兩筆；`month` 非六位數 400。
- **ingest**：用 fixture 輸入包跑到底，快照落地且 `ingest.json` 有一筆；缺 summary 得 `missing_input`；並發鎖用兩個執行緒驗證第二個得 `busy`；假造含 `LA1234567` 的 briefing 驗證 `rejected_pii` 且不寫快照。
- **tools**：對一份固定測試快照（從 fixture 產出，存 `tests/eis_mcp/fixtures/`）逐 tool 驗證回傳形狀；`get_project` 的三種命中結果；`diff_project` 對兩份手工差異快照；`month` 省略取最新。
- **PII 出口保險**：monkeypatch 快照塞入工號，驗證 `get_project` 回 `rejected_pii`。
- **audit**：任一 tool 呼叫後 SQLite 多一列且欄位正確。

## 9. 依賴與執行

`requirements.txt` 新增：`mcp>=2.2,<3`、`starlette`、`uvicorn`、`python-multipart`、`httpx`（測試用 ASGI transport）。

啟動：

```bash
python -m src.eis_mcp --data /srv/eis --host 0.0.0.0 --port 8765
```

client 端設定（Claude Desktop / Claude Code）：

```json
{"mcpServers": {"eis": {"url": "http://<host>:8765/mcp",
                         "headers": {"Authorization": "Bearer <token>"}}}}
```

上傳：

```bash
scripts/eis-upload.sh 202610 ./input-10     # 讀 $EIS_TOKEN 與 $EIS_URL
```

## 10. 決策紀錄

| 決策 | 選項 | 理由 |
|---|---|---|
| input 定義 | 上傳 EIS Excel 包（非人工填狀態） | 真相留在 EIS 匯出檔，符合第一守則 |
| 部署 | 內網共用 HTTP（非本機 stdio） | 「有人 input、其他人 query」需要共用狀態 |
| 原檔 | 保留在 server | 需求方選擇，方便重跑與稽核；以目錄權限與「不暴露原檔」補償 |
| 認證 | 兩級靜態 token | 第一版可落地；SSO 留待 IT 配合 |
| 上傳通道 | 獨立 HTTP endpoint，非 MCP tool 參數 | 大檔 base64 進 tool call 不可行 |
| 儲存 | 沿用快照 JSON，不建 SQL 表 | 1.7 MB 直接載入即可；避免兩套資料模型 |
