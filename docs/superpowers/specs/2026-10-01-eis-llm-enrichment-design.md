# EIS LLM 導入（Cambrian）— 設計文件

日期：2026-10-01
狀態：設計，待實作（計畫 docs/superpowers/plans/2026-10-01-eis-llm-enrichment.md）
相依：`2026-09-18-eis-mcp-server-design.md`（快照、資料目錄、store）、`2026-09-21-eis-web-ui-design.md`（`/ui/` 頁面）
Pilot 評估：`out/EIS_LLM_Work_Summary_AI_Pilot_Plan.md`（不進版控；本設計是該 Pilot 要用的軟體）

## 1. 目標

1. **Briefing 狀態說明原文上網頁（不用 LLM）。** 解析器早已讀出 `status_text`，但沒有存進快照。實測 50 筆最新 Briefing 中 28 筆有寫，中位數 110 字，直接顯示原文即可。
2. **大專案每月 task 描述的工作重點歸納（用 Cambrian）。** 202609 快照共 7,951 筆 task；8 月 task 最多的 6 案每案 102–165 筆，沒有人讀得完。程式先依 side＋function 分群並加總 FTE，Cambrian 只替每群取一個工作主題名稱、寫一句描述。

## 2. 需求方決定（2026-10-01）

- 內網環境下人名與資料都可以顯示：狀態說明原文照實顯示，包含人名。
- 現行 `find_pii` 只擋工號（`LA\d{7}`）與「英文名(中文名)」實名配對；實測新版 Briefing 狀態說明與 task 描述 0 命中，**本設計不改 PII 規則**，所有輸出照舊過 `find_pii`。
- 採「server 端產生，但與 ingest 分開」：核心快照 `portfolio.json` 維持不含任何 LLM 產出；AI 結果另存 `ai.json`。

## 3. 原則

1. **LLM 不輸出數字。** FTE、task 筆數、月份全部由程式計算並填入；LLM 回的 JSON 只有 `theme`（≤40 字元）與 `summary`（≤200 字元）。
2. **Grounding 檢查。** LLM 輸出中任何含數字的詞（版本、日期、數量、型號），必須逐字出現在該群的原文裡；不通過就丟掉該群的 AI 文字，改顯示「描述未通過檢查，請看原文」。
3. **與 ingest 分離。** `ingest_month` 完全不變。產生 AI 摘要是另一個指令，Cambrian 掛掉或很慢都不影響每月資料上線。
4. **過期偵測。** 每個專案的 AI 結果記下輸入雜湊；網頁重算當下快照的雜湊，不一致就顯示「摘要已過期」，不顯示舊內容。
5. **可快取。** 輸入雜湊、模型、prompt 版本都相同時沿用上次結果，不重打 Cambrian。
6. **標示清楚。** 網頁上標「AI summary」，並註明數字由程式計算、每點附來源 task 筆數，原文就在同頁下方。

## 4. 架構

```
src/portfolio/entities.py        改：Project.status_text
src/portfolio/model/normalize.py 改：最新 Briefing 的 status_text 寫進 Project
src/eis_mcp/ai/
├── __init__.py
├── groups.py      純函式：snapshot project → 分群（side, function, fte, n_tasks, texts）＋ input_hash
├── grounding.py   純函式：數字詞擷取與 grounded() 檢查
├── cambrian.py    Cambrian（OpenAI 相容）chat completions 客戶端，httpx，JSON mode
├── enrich.py      enrich_month()：選專案、分群、呼叫、檢查、快取、寫 ai.json
└── __main__.py    CLI：python -m src.eis_mcp.ai --data DIR --month YYYYMM
src/eis_mcp/store.py             改：ai_summary(month) 讀 ai.json
src/eis_mcp/web/pages_project.py 改：狀態說明區塊、AI 工作重點區塊
src/eis_mcp/web/routes.py        改：單案頁把 ai 結果傳進 page
config/thresholds.yaml           改：portfolio: 下加 ai_min_task_rows、ai_max_groups（load_config 只讀 portfolio 這層）
```

### 4.1 分群（`groups.py`）

- 只看快照 `meta.latest_month` 那個月的 tasks。
- 群組鍵 `(side, function.strip().upper())`，function 空白歸為 `"(none)"`。
- 每群：`fte` 加總（四捨五入 2 位）、`n_tasks`、`texts`＝去重後的非空描述（排除 `N/A`、`NA`、`-`、空白），依 FTE 由大到小。
- 取 FTE 前 `portfolio.ai_max_groups`（預設 5）群；其餘合成 `side="*"`、`function="Other"` 一群，不送 LLM。
- `input_hash`：`sha256` of JSON `[month, [(side, function, fte, n_tasks, texts) ...]]`（排序穩定）。

### 4.2 選哪些專案

`n_tasks（latest_month）≥ portfolio.ai_min_task_rows`（預設 100）。202609 快照 8 月份符合的是 Foxtrot14、Delta3-7、KILO12、D5K2、KILO10、D7K2。可用 CLI `--code` 指定額外專案（Pilot 的困難案例）。

### 4.3 Cambrian 客戶端（`cambrian.py`）

- `POST {base_url}/v1/chat/completions`，`Authorization: Bearer <token>`，`response_format={"type":"json_object"}`，`temperature=0`。
- `verify_ssl` 預設 False（Cambrian 為內網自簽憑證），可用環境變數打開。
- 逾時預設 120 秒；HTTP 非 200、回應不是合法 JSON、缺 `theme`/`summary` → `CambrianError`。
- 設定來源（CLI 讀環境變數，不進版控）：`EIS_CAMBRIAN_URL`（預設 `https://api.cambrian.pegatroncorp.com`）、`EIS_CAMBRIAN_TOKEN_FILE`（必填，檔案權限 600/640）、`EIS_CAMBRIAN_MODEL`（預設 `LLAMA 3.3 70B`）、`EIS_CAMBRIAN_VERIFY_SSL`（`1` 才驗證）。

### 4.4 `ai.json` 格式

```json
{
  "meta": {"report_month": "202609", "month": 8, "model": "LLAMA 3.3 70B", "prompt_version": "1",
           "max_groups": 5, "generated": "2026-10-02T09:00:00+08:00"},
  "projects": {
    "BR0000016203": {
      "status": "ok",                       // ok | failed
      "reason": "",                         // failed 時的原因（不含 token）
      "input_hash": "…",
      "groups": [
        {"side": "BU", "function": "ME", "fte": 3.8, "n_tasks": 3,
         "theme": "DVT-1 build issue 管理", "summary": "…", "grounded": true, "note": ""}
      ]
    }
  }
}
```

每個群組另有 `note`：`""`（正常）、`"ungrounded"`（未通過 grounding，`theme`/`summary` 清空，`grounded=false`）、`"no_text"`（該群沒有可用描述，不呼叫 LLM）、`"other"`（FTE 排名在 `max_groups` 之後合併的群，不呼叫 LLM）。`meta` 另記 `max_groups`，網頁重算 `input_hash` 時用同一個值。寫檔用 tmp＋`os.replace`，寫之前整份 JSON 過 `find_pii`，命中就不寫（CLI 回 exit 2）。

### 4.5 網頁

單案頁（`/ui/{month}/projects/{code}`）在「Milestones, plan vs actual, tasks」之前加兩個區塊：

1. **PM status · PM 狀態說明**：`p.status_text` 原文，`white-space: pre-wrap`、全文跳脫；標題註明「Briefing {snap_date}」。舊快照沒有這個欄位或為空字串時整塊不顯示。
2. **Work this month (AI) · 本月工作重點（AI）**：只有 `ai.json` 存在、該專案有紀錄、且 `meta.report_month` 等於本頁月份時才顯示。
   - 重算 `input_hash` 與紀錄不同 → 顯示「This summary is out of date; re-run the AI summary for {month}.」不顯示內容。
   - `status=failed` → 顯示原因一句。
   - 正常 → 表格：Theme／Summary／Side·Function／FTE／Tasks；`grounded=false` 的列 Theme 與 Summary 欄顯示「Did not pass the check; read the tasks below」。
   - 區塊下方一行：「AI summary by {model}. FTE and task counts are computed from the Control List; the model only names each group.」中英並列。

`/ui/` 首頁、總覽、月報**不變**。

## 5. 錯誤處理

| 情況 | 行為 |
|---|---|
| token 檔不存在或空白 | CLI exit 2，訊息指出 `EIS_CAMBRIAN_TOKEN_FILE`；不寫 ai.json |
| 月份沒有快照 | CLI exit 1 |
| 單一群組呼叫失敗（逾時、非 JSON、缺欄位） | 該專案 `status=failed`、`reason` 記錯誤類別；其他專案繼續 |
| 全部專案都失敗 | 仍寫 ai.json（紀錄失敗），CLI exit 3 |
| LLM 輸出含原文沒有的數字詞 | 該群 `grounded=false`，文字清空 |
| ai.json 讀不出來（壞 JSON） | 網頁視同沒有 AI 結果，並在區塊顯示「AI summary file is unreadable」 |
| ai.json 輸出命中 PII | 不寫檔，CLI exit 2 |

## 6. 不做（本輪）

- MCP `get_project` 回傳 AI 結果（等 Pilot Go 再加）。
- 月報 HTML 的狀態說明與 AI 摘要。
- 狀態說明本身的 LLM 摘要（文字短，不需要）。
- 自動在 ingest 後觸發（Pilot 期間由報表維護者手動執行，避免在 PM 寫完 golden 前就公開摘要）。
- 取消 task 描述的人名遮罩、顯示原始檔名（需求方已允許人名，但範圍另議）。

## 7. 對既有設計的修訂

「server 端不含 LLM」目前寫在兩份操作文件，改為「核心快照（`portfolio.json`）與所有 MCP tool 回傳不含 LLM 產出；選用的 AI 摘要另存 `ai.json`，由獨立指令產生，不設定就不會有」：
- `docs/eis-mcp-client-setup.md` 第 11 行。
- `docs/eis-mcp-install.md` 第 12 行，並新增一節「AI 工作重點（選用）」：token 檔位置、執行指令、exit code。
- `README.md` §7 新增 7.9 同義的一段；`AGENTS.md` MCP server 段落補一行。

## 8. 測試

- `groups`：分群、排序、Other 合併、N/A 過濾、雜湊穩定且對內容變動敏感。
- `grounding`：數字詞擷取；原文有的通過、沒有的拒絕；不含數字的輸出一律通過。
- `cambrian`：用 `httpx.MockTransport` 驗證請求格式、Bearer、JSON mode；非 200、非 JSON、缺欄位都丟 `CambrianError`。
- `enrich`：假客戶端；選案門檻、失敗隔離、grounding 清空、快取命中不呼叫、PII 命中不寫檔。
- CLI：token 檔缺 → exit 2；全部失敗 → exit 3。
- 網頁：狀態說明顯示且跳脫；AI 區塊正常、過期、失敗、grounded=false 四種顯示；沒有 ai.json 時不顯示；狀態說明欄缺（舊快照）不顯示。
