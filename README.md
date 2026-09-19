# BU10 Portfolio Review — 產生月報

每月一份給 BU10 主管的英文單頁 HTML：第一屏是規則算出來的「Decisions this month」，後面是里程碑、六個月時程、人力與產能、資料健康度、逐案附錄。輸出零外部依賴，可以直接 mail 給人用瀏覽器開。

設計文件：`docs/superpowers/specs/2026-09-12-bu10-portfolio-dashboard-design.md`

## 1. 環境（只需做一次）

需要 Python 3.12 以上（開發時用 3.14）。

```bash
python3 -m venv /tmp/dashboard_eis_venv
/tmp/dashboard_eis_venv/bin/pip install -r requirements.txt
```

以下指令都在 repo 根目錄執行，`python` 指 `/tmp/dashboard_eis_venv/bin/python`。

## 2. 準備每月的輸入包

在 repo 根目錄放一個 `input-<MM>/` 目錄（例如 `input-10/`），內容直接從 EIS 與 PM 拿到的原檔，不用改名：

| 檔案 | 來源 | 用途 |
|---|---|---|
| `Project List-YYYYMM.xlsx` | EIS | PROJECTCODE 主檔，所有資料靠它對上 |
| `BU10_Project_Briefing_YYYYMMDD.xlsx` | PM 雙週 Briefing | Stage、EVT/DVT/PVT/MP 日期；一個檔內含所有雙週分頁，取最新一份即可 |
| `2026 EIS Resource Summary.xlsx` | EIS | 每案逐月人力與 NTD，也決定「最新月」 |
| `2026  EIS Resource Control List-<專案> (<PM>).xlsx` × N | EIS | Plan vs Actual、任務列、部門負載；`.xlsb` 也可 |

`input-*/` 已在 `.gitignore`，原檔含姓名工號，絕不進版控。

## 3. 產生報告

```bash
python -m src.portfolio.cli --input input-10 --report-month 202610
```

參數：

| 參數 | 預設 | 說明 |
|---|---|---|
| `--input` | 必填 | 輸入包目錄 |
| `--report-month` | 必填 | 報告月份 `YYYYMM`，也是快照目錄名 |
| `--today` | 今天 | 計算「已過期」「未來八週」的基準日，重跑歷史月份時指定 |
| `--lang` | `en` | `zh` 可產中文版（字串表已備，未經完整驗證） |
| `--snapshots` | `data/snapshots` | 每月正規化 JSON 存放處，下個月自動拿來比對 |
| `--out` | `out` | HTML 輸出目錄 |

輸出：

- `out/portfolio_202610_en.html` — 交付物，單檔自包含
- `data/snapshots/202610/portfolio.json` — 正規化資料，供下個月比對「過去月份數字是否被改」

結束碼：`0` 成功；`1` 主檔、Briefing 或 Resource Summary 缺檔或不可讀，或 Resource Summary 沒有任何非零月份；`2` PII 檢查命中（工號或人名形狀），此時 HTML 與快照都不會寫出，stderr 會列出命中片段。

Control List 有問題不會中斷，會變成報告裡「Data health」的一列。

## 4. 每月流程

1. 把新的一包放進 `input-<MM>/`。
2. 跑第 3 節的指令；看 stdout 的一行摘要（案數、Control List 份數、最新月）。
3. 打開 HTML，先看「Data health」：`decide` 級的列代表要主管出面，`track` 級由你處理（例如名稱對不到主檔，補到 `config/portfolio_aliases.yaml`）。
4. 確認無誤後寄出 HTML。若郵件閘道擋 `.html`，壓成 zip。

## 5. 調整規則

- 門檻（MP 延後天數、可調度部門的負載 %、停案掛帳門檻等）：`config/thresholds.yaml` 的 `portfolio:` 區塊。
- Stage 文字分類：`config/stages.yaml`。
- 名稱備援對照（只在該列沒有 PROJECTCODE 時才用）：`config/portfolio_aliases.yaml`。解析順序是 代碼 → alias → 正規化全名 → 唯一尾綴匹配。
- 介面文字：`src/portfolio/render/strings.py`，en 與 zh 的 key 必須一致，測試會擋。

## 6. 測試

```bash
python -m pytest tests/portfolio -q
```

全部用合成的小 xlsx 跑，不需要真實資料。改任何規則或版面後都跑一次。

## 7. MCP server（內網共用查詢）

`src/eis_mcp` 把同一條管線包成 Streamable HTTP MCP server：uploader 上傳每月 Excel 包並執行 `ingest_month`，其他人用 Claude Desktop / Claude Code 查詢。設計文件：`docs/superpowers/specs/2026-09-18-eis-mcp-server-design.md`。

### 7.1 伺服器端（做一次）

先產生一個 token（不要用範例裡的字面值，那只是佔位符，啟動時會被拒絕）：

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

把輸出貼進 `token:` 那一行：

```bash
mkdir -p server_data
cat > server_data/tokens.yaml <<'EOF'
tokens:
  - token: "REPLACE_ME"
    name: Alice
    role: uploader        # uploader | viewer
EOF
chmod 600 server_data/tokens.yaml
python -m src.eis_mcp --data server_data --host 0.0.0.0 --port 8765
```

- 原檔落在 `server_data/input/<YYYYMM>/`（0700），快照在 `server_data/snapshots/<YYYYMM>/`，稽核在 `server_data/audit.sqlite`。整個 `server_data/` 不進版控。
- 權限不對（`input/` 非 0700、`tokens.yaml` 非 0600）會拒絕啟動並印出 `chmod` 指令。
- 改 `tokens.yaml` 後要重啟。

營運注意事項：
- `audit.sqlite` 與 `snapshots/*/ingest.json` 含被判定為 PII 的原始片段，備份與權限比照原檔。
- 上傳無大小上限（內網、uploader 限定）。
- 建議一律設 `--allowed-host`。
- 若要防 DNS rebinding，加 `--allowed-host eis-host:8765`（可重複）。TLS 由前置 nginx 處理。

### 7.2 client 端設定

```json
{"mcpServers": {"eis": {"url": "http://eis-host:8765/mcp",
                         "headers": {"Authorization": "Bearer <token>"}}}}
```

### 7.3 每月流程（uploader）

```bash
EIS_URL=http://eis-host:8765 EIS_TOKEN=<token> scripts/eis-upload.sh 202610 ./input-10
```

然後在 Claude 裡說「ingest 202610」（呼叫 `ingest_month("202610")`）。回傳 `rejected_pii` 代表原檔含姓名工號形狀的字串，什麼都不會寫；修好原檔重傳再跑。

端到端實測：真實的 8 月包（41 個檔案、38 份 Control List、62 個專案）ingest 約 1.5 秒。

### 7.4 可用的 tools

| tool | 用途 |
|---|---|
| `ingest_month(report_month, today?)` | uploader 限定；跑管線、寫快照 |
| `list_months()` | 已有月份、上傳檔的 category/size/sha256/uploader/time（不含原始檔名）、ingest 狀態 |
| `get_project(query, month?)` | 代碼 / 名稱 / alias 查單案 |
| `search_projects(stage_cat?, group?, customer?, text?, month?)` | 篩選清單 |
| `get_exceptions(month?)` / `get_health(month?)` | 第一屏 Decisions 與 Data health |
| `get_upcoming_milestones(weeks=8, month?, today?)` | 前後 N 週的 EVT/DVT/PVT/MP |
| `get_dept_loads(month?, min_util?)` / `get_capacity(month?)` | 部門負載與產能；`min_util` 是百分比（例如 85），`util` 為 `null` 的部門排最後、被 `min_util` 排除 |
| `diff_project(code, month_a, month_b)` / `get_corrections(month?)` | 跨月差異、歷史數字被改 |

`diff_project` 回傳 `meta_a` / `meta_b`（兩個月份各自的 meta），沒有單一 `meta`；其他 tool 一律有 `meta`。

Resources：`eis://months`、`eis://<YYYYMM>/report.html`（月報 HTML）。

所有回傳都帶 `meta.report_month`；每個 tool 回傳出口都再過一次 PII 檢查。

### 7.5 測試

```bash
python -m pytest tests -q
```

### 7.6 內網主機部署（systemd）

`deploy/` 有一組可直接用的部署檔：

| 檔案 | 用途 |
|---|---|
| `deploy/install.sh` | 冪等安裝腳本：建 `eis` 服務帳號、程式碼 rsync 到 `/opt/eis-mcp`、建 venv、資料目錄 `/var/lib/eis-mcp`（0700）、首次產生 `tokens.yaml`、寫 `/etc/eis-mcp/env`、裝 unit 並啟動 |
| `deploy/eis-mcp.service` | systemd unit：非 root、`UMask=0077`、程式碼唯讀、只允許寫資料目錄、失敗自動重啟、log 進 journald |
| `deploy/env.example` | 監聽位址、port、`--allowed-host` 設定；安裝時複製到 `/etc/eis-mcp/env` |
| `deploy/offline/` | 進版控的離線檔案：40 個 wheel + Python 3.12 stripped tarball；`git clone` 後主機不需任何網路即可 `sudo deploy/install.sh`（自動偵測） |
| `deploy/bundle-offline.sh` | 主機連不到 PyPI 時：在 Mac 打包程式碼＋全部 wheel（約 12 MB），scp 到主機後 `sudo deploy/install.sh` 自動離線安裝 |
| `deploy/eis-token.sh` | 發放／列出／輪換／撤銷 token：`sudo deploy/eis-token.sh add <名字> viewer`，產生後只印一次並自動重啟服務 |

```bash
git clone <repo> && cd dashboard_eis
sudo deploy/install.sh              # 需 python3.12+；其他版本用 PYTHON=/usr/bin/python3.12 sudo -E deploy/install.sh
sudo -u eis cat /var/lib/eis-mcp/tokens.yaml   # 發 token 給同仁
journalctl -u eis-mcp -f
```

更新程式：`git pull && sudo deploy/install.sh`（資料、tokens、env 都保留）。加人或改 token：編輯 `/var/lib/eis-mcp/tokens.yaml` 後 `sudo systemctl restart eis-mcp`。

## 8. 已知限制

- 每人每月填報上限 1.0 FTE，超載不會出現在數字裡；報告頁尾有註明。
- 部門負載的分母是「有填報的人數」，不是編制。
- Briefing 裡停案的 PROJECTCODE 常不在主檔（主檔只列在案專案），這些案子的掛帳人力接不到停案清單，會顯示在 Data health 的 name_unresolved。
- 舊的月報管線 `src/build_review.py` 與本管線互不相干，說明見 `AGENTS.md`。
