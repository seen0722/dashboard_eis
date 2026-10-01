# BU10 Portfolio Review — 設計文件

日期：2026-09-12
狀態：草稿，待使用者審閱
取代：無（與 `src/build_review.py` 舊月報管線並存，互不影響）
Mock 依據：`out/mock_bu10_portfolio_v3.html`（拋棄式，實作完成後刪除）

## 1. 目標與受眾

- **受眾**：BU10 事業處主管一人。每月一次的專案組合檢討會議用。
- **主要工作**：讓主管在第一屏就看到「這個月要決定的事」，每條附證據與出處；其餘章節是證據的展開。
- **語言**：英文為預設輸出。字串集中管理，中文為可選第二語言。
- **交付形式**：每月一份自包含的單頁 HTML（inline CSS/SVG/JS，零外部依賴），可寄送、可放內網。不做伺服器、不做登入。

## 2. 輸入資料

每月一包目錄（例如 `input-09/`），內容與 `input-08/` 相同結構：

| 檔案 | 用途 | 更新節奏 |
|---|---|---|
| `Project List-YYYYMM.xlsx` | PROJECTCODE 主檔：code、name、group、產品別、生效 | 每月 |
| `BU10_Project_Briefing_YYYYMMDD.xlsx` | Stage、EVT/DVT/PVT/MP 日期、Original MP、Customer、Product、Project Code、狀態文字。**一個檔案內含所有雙週快照分頁**（`YYYYMMDD` 命名） | 每兩週更新，每月取最新一份 |
| `2026 EIS Resource Summary.xlsx` | 每案逐月 Total EIS 人力與 NTD | 每月 |
| `2026  EIS Resource Control List-<PROJECT> (<PM>).xlsx` × N | 每案：`Plan vs. Acutal`（FU RD / BU RD / PM 三組 budget 與實際）、`BU-Task` / `FU-Task`（任務列）、月分頁 `1`..`12`（部門 × 專案人力、`單位TotalKeyIn人數`）、`實名制`、`人力`（**含姓名工號，不讀**） | 每月 |

已知例外：`CPL22B` 為 `.xlsb`，需 `pyxlsb` 讀取；檔名 `RFQ_OTHERS(...)` 沒有空格；`~$` 鎖檔要略過。

## 3. 資料模型

### 3.1 主鍵

- **PROJECTCODE（`BR0000xxxxxx`）為唯一主鍵。** Project List 是主檔；Briefing 有 `Project Code` 欄；Control List 的任務列與月分頁都有 `PROJECTCODE`。
- 名稱只在代碼缺漏時當備援：正規化（大寫、去空白底線連字號）後比對，再查 `config/aliases.yaml` 的人工對照表。對不上的列入健康度「需 alias」項，不靜默丟棄。
- 一個 Control List 檔可能對應多個 code（例如 `AF900/AF903/...`）：以檔內 `Project List` 分頁與任務列的 code 為準，不用檔名。

### 3.2 正規化實體

```
Project        code, name, group, family, customer, product, stage, stage_cat,
               dates{kickoff, evt, dvt, pvt, mp, mp_orig}, in_briefing, in_control_list
BriefingSnap   snap_date, code, stage, dates, status_text        # 每個雙週分頁一筆
MonthlyFTE     code, yyyymm, total_fte, total_ntd                 # Resource Summary
PlanVsActual   code, role(FU RD|BU RD|PM), yyyymm, plan, actual, ntd
Task           code, yyyymm, side(BU|FU), function, dept_short, fte, description_masked
DeptLoad       dept_code, dept_short, function, yyyymm, keyed_in_headcount, allocated_fte
Health         check_id, level(decide|track|ok), count, codes[], source
Exception      rank, title, evidence, decision_ask, source, codes[]
```

### 3.2a 「最新月」定義

Resource Summary 中最後一個 Total EIS 人力非零的月份（input-08 為 2026-08）。所有「latest month」的數字都以它為準，與 Briefing 快照日期無關。

### 3.3 Stage 分類（`stage_cat`）

依 Briefing Stage 文字，順序判斷：Terminated（terminat / discontinu / cancel）→ Suspended（suspend / hold）→ RFQ/RFI → POC → Execution（EVT / DVT / PVT / EIV）→ MP → Sustain/EOP → Other。規則放 `config/stages.yaml`，可調。2026-10 起把結案（Terminated，掛帳人力該撤）與暫停（Suspended，掛帳可能刻意保留）分開；程式以 `entities.INACTIVE` 同時涵蓋兩者。

### 3.4 部門負載

`load% = Σ(各專案 主管填入人力) ÷ 單位TotalKeyIn人數`，同部門同月份的分母在所有 Control List 內一致（已驗證 422 組零不一致）。分母是「有填報的人數」不是編制，報告要註明。

## 4. 規則

### 4.1 例外（Decisions this month）

由規則產生、依急迫排序、每條輸出 title / evidence / decision ask / source。第一版規則：

1. **Milestone passed, stage not advanced**：MP 已過且 stage_cat ∉ {MP, Sustain/EOP}；或 PVT 已過且 stage 含 EVT/DVT/POC。依過期天數排序。
2. **Suspended projects still charging**：stage_cat ∈ INACTIVE（Terminated 或 Suspended）且最新月 total_fte > 0.05；標題分別列出 terminated / suspended 數。
3. **Budget missing**：Control List 三組 plan 全為 0。附預測涵蓋率。
4. **MP slipped > 60 days vs Original MP**；相差 > 300 天另標「疑為輸入錯誤」。
5. **Departments with spare capacity**：最新月 load% < 85%。附「其餘 N 個部門已達上限」。

規則的門檻（60 天、300 天、85%、0.05）放 `config/thresholds.yaml`。每條例外的 codes[] 用來在時程表與附錄標橘色。

### 4.2 健康度檢查

| level | 檢查 | 來源 |
|---|---|---|
| decide | Budget plan 未填 | Control List |
| decide | 里程碑已過但 Stage 未推進 | Briefing |
| track | 在 Briefing（非停案）但沒有 Control List | 對照 |
| track | 有 Control List 但不在 Briefing | 對照 |
| track | MP 與 Original 相差 > 300 天 | Briefing |
| track | Customer 為 NA / TBD / 空白 | Briefing |
| track | 名稱需 alias 才對得上 | 三來源 |
| track | BU-Task 有人力列但 Task Description 空白 | Control List |
| track | Briefing `資料更新日` 距快照 > 60 天 | Briefing |
| track | 無法讀取的檔案、格式漂移（缺分頁、缺欄） | Control List |
| track | **跨月修正**：本月快照對「過去月份」的數字與上月快照不同（例如 THORPE FU 更正） | 兩個月的 snapshot JSON |

### 4.3 人名遮罩

任務文字由 PM 填寫，偶爾夾帶姓名。遮罩規則：`英文名(中文名)`、`英文名_英文姓`（需同時含母音且非全大寫產品代號）、`英文名+四位數日期`。被遮罩的筆數列入健康度。**不讀 `人力` 與 `實名制` 分頁。** 輸出檔不含任何工號或姓名，不需 `_internal` 後綴。

## 5. 頁面結構（v3 骨架，英文文案）

單頁、單欄、左對齊、最大寬 1280，章節順序即會議順序：

1. **Header + title block**：左為 `BU10 Portfolio Review` 與一句用途說明；右上角標題欄四列：Report month / Manpower data (range, N projects) / Briefing snapshot (date, revision) / Generated (date, pipeline version)。
2. **Decisions this month**：有序清單，橘色序號；每條 title（粗）、evidence、`Decision needed:` 一句、`Source:` 一句。
3. **Stage strip**：一列數字 RFQ/RFI、POC、Execution、MP、Sustain/EOP、Terminated（橘）、Suspended（橘）、Total FTE latest month（含 FU，來源 Resource Summary，標籤註明 `incl. FU`）。
4. **Milestones, next 8 weeks**（左，含過去 7 天）與 **Six-month timeline**（右）：週格線，月份標籤 `2026-09`；標記 □ EVT ■ DVT ▲ PVT ● MP；過期未推進為橘；停案不列；RFQ/RFI 無日期者顯示 `RFQ, no dates yet`。
5. **Manpower and capacity**：一張圖，Jan–Dec：BU keyed-in headcount（天花板，黑虛線）、BU RD + PM actual（板岩實線）、BU RD + PM budget（板岩虛線）、FU RD actual（鋼青）。9–12 月區域灰底並標 `Budget covers N / M projects`。
6. **Data health**：表格，欄位 Level / Check / Count / Projects / Source；decide 級的數字為橘。
7. **Project appendix**：下拉選案；五格里程碑（含距今天數）；三組 plan vs actual 小圖；**Task list** 按月 `<details>` 收合，預設收合，summary 為 `Aug: 15 BU tasks, 55 FU tasks, 12.4 FTE`。
8. **Footer**：資料限制三句（FTE 上限 1.0、分母為填報人數、budget 涵蓋率）。

不做：側欄、卡片、圓餅、動畫（僅 `<details>` 展開）、全大寫小標、中點串接。

## 6. 視覺系統

| token | 值 | 用途 |
|---|---|---|
| paper | `#F5F6F4` | 背景 |
| ink | `#22262A` | 文字、天花板線 |
| ink-2 / ink-3 | `#5B6167` / `#9AA3AB` | 次要文字、來源 |
| rule | `#D5D9D6` | 分隔線 |
| slate / slate-2 | `#3D5A80` / `#A9B8CC` | BU 人力實際 / budget |
| teal | `#5C8D89` | FU |
| signal | `#E8590C` | **只用於**例外序號、決定級數字、過期里程碑、Suspended |

字體：系統無襯線單一家族（`-apple-system, "Segoe UI", "PingFang TC", "Microsoft JhengHei"`），等寬數字。字級：h1 28/600、h2 20/600、內文 14、註記 12。

## 7. 管線架構

```
src/portfolio/
  cli.py            # python -m src.portfolio.cli --input input-09 --month 202609 [--lang en|zh]
  extract/
    project_list.py, briefing.py, resource_summary.py, control_list.py  # 每種檔案一模組
    xlsb.py         # pyxlsb 薄包裝
  model/
    normalize.py    # 合併為 §3.2 實體，主鍵解析、alias
    rules.py        # §4.1 例外、§4.2 健康度
    load.py         # 部門負載
    diff.py         # 與上月 snapshot JSON 比對
  render/
    page.py         # 組頁
    charts.py       # SVG：timeline、capacity、plan-vs-actual
    strings.py      # en / zh 字串表（沿用 src/i18n.py 模式）
    css.py
tests/portfolio/    # 見 §9
config/
  stages.yaml, thresholds.yaml, aliases.yaml（沿用既有檔）
```

- **輸出**：`data/snapshots/YYYYMM/portfolio.json`（正規化實體，含遮罩後任務文字，gitignored）與 `out/portfolio_YYYYMM_en.html`。
- **跨月**：`diff.py` 讀上月 JSON，產生「跨月修正」健康度項與（第二版）決定回顧。
- **不動** `src/build_review.py` 與其 i18n；新字串表獨立檔，避免舊表膨脹。
- 每個 extract 模組回傳 `(records, issues)`，issues 直接進健康度，不拋例外中斷；只有主檔讀不到才失敗。

## 8. 錯誤處理與驗證

- 每份 Control List 檢查必要分頁與欄位；缺者記 issue、跳過該檔、繼續。
- Briefing 分頁名不符 `YYYYMMDD` 者略過並記錄；沒有任何合法分頁則失敗。
- 日期欄接受 `M/D/YYYY`、`YYYY-MM-DD`、datetime；`NA`/`TBD`/空白視為無日期；其他格式記 issue。
- 產出前的斷言：例外 codes[] 都能在 Project 表找到；健康度 count 與 codes[] 長度一致；HTML 內不得出現工號樣式 `LA\d{7}` 與 `人力` 分頁中的任何姓名（用抽出的姓名集合做負向檢查）。

## 9. 測試

- **extract**：以合成的小型 xlsx fixture（每種格式一份，含刻意的格式漂移與 `.xlsb`）跑 pytest。
- **model**：規則以表驅動測試（每條例外與健康度至少一正一負案例）；alias 與代碼解析；遮罩規則含「不得遮 `THORPE_MB`」的反例。
- **render**：以 `data/snapshots/` fixture JSON 產 HTML，snapshot test；headless Chrome 截圖 1280 與 1024 寬做視覺回歸；檢查頁面無橫向捲動。
- **PII 負向測試**：對真實資料跑一次，斷言輸出不含姓名工號（本地執行，不進 CI）。

## 10. 第一版不做

- 中文版輸出（字串表預留，不產檔）。
- 成本視圖（NTD）、跨月決定回顧、實名個人視角。
- 部署到 VPS、多頁站、任何伺服器端。
- 部門 × 月熱圖（資料已能算，留第二版）。

## 11. 已確認的決定（2026-09-12）

- 「Suspended 仍掛人力」門檻採 0.05 FTE。
- 例外第五條（可調度部門）保留在給主管的版本。
- NTD 成本允許出現在主管報告；第一版不做，第二版加成本視圖。
