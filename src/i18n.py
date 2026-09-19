"""介面字串。新增語言只需加一個 dict。

原則：只放事實性標籤與方法說明，不放評論或立場。
"""

MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

STRINGS = {
    "zh": {
        "html_lang": "zh-Hant",
        "kicker": "BU10 · 第十事業處 · 人力執行",
        "title": "{ym} 實際 vs 計畫",
        "doc_title": "BU10 人力執行 {ym}",
        "source": "資料源",
        "month": lambda m: f"{m}月",
        "ym": lambda y, m: f"{y}/{m:02d}",

        "hc_h": "編制 vs 計畫編列",
        "hc_src": "來源 <code>2026_plan.xlsx</code> → <code>人力分攤-updated</code> 列 129 / 130 / 131"
                  "　·　編制 {est:.0f} 人（列 129）　·　計畫編列 = BU RD + BU PM（列 130）",
        "hc_ref": "編制 {est:.0f}",
        "k_est": "編制", "k_planned": "{ym} 計畫編列", "k_gap": "{ym} 不足/超出",
        "k_first_neg": "首度轉負", "k_worst": "全年最大缺口",
        "u_people": "人", "u_fte": "FTE", "u_projects": "個",

        "over_h": "實際人力超過計畫的專案",
        "over_src": "plan &gt; 0 且 actual &gt; plan，依絕對超出量排序　·　單位：FTE（人月當量）",
        "lg_plan": "▬ plan", "lg_act": "▬ actual", "lg_ex": "▬ 超出部分", "lg_axis": "超出 FTE",
        "k_count": "專案數", "k_plan_tot": "plan 合計", "k_act_tot": "actual 合計", "k_ex_tot": "超出合計",
        "by_project": "逐專案明細",
        "depts": "人力來自哪些單位",
        "with_names_hint": "含成員（BU RD／PM）",
        "pii_warn": "⚠ 含個人資料（員工姓名／工號）· 限內部使用 · 請勿轉寄或公開",
        "dept_rest": "其餘 {n} 個部門",
        "skipped": "超出低於 {t} FTE 未列入圖表：{items}",

        "zero_h": "計畫為 0、實際有人力的專案",
        "zero_src": "單位：FTE　·　<code>人力分攤-updated</code> 無 <code>PROJECTCODE</code> 欄，"
                    "plan 與 actual 以專案名稱比對",
        "zeroed_h": "plan 有此列但已編為 0",
        "unplanned_h": "plan 無此專案",
        "unplanned_detail_h": "非計畫內專案 · 逐案明細",
        "unplanned_detail_src": "「非計畫內」＝ plan 分頁查無此案 —— 可能是計畫後才啟動，"
                                "或名稱未對上別名（見附註）。以下列出實際投入的部門與人力，"
                                "供判斷該補計畫、或該收斂。",
        "u_depts": "個部門",
        "roles_line": "BU RD {rd} · BU PM {pm} · FU RD {fu}　FTE",
        "total": "合計 {v} FTE",
        "total_pending": "合計 {v} FTE　·　含 {n} 條名稱待確認（見附註）",

        "rail_y": "2026",
        "rail_note": "{n} 個月可用",
        "trend_h": "各月變化",
        "trend_src": "超出 FTE 的逐月變化（plan − actual，僅列任一月曾超配的專案）　·　"
                     "各月資料皆取自該月自己的檔案",
        "lg_up": "增加", "lg_down": "減少",
        "totals_h": "每月超出合計",
        "totals_src": "長條下方數字為當月超配專案數",
        "mover_up": "增加最多", "mover_down": "減少最多",

        # 部門碎片化頁（--dept；逐人、含個資）
        "d_kicker": "BU10 · 部門碎片化",
        "d_title": "人力碎片化檢視",
        "d_doc_title": "BU10 部門碎片化 {ym}",
        "d_src": "focus = Σ(每案佔比²)：1.00 ＝ 全心單一案，越低越分散。"
                 "當某人 focus 低於其職能門檻（深度職能 0.70／廣度職能 0.30）"
                 "且非微量專案數 ≥ 3，標為偏碎片。僅 D 組（人力明細）逐人資料、僅 BU10。",
        "d_k_depts": "部門", "d_k_people": "人數", "d_k_flagged": "偏碎片", "d_k_fte": "總 FTE",
        "d_flagged_badge": "偏碎片",
        "d_focus": "專注度",
        "d_breadth": "廣度職能",
        "d_none": "此部門無偏碎片人員",
        "d_more": "其餘 {n} 人（專責，未標記）",
        "d_pick": "選擇部門",
        "d_all": "── 顯示全部部門 ──",
        "d_opt": "{name}　·　{f} 偏碎片 / {p} 人",

        # 單一專案專頁（--project）
        "pj_kicker": "BU10 · 逐專案檢視",
        "pj_title": "逐專案 · plan vs 實際",
        "pj_doc_title": "BU10 逐專案檢視 {ym}",
        "pj_src": "選一個專案，看它 {n} 個月的 plan（計畫編列）與 actual（實際投入）逐月對照。"
                  "各月資料皆取自該月自己的檔案。",
        "pj_pick": "選擇專案",
        "pj_opt": "{name}　·　最新 {a} FTE",
        "pj_lg_plan": "plan 計畫", "pj_lg_act": "actual 實際",
        "pj_k_latest": "最新 actual · {ym}", "pj_k_latplan": "最新 plan",
        "pj_k_gap": "差距 · {ym}", "pj_k_peak": "actual 高峰", "pj_k_avg": "actual 月均",
        "pj_none": "此專案無資料",

        "method_h": "計算方式",
        "notes_h": "附註",
        "m1": "<b>actual</b> ＝ <code>{ym}-人力明細</code>（逐人填報）＋ <code>{ym}-ProjectCode人力</code>"
              " 的 Y 組（百分比分攤）。兩者部門族群不重疊。",
        "m2": "<b>角色</b>：<code>FU RD</code> ＝ 部門所屬組織 ≠ 專案所屬 BU（非本 BU 的支援，含其他 BU）；"
              "<code>BU PM</code> 依 <code>EIS_FUNCTION</code> 判定；其餘為 <code>BU RD</code>。"
              "此規則與 <code>Project {p} vs.{c}</code> 分頁逐筆一致（19/19，誤差 0）。",
        "m3": "<b>plan</b> 取 <code>人力分攤-updated</code>（與 <code>人力樞紐</code>、"
              "<code>25 vs. 26 人力</code> 一致）。",
        "m4": "<b>已排除</b>：製造單位（部門代碼 H 開頭，{mfg} FTE）、RFQ 報價階段專案（不編 plan）、"
              "plan 的產品別小計列與編制檢核列。",
        "n1": "<code>人力分攤-updated</code> 無 <code>PROJECTCODE</code> 欄，plan 與 actual 以專案名稱比對。"
              "已建立名稱對照 {n} 條；另有 {c} 條待確認（{cands}），尚未套用。",
        "n2": "本表為 {ym} 單月。跨月比較須各取當月檔案。",
    },
    "en": {
        "html_lang": "en",
        # ⚠ 只用資料裡真實存在的識別碼。BU10 是 EIS 的實際欄位值；
        #   「第十事業處」在資料中沒有官方英文名 —— 不可自行翻譯成 "Division 10"，
        #   那是編出來的，而錯誤的組織名在公開文件上只有內部人看得出來。
        "kicker": "BU10 · Manpower Execution",
        "title": "Actual vs. Plan",
        "doc_title": "BU10 Manpower Execution — {ym}",
        "source": "Source",
        "month": lambda m: MONTHS_EN[m - 1],
        "ym": lambda y, m: f"{MONTHS_EN[m-1]} {y}",

        "hc_h": "Headcount vs. Planned Allocation",
        "hc_src": "<code>2026_plan.xlsx</code> → <code>人力分攤-updated</code>, rows 129 / 130 / 131"
                  "　·　Headcount {est:.0f} (row 129)　·　Planned = BU RD + BU PM (row 130)",
        "hc_ref": "Headcount {est:.0f}",
        "k_est": "Headcount", "k_planned": "Planned · {ym}", "k_gap": "Gap · {ym}",
        "k_first_neg": "First deficit", "k_worst": "Largest gap",
        "u_people": "", "u_fte": "FTE", "u_projects": "",

        "over_h": "Projects Over Plan",
        "over_src": "plan &gt; 0 and actual &gt; plan, ranked by absolute excess　·　FTE (full-time equivalent)",
        "lg_plan": "▬ plan", "lg_act": "▬ actual", "lg_ex": "▬ excess", "lg_axis": "Excess FTE",
        "k_count": "Projects", "k_plan_tot": "Plan total", "k_act_tot": "Actual total", "k_ex_tot": "Total excess",
        "by_project": "Project detail",
        "depts": "Contributing departments",
        "with_names_hint": "with members (BU RD/PM)",
        "pii_warn": "⚠ Contains personal data (names / employee IDs) · Internal use only · Do not forward or publish",
        "dept_rest": "{n} other departments",
        "skipped": "Excess below {t} FTE, not charted: {items}",

        "zero_h": "Projects with No Plan but Actual Manpower",
        "zero_src": "FTE　·　<code>人力分攤-updated</code> has no <code>PROJECTCODE</code> column; "
                    "plan and actual are matched by project name",
        "zeroed_h": "In plan, allocated 0",
        "unplanned_h": "Not in plan",
        "unplanned_detail_h": "Not in Plan — Project Detail",
        "unplanned_detail_src": "\"Not in plan\" = the project is absent from the plan sheet — it may have "
                                "started after planning, or a name did not match an alias (see notes). "
                                "The departments and people actually staffed are listed below, to judge "
                                "whether to add it to the plan or wind it down.",
        "u_depts": "depts",
        "roles_line": "BU RD {rd} · BU PM {pm} · FU RD {fu}　FTE",
        "total": "Total {v} FTE",
        "total_pending": "Total {v} FTE　·　includes {n} names pending confirmation (see notes)",

        "rail_y": "2026",
        "rail_note": "{n} months available",
        "trend_h": "Month-over-Month",
        "trend_src": "Excess FTE (actual − plan) by month, for projects over plan in any month　·　"
                     "each month is read from its own file",
        "lg_up": "increasing", "lg_down": "decreasing",
        "totals_h": "Total excess by month",
        "totals_src": "The figure under each bar is that month's over-plan project count",
        "mover_up": "Largest increase", "mover_down": "Largest decrease",

        # Department fragmentation page (--dept; per-person, contains personal data)
        "d_kicker": "BU10 · Fragmentation",
        "d_title": "Manpower Fragmentation",
        "d_doc_title": "BU10 Fragmentation — {ym}",
        "d_src": "Focus = Σ(share²): 1.00 means fully on a single project, lower means more scattered. "
                 "A person is flagged when focus falls below the threshold for their function "
                 "(deep roles 0.70, breadth roles 0.30) across at least 3 non-trivial projects. "
                 "Per-person data comes from the D group (人力明細) only, BU10 only.",
        "d_k_depts": "Departments", "d_k_people": "People", "d_k_flagged": "Spread thin", "d_k_fte": "Total FTE",
        "d_flagged_badge": "spread thin",
        "d_focus": "focus",
        "d_breadth": "breadth role",
        "d_none": "No one flagged in this department",
        "d_more": "{n} more (focused, not flagged)",
        "d_pick": "Department",
        "d_all": "── Show all departments ──",
        "d_opt": "{name}　·　{f} spread thin / {p} people",

        # Single-project view (--project)
        "pj_kicker": "BU10 · By Project",
        "pj_title": "By Project · Plan vs. Actual",
        "pj_doc_title": "BU10 By Project — {ym}",
        "pj_src": "Pick a project to see its planned allocation vs. actual staffing across {n} months. "
                  "Each month is read from its own file.",
        "pj_pick": "Project",
        "pj_opt": "{name}　·　latest {a} FTE",
        "pj_lg_plan": "plan", "pj_lg_act": "actual",
        "pj_k_latest": "Actual · {ym}", "pj_k_latplan": "Plan (latest)",
        "pj_k_gap": "Gap · {ym}", "pj_k_peak": "Actual peak", "pj_k_avg": "Actual avg/mo",
        "pj_none": "No data for this project",

        "method_h": "Method",
        "notes_h": "Notes",
        "m1": "<b>Actual</b> = <code>{ym}-人力明細</code> (per-person reporting) + the Y group of "
              "<code>{ym}-ProjectCode人力</code> (percentage allocation). The two department "
              "populations do not overlap.",
        "m2": "<b>Roles</b>: <code>FU RD</code> = department's own organisation ≠ the project's BU "
              "(support from outside the owning BU, including other BUs); <code>BU PM</code> is "
              "determined by <code>EIS_FUNCTION</code>; everything else is <code>BU RD</code>. "
              "This rule reproduces the <code>Project {p} vs.{c}</code> sheet exactly (19/19, zero variance).",
        "m3": "<b>Plan</b> is taken from <code>人力分攤-updated</code> (consistent with <code>人力樞紐</code> "
              "and <code>25 vs. 26 人力</code>).",
        "m4": "<b>Excluded</b>: manufacturing departments (code prefix H, {mfg} FTE), RFQ-stage projects "
              "(not planned), and the plan's product-subtotal and headcount-check rows.",
        "n1": "<code>人力分攤-updated</code> has no <code>PROJECTCODE</code> column, so plan and actual are "
              "matched by project name. {n} name mappings are established; {c} more are pending "
              "confirmation ({cands}) and are not applied.",
        "n2": "This report covers {ym} only. Cross-month comparison requires each month's own file.",
    },
}


def strings(lang):
    if lang not in STRINGS:
        raise KeyError(f"未支援的語言 {lang}；可用：{list(STRINGS)}")
    return STRINGS[lang]
