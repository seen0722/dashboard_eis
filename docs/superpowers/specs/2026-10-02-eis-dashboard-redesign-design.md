# EIS Dashboard Redesign（v2 風格＋ECharts）— 設計文件

日期：2026-10-02
狀態：已實作（計畫 docs/superpowers/plans/2026-10-02-eis-dashboard-redesign.md）
相依：`2026-09-12-bu10-portfolio-dashboard-design.md`（月報單頁、快照格式）、`2026-09-21-eis-web-ui-design.md`（`/ui/` 頁面）
視覺依據：`out/mock_bu10_portfolio_v2.html`（不進版控；本設計採用其版面語彙，不採用其資料口徑）

## 1. 背景與目標

2026-09-12 的月報設計在 mock v2（圖表儀表板）與 v3（第一屏＝本月決策）之間選了 v3。BU 主管實際使用後偏好 v2 的儀表板風格。本設計把 `/ui/` 網頁與月報單頁 HTML 一起改為 v2 風格，重點是圖表。

成功標準：
1. 主管打開 Overview 第一屏就看到 KPI 卡與分布圖，不必讀文字段落。
2. 圖上的每一個數字都能指回快照的某個欄位（AGENTS.md 第一守則）；資料缺口在圖上明示，不顯示成 0。
3. 月報仍是單一檔案、可寄送；沒有 JS 時（郵件預覽、列印）每張圖的數字仍可從資料表讀到。

## 2. 需求方決定（2026-10-02）

- 範圍：`/ui/` 與月報 HTML 兩者，共用同一套圖表元件與配色。
- 「Decisions this month」移出第一屏，成為獨立分頁（月報為獨立區塊）。
- Overview 放四類圖：Stage／Customer 分布、六個月 Gantt、Resource Load 熱度表、Forecast vs Capacity；未來 8 週里程碑表保留並加狀態標籤。
- 圖表 library：Apache ECharts，vendor 進 repo。
- 分支從 `main` 開（`feat/dashboard-redesign`），與 `feat/llm-enrichment` 各自合併。

## 3. 原則

1. **數字在 server 算。** 每張圖由 Python 純函式產生 ECharts option dict（含所有數值），以 JSON 嵌入頁面；JS 只負責 `echarts.init(el).setOption(opt)`。
2. **缺口明示。** 不在 Briefing 的專案、空白客戶、沒有填報的月份、沒有 budget 的專案，都以獨立類別、斜線格、或覆蓋率文字顯示，不合併、不補 0。
3. **不新增規則。** At Risk KPI 是既有 `milestones_passed`（exceptions）與 `mp_slipped`（health）兩條規則涉及專案的聯集。
4. **無 JS 可讀。** 每張圖下方附 `<details>` 資料表（同一份 option 資料產生）。
5. **PII 出口不變。** 嵌入的 JSON 是 HTML 文字的一部分，照舊整頁過 `find_pii`。
6. **零外部網路依賴。** 不用 CDN；字型沿用系統字型堆疊。

## 4. 架構

```
vendor/echarts/echarts.min.js        新：Apache ECharts（固定版本，檔頭保留授權註記）＋ LICENSE、VERSION
src/portfolio/render/viz/
├── __init__.py
├── options.py     純函式：snapshot → ECharts option dict（每張圖一個函式）
├── tables.py      option dict → <details> 資料表 HTML
├── embed.py       chart_div(id, option) → <div> + <script type="application/json">；echarts_tag(mode) → 內嵌或外部 <script>
└── tokens.py      設計 token（色票、stage 對應色、狀態色）供 CSS 與 option 共用
src/portfolio/render/css.py          改：新版型（側欄、KPI 卡、卡片格線、狀態標籤）
src/portfolio/render/page.py         改：月報改為 v2 版型；決策成為獨立區塊
src/portfolio/render/charts.py       移除被 ECharts 取代的 timeline_svg / capacity_svg / pva_svg（測試同步調整）
src/eis_mcp/web/shell.py             改：左側導覽外殼、`/ui/static/echarts.min.js` script 標籤
src/eis_mcp/web/routes.py            改：新增 /ui/{month}/decisions、/ui/{month}/health、/ui/static/echarts.min.js
src/eis_mcp/web/pages_overview.py    改：KPI＋圖表版面
src/eis_mcp/web/pages_decisions.py   新：決策清單（沿用 exceptions_html）
src/eis_mcp/web/pages_health.py      新：健康度表＋Corrections
src/eis_mcp/web/pages_load.py        改：部門 × 月熱度表
src/eis_mcp/web/pages_project.py     改：小卡、PVA 圖、迷你時程
```

### 4.1 ECharts 交付

- 版本固定：實作時取 npm registry 上 `echarts` 最新的 5.x 正式版，版本號寫進 `vendor/echarts/VERSION`，檔案、版本號與 Apache-2.0 授權放 `vendor/echarts/`。
- 月報：`echarts_tag("inline")` 把整份 min.js 內嵌（每份約 +1MB）。
- `/ui/`：`echarts_tag("static")` 輸出 `<script src="/ui/static/echarts.min.js">`；route 回傳該檔並帶 `Cache-Control: public, max-age=86400`。此 route 不需 token（與 `/ui/` 其他頁一致為免登入唯讀）。
- 初始化腳本（inline，<40 行）：找所有 `[data-chart]`，讀相鄰 JSON，`echarts.init`；視窗縮放時 `resize`；Gantt 的客戶篩選以 `setOption` 重繪。

## 5. 頁面

### 5.1 外框

左側深色導覽列（品牌、月份選擇器、導覽項目；Decisions 顯示件數 badge）、頁首（標題、Report month · keyed in through · Briefing 日期、搜尋）。寬度 ≤ 900px 時側欄收為頁首選單按鈕。卡片＝單一圓角底卡；若有色頭標頭，只圓上緣（避免雙圓角互咬的凹口）。

導覽：Overview｜Decisions｜Projects｜Loads｜Data health｜Report。舊網址 `/ui/{month}/corrections` 轉址到 `/ui/{month}/health`（301）。

### 5.2 Overview（`/ui/{month}/`）與月報第一區

1. KPI 卡 ×6：Total projects（快照全部專案，與甜甜圈中心數字相同；副標「{n} in Briefing · {m} terminated/suspended」）、RFQ/RFI、POC、Execution、MP + Sustain、At Risk（點擊 → Decisions）。
2. 分布列：Stage 甜甜圈｜Customer 橫條。
3. 六個月 Gantt（全寬）。
4. 下排三欄：Resource Load 熱度表（function 層級）｜Forecast vs Capacity｜未來 8 週里程碑。

月報第一區相同，接著是 Decisions、Data health、各案附錄；左側導覽在月報裡是頁內錨點。

### 5.3 其他頁

- **Decisions**：現行 `exceptions_html` 原樣搬過來，套新樣式。
- **Projects**：現有清單與篩選，套新表格樣式。
- **Loads**：部門 × 月熱度表（每列一個部門，依 function 分組）＋現有明細表。
- **Data health**：現行健康度表＋Corrections 內容。
- **單案頁**：頂部小卡（stage、customer、下一個里程碑、最新月 FTE）；PVA 圖（FU RD／BU RD／PM 三組，plan 折線＋actual 長條）；迷你時程；其餘區塊不變。

## 6. 各圖口徑

| 函式 | 資料 | 缺口呈現 |
|---|---|---|
| `kpis(snap)` | `stage_cat` 計數；At Risk ＝ `exceptions[title=milestones_passed].codes` ∪ `health[check=mp_slipped]` 的專案 | 與甜甜圈同一來源 |
| `stage_donut(snap)` | `stage_cat` | 空值成「Not in Briefing」灰色區塊 |
| `customer_bars(snap, top=8)` | `customer`（去前後空白） | 空白→「(blank)」、`NA` 獨立一列；第 9 名以後併 Others |
| `gantt(snap, today, months=6)` | 活躍專案（`stage_cat ∉ INACTIVE` 且 in_briefing）的 `dates` EVT/DVT/PVT/MP | 無日期列顯示「no milestone dates」；已過期且 stage 未前進者標紅（沿用 `milestones_passed` 判定） |
| `load_heatmap(snap, by="function")` | `loads`：同 function 同月 Σallocated ÷ Σkeyed_in ×100 | Σkeyed_in = 0 → `null`，斜線格「no data」；圖說「denominator = headcount that keyed in」 |
| `forecast_capacity(snap)` | actual／plan＝各案 `pva` 三組加總；capacity＝`capacity` | 標題旁「Plan covers {n_plan}/{n_projects} projects」；latest_month 之後 capacity 以虛線、圖說「carried from {latest}」（沿用 `carry_forward`） |
| `milestones(snap, today, weeks)` | 沿用現行 upcoming 計算 | 狀態：Passed（紅）、Due ≤14d（橙）、On track（綠） |
| `pva(project)` | 單案 `pva` 三組 | 該組 plan 全 0 → 只畫 actual，圖例註「no budget plan」 |

`n_plan`／`n_projects` 由程式計算，不寫死。

## 7. 錯誤處理

| 情況 | 行為 |
|---|---|
| 舊快照缺欄位（例如沒有 `capacity`） | 該圖不畫，卡片內顯示「not in this snapshot」；頁面 200 |
| JS 被擋或未執行 | 圖區顯示 `<noscript>` 提示，`<details>` 資料表照常可讀 |
| `/ui/static/echarts.min.js` 讀不到（部署漏檔） | server 啟動時檢查檔案存在，缺檔就拒絕啟動並指出路徑 |
| option 中出現 NaN/inf | JSON 序列化前轉 `null`；測試涵蓋 |

## 8. 不做（本輪）

- Product 分布圖（需另建產品對照表；mock v2 中 49% 落在 Others）。
- v2 的 Timeline、Pipeline (RFQ/RFI) 獨立頁。
- 深色模式。
- `feat/llm-enrichment` 的 AI 區塊樣式（該分支合併時再套新樣式）。

## 9. 測試

- `options.py`：每個函式一組測試，斷言數值（stage 計數總和＝專案數、Not in Briefing 計數、customer 空白與 NA 分列、熱度表無資料格為 `null`、forecast 覆蓋率字串、At Risk 聯集去重）。
- `embed.py`：JSON 中 `</script>` 被跳脫；NaN 轉 null。
- 網頁：每頁 200、含 `data-chart` 與 `<details>`、`/ui/static/echarts.min.js` 回 200 且有 Cache-Control、corrections 轉址、Decisions badge 件數＝exceptions 數。
- 月報：內嵌 echarts、無外部 `<script src>`、`find_pii` 通過。
- 版面：headless Chrome 於 1440 與 375 寬截圖，`document.documentElement.scrollWidth <= innerWidth`；色頭卡交界處放大目視無凹口。
