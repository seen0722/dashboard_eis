# EIS Web UI — 設計文件

日期：2026-09-21
狀態：已實作（2026-09-21，計畫 docs/superpowers/plans/2026-09-21-eis-web-ui.md）
相依：`docs/superpowers/specs/2026-09-18-eis-mcp-server-design.md`（MCP server、資料目錄、快照格式以該文件為準，本文件不重複）

## 1. 目標與受眾

- **目的**：不用裝 MCP client 的同仁，也能用瀏覽器查 EIS 專案狀態。內容與 MCP tools 一對一，同一份快照、同一套規則。
- **受眾**：內網同仁，全部視為 viewer。需求方確認**不做存取管制**：頁面不需 token、不需登入。
- **部署**：掛在既有 `src/eis_mcp` 的同一支 Starlette app、同一個 port，路徑前綴 `/ui/`。內網 nginx 多開一個 `location /ui/`。VPS 那台 nginx 只代理 `/mcp` 與 `/upload/`，因此即使部署同一版程式，公網也看不到 `/ui/`。

### 明確不做

- 登入、session、角色；`tokens.yaml` 與 `BearerAuthMiddleware` 對 `/mcp`、`/upload/` 的行為完全不變。
- 從網頁上傳或 ingest（uploader 流程仍走 `scripts/eis-upload.sh` + MCP `ingest_month`）。
- JSON `/api/*`。程式化取資料走 MCP；`queries.py` 抽出後日後要加很便宜。
- 前端框架、Node build 鏈、CDN 資源。內網主機離線部署（`deploy/bundle-offline.sh`），一切 server-side render、CSS inline。
- 中文介面。v1 英文（與月報、tools 一致）；`?lang=zh` 留到 v2，`render/strings.py` 已有雙語字串。

## 2. 架構

```
src/eis_mcp/
├── app.py            # 改：build_app() 多呼叫 web.register_routes(mcp, state)
├── auth.py           # 改：BearerAuthMiddleware 對 PUBLIC_PREFIXES（"/ui/"）放行
├── queries.py        # 新：純查詢函式（snapshot dict → dict），MCP tool 與 web 共用
├── tools/*.py        # 改：tool 本體改呼叫 queries.py，只留 docstring、參數與 guarded()
└── web/
    ├── __init__.py   # register_routes()
    ├── routes.py     # Starlette route handlers：解析參數 → queries → pages → 出口檢查 → Response
    ├── shell.py      # 頁面外殼：<head>、nav、footer、錯誤頁；CSS = render/css.py + WEB_CSS
    ├── pages_overview.py   # 月份清單、總覽（重用 page.py 的 exceptions/health/stage_strip 片段；里程碑用 queries.upcoming）
    ├── pages_project.py    # 專案表、單案、diff
    └── pages_load.py       # 部門負載/產能、corrections
```

### 2.1 `queries.py`：把查詢從 tool 殼裡抽出來

現在每個 tool 的 `go(p)` 裡都是「`resolve_month` 拿快照 → 對 dict 篩選/組裝 → `with_meta`」。抽成純函式，簽章一律 `(snap: dict, ...) -> dict`，不碰 `ctx`、`state`、audit：

| 函式 | 來源 tool | 備註 |
|---|---|---|
| `project(snap, query, cfg)` | `get_project` | 回 `{"project"}` 或 `{"candidates", "hint"}`；查無 raise `NotFound` |
| `search(snap, stage_cat, group, customer, text)` | `search_projects` | 回 `{"count", "projects"}` |
| `exceptions(snap)` / `health(snap)` | `get_exceptions` / `get_health` | 直接取快照欄位 |
| `upcoming(snap, today, weeks)` | `get_upcoming_milestones` | `overview.upcoming_milestones` 搬進來 |
| `dept_loads(snap, min_util)` / `capacity(snap)` | `get_dept_loads` / `get_capacity` | 排序規則不變 |
| `diff(snap_a, snap_b, code)` | `diff_project` | 回 `{"code", "changed"}`；缺案 raise `NotFound(where=...)` |
| `corrections(snap)` | `get_corrections` | |

- 例外：`queries.NotFound(msg)`，訊息是完整句子（如 `no project in 202609 matches 'x'`）。tool 殼加 `not_found:` 前綴與 tool 專用提示（`Try search_projects(...)`）；web 翻成 404 並附回列表的連結。
- `resolve_month`、`with_meta`、`guarded`、`check_date` 留在 `tools/_common.py`；tool 的 docstring、參數與回傳格式**一字不改**，現有 173 個測試是這次重構的回歸保護。`tools.overview.upcoming_milestones` 與 `tools.diff.diff_values` 以 re-export 保留舊 import 路徑。
- `list_months` 與 `ingest_month` 不抽（前者只是 `store.months()`，後者是寫入操作，web 不用）。

### 2.2 認證邊界

`BearerAuthMiddleware.dispatch()` 加一條：`is_public(path)` 為真就直接 `call_next`，不設 `request.state.principal`。`is_public` 只認 `PUBLIC_PATHS = ("/ui",)` 的完全相等與 `PUBLIC_PREFIXES = ("/ui/",)` 的前綴；`/ui`（無斜線）放行是為了讓 route 層能 redirect 到 `/ui/`。其餘路徑行為不變。

這是本次唯一動到安全邊界的改動，測試明訂：
- `GET /ui/` 無 header → 200。
- `POST /mcp` 無 header → 401；`POST /upload/202609` 無 header → 401（與現況相同）。
- `GET /uiX/...`、`GET /ui-anything` → 401（前綴比對含斜線）。

### 2.3 每個頁面請求的流程

```
route handler
  ├─ 解析 path/query 參數（month 格式、日期格式、數值）
  ├─ store.load_snapshot(month)          # UnknownMonth / SnapshotBroken → 錯誤頁
  ├─ queries.xxx(snap, ...)              # NotFound → 404 頁
  ├─ pages_xxx.render(...) → HTML 字串
  ├─ find_pii(html)                      # 命中 → 整頁不出，回 503 "withheld"，audit rejected_pii
  ├─ audit.record(None, "web", path, params, status, ms)
  └─ HTMLResponse
```

- **PII 出口保險**與 tools 相同：用 `portfolio.render.pii.find_pii`，命中就整頁攔下。月報 HTML 在 ingest 時已檢查過，但 web 頁面是新組裝的內容，一律再檢一次。
- **Audit**：`kind="web"`，`name`/`role` 為空（`Audit.record` 已允許 `principal=None`），`action` 為路徑，`args` 為 query 參數。目的與 tools 一致：知道誰在什麼時候查了什麼；免登入所以只有來源，不記 IP（同 tools 不記）。
- **快照快取**：`Store.load_snapshot` 已有 mtime 快取，web 不另做。

## 3. 頁面

所有路徑在 `/ui/` 之下；`{month}` 一律 `YYYYMM`。

| 路徑 | 內容 | 對應 tool |
|---|---|---|
| `/ui/` | 月份清單（status、ingest 時間、上傳檔 category/size，不含原始檔名），最新 ok 月份放最上面並標示 latest；沒有任何月份時顯示「nothing ingested yet」 | `list_months` |
| `/ui/latest/` | 307 到最新 ok 月份的總覽（nav 與書籤用）；沒有月份時 404 | — |
| `/ui/{month}/` | 總覽：Decisions this month、stage 統計條、里程碑視窗（±N 週，與 `get_upcoming_milestones` 同義，不是月報的「-1 週到 +N 週」）、Data health。N 取 `cfg.thresholds["upcoming_weeks"]`，可用 `?weeks=`、`?today=` 覆蓋 | `get_exceptions` / `get_health` / `get_upcoming_milestones` |
| `/ui/{month}/projects?stage_cat=&group=&customer=&q=` | 專案表：code、name、stage、stage_cat、customer、group、latest FTE。四個篩選欄位為 GET 表單，狀態在 URL；`stage_cat` 用下拉（七個固定值），`group`/`customer` 用下拉（從快照 distinct 值填）；`q` 對應 tool 的 `text`。nav 搜尋框也送到這裡；`q` 與某個 code 相同（不分大小寫）或與恰好一個專案名稱完全相同時，先 307 到該單案頁（`queries.exact_code`，2026-10-01），否則走子字串比對，結果剛好一筆時同樣 307 | `search_projects` |
| `/ui/{month}/projects/{code}` | 單案：基本資料、dates、`in_briefing`/`in_control_list`/`has_plan`、FTE 與 NTD 12 個月表、PVA 圖（重用 `charts.pva_svg`）、tasks、history；頂端「compare with previous month」連到 diff（前一個 ok 月份存在時才顯示） | `get_project` |
| `/ui/{month}/projects/{code}/diff?to={YYYYMM}` | 跨月差異表：欄位、a、b；巢狀欄位攤平成 `dates.evt`、`pva.SW.plan` 這種鍵；`changed` 為空顯示 identical | `diff_project` |
| `/ui/{month}/loads?min_util=` | 部門負載表（dept、function、util 12 個月、latest_util，`min_util` 篩選）+ 產能圖（重用 `charts.capacity_svg`）。橘色標「latest_util 低於 `spare_capacity_pct`」的閒置產能，與月報「可調度部門」例外同義；不標 100%（mock 實測 54 個部門有 47 個是 100%，標了等於沒標） | `get_dept_loads` / `get_capacity` |
| `/ui/{month}/corrections` | 歷史數字被改清單 | `get_corrections` |
| `/ui/{month}/report.html` | 現成月報 `store.report_html(month)` 原樣送出 | resource `eis://{month}/report.html` |

### 3.1 共用外殼（`shell.py`）

- `<head>`：`<meta charset="utf-8">`、viewport、`<title>EIS · {page} · {YYYY-MM}</title>`、`<style>` 內嵌 `render/css.py` 的 `CSS` + `WEB_CSS`（nav、表單、錯誤頁、diff 表的少量樣式）。
- nav：月份下拉（列出所有 ok 月份，選了就跳同一頁的該月份）、Overview / Projects / Loads / Corrections / Report 連結、搜尋框（送到 projects 頁 `q=`）。
- footer：與月報相同的三行說明（資料來源、`report_month`、`latest_month`）。
- 每頁 `<h1>` 下方印資料時點：「Report month 2026-09 · manpower keyed in through Aug · Briefing 2026-09-07」，分別來自 `meta.report_month`、`meta.latest_month`、`meta.snap_date`（與 tools 的「回答時一律引用 meta」同一原則；2026-10-01 起不再直接印欄位名）。
- 表單一律 GET，無 JavaScript（2026-10-01 起）。月份切換是 GET 表單送到 `/ui/go?month=&page=`，server 驗證月份與 `page`（只接受 `/ui/{month}/` 之下的相對路徑，擋 scheme、host、開頭斜線、`..`、反斜線）後 307；鍵盤選月份不會每按一次就跳頁。diff 頁換月份時回到該案的單案頁。
- 頁面上的「幾天前／後」與里程碑視窗，`today` 預設為快照的 Briefing 日期（`meta.snap_date`），與例外文字的天數同一基準；`?today=` 可覆蓋。
- 總覽的例外每條附「Open:」連結到相關專案（來源是例外自帶的 `codes`）；Data health 名稱欄裡完全等於某專案名稱的項目為連結；decide 級三項與 Decisions 重複，收進 `<details>`。單案頁最新月份的 task 表預設展開。

### 3.2 視覺

沿用月報的紙色底、細線表格、`--signal` 橘色標示例外；不引入第二套配色。表格數字右對齊、`tabular-nums`（CSS 已有）。行動裝置寬度下表格外層 `overflow-x:auto`（CSS 已有 `.tl` 可套用）。

## 4. 錯誤處理

| 情況 | HTTP | 頁面內容 |
|---|---|---|
| `month` 非 `YYYYMM` 或無 snapshot | 404 | 「No snapshot for {month}」+ 可用月份連結 |
| snapshot 讀不出來（`SnapshotBroken`） | 503 | 「Snapshot for {month} is unreadable; ask an uploader to run ingest_month('{month}') again」 |
| 專案查無 | 404 | 訊息同 tool 的 `not_found`，附回 projects 頁連結 |
| 專案多筆符合 | 200 | 候選清單（code、name、stage），點了到單案頁 |
| diff 的 `to` 缺、格式錯或無 snapshot | 400 / 404 | 說明 + 可用月份 |
| `weeks`、`min_util` 非數字或超界（weeks 1–52，min_util 0–1000） | 400 | 說明 |
| 尚未 ingest 任何月份 | 200 | `/ui/` 顯示「nothing ingested yet」；其他頁 404 |
| PII 命中 | 503 | 「This page was withheld: it contained N PII-shaped fragment(s). Tell the server owner.」；audit `rejected_pii` |
| 未預期例外 | 500 | 通用錯誤頁；Starlette 預設 handler 即可，內容不回傳 traceback |

所有錯誤頁都走同一個 `shell.render_error(status, title, body_html, months)`，並一樣寫 audit（status 為 `error`、detail 為原因）。

## 5. 部署與文件

- `README.md` §7 新增「7.8 網頁查詢（免登入）」：路徑一覽、nginx `location /ui/ { proxy_pass ...; }` 範例、提醒 `/ui/` 沒有存取管制所以只該開在內網、VPS 不要開。
- `deploy/nginx.conf.sample`（若無則新增）加 `/ui/` location。systemd unit、`env.example`、`bundle-offline.sh` 不動（沒有新依賴）。
- `docs/eis-mcp-client-setup.md` 補一句：不想裝 client 的人可以直接開 `http://<HOST>:<PORT>/ui/`。
- `requirements.txt` 不變：Starlette、`find_pii`、`charts.py` 都已在。

## 6. 測試

- `tests/eis_mcp/test_queries.py`：每個 `queries.*` 函式的單元測試，用 `tests/portfolio/test_cli.build_input` 產的快照。
- `tests/eis_mcp/test_web.py`：`starlette.testclient.TestClient(build_app(...))`，不需要 MCP client helper。
  - 認證邊界（§2.2 三條）。
  - `/ui/` 200 列出月份且 latest 標示正確；`/ui/latest/` 307 到最新月；無月份時 `/ui/` 200 顯示提示、`/ui/latest/` 404。
  - 總覽含 exceptions 標題與 health 列；`?weeks=2` 改變里程碑數量。
  - projects 篩選：`stage_cat`、`group`、`q` 各一；`q` 命中一筆時 307 到單案頁。
  - 單案頁含 code、name、PVA `<svg>`；多筆候選頁；查無 404。
  - diff：有差異、identical、`to` 無 snapshot 404。
  - loads：`min_util` 篩選；corrections 頁。
  - `report.html` 內容與 `store.report_html` 相同。
  - PII：monkeypatch `find_pii` 回一筆 → 503 且 audit 有 `rejected_pii`。
  - 每個 200 請求 audit 都有一列 `kind="web"`。
- 既有 `tests/eis_mcp/test_tools_*.py` 不改，作為 `queries.py` 重構的回歸保護。

## 7. 開放事項（不阻塞 v1）

- 中文介面（`?lang=zh`）。
- JSON API。
- 若日後要開到內網以外或要區分人，再加登入；到時 `PUBLIC_PREFIXES` 改成空的即可回到全站 token。
