import re
import pytest
from dataclasses import asdict
from src.portfolio.entities import Project, PlanVsActual, Task, Exception_, HealthRow, Issue
from src.portfolio.model.load import DeptLoad
from src.portfolio.model.snapshot import build_snapshot
from src.portfolio.render.page import render_page
from src.portfolio.render.pii import find_pii

TH = {"mp_slip_days": 60, "spare_capacity_pct": 85, "suspended_fte_min": 0.05, "briefing_stale_days": 60, "upcoming_weeks": 8, "timeline_months": 6}


def snap():
    a = Project(code="BR1", name="THORPE", stage="PVT", stage_cat="Execution", customer="Trimble", product='Tablet 10"', biz_type="ODM",
                category="Tablet", panel_size='10"', in_briefing=True, in_control_list=True, has_plan=True)
    a.dates.update({"kickoff": "2024-04-02", "dvt": "2026-09-08", "pvt": "2026-03-21", "mp": "2026-07-31", "mp_orig": "2025-10-13"}); a.fte[7] = 12.4
    a.pva = {"BU RD": PlanVsActual("BU RD", plan=[14.5] * 12, actual=[18] * 8 + [0] * 4)}
    a.tasks = [Task(8, "BU", "BSP", "研發三部", 3.1, "SW release"), Task(8, "FU", "SQA", "軟體三處", 0.6, "SQA")]
    b = Project(code="BR2", name="TOMY", stage="RFQ", stage_cat="RFQ / RFI", customer="Trimble", in_briefing=True)
    c = Project(code="BR3", name="Q11", stage="suspended", stage_cat="Suspended", customer="TBD", in_briefing=True)
    c.dates.update({"evt": "2026-09-10"})
    d = Project(code="BR4", name="AX200", stage="MP", stage_cat="MP", customer="Axelera", in_briefing=True)
    d.dates.update({"pvt": "2026-09-08"})
    e = Project(code="BR5", name="KOS", stage="Terminate", stage_cat="Terminated", customer="TBD", in_briefing=True)
    f = Project(code="TR_KOS", name="TR_BU10_IPC_KOS", in_control_list=True)
    f.fte[7] = 0.49   # same project as KOS, booked under a second (non-briefing) code
    twin = {"name": "KOS", "code": "BR5", "cat": "Terminated", "twin": "TR_BU10_IPC_KOS", "twin_code": "TR_KOS", "twin_fte": 0.49, "twin_in_cl": True}
    ex = [Exception_(1, "milestones_passed", "THORPE MP 2026-07-31 (+43d, stage PVT)", "milestones_passed", "briefing", ["BR1"], count=1),
          Exception_(2, "suspended_charging", "", "suspended_charging", "briefing_summary", ["TR_KOS"], count=1,
                     extra={"pct": 20, "briefed": 5, "charging": 0, "twins": 1, "terminated": 1, "suspended": 1, "charging_list": [],
                            "wound_list": [{"name": "Q11", "code": "BR3", "cat": "Suspended", "peak": 12.2, "peak_month": "May", "zero_since": "Jul"},
                                           {"name": "Sabre", "code": "BRS", "cat": "Terminated", "peak": 5.4, "peak_month": "Jun", "zero_since": "Jul"}],
                            "zero_list": [{"name": "KOS", "code": "BR5", "cat": "Terminated"}], "twin_list": [twin]}),
          Exception_(3, "budget_missing", "", "budget_missing", "control_list_pva", [], count=0, extra={"covered": 1, "total": 1}),
          Exception_(4, "mp_slipped", "THORPE 2025-10-13 -> 2026-07-31 (291d)", "mp_slipped", "briefing_mp", ["BR1"], count=1),
          Exception_(5, "spare_capacity", "", "spare_capacity", "control_list_month", [], count=0, ask_data="2")]
    hl = [HealthRow("decide", "budget_missing", "budget_missing", 0, [], "control_list"), HealthRow("ok", "names_masked", "names_masked", 3, [], "control_list")]
    return build_snapshot("202609", 8, "20260907", "2026-09-12", [a, b, c, d, e, f], [DeptLoad("D", "x", "BSP", keyed_in=[5] * 12, util=[100] * 12)], [207] * 12, ex, hl, [])


def test_page_sections_and_strings():
    html = render_page(snap(), "en", "2026-09-12", TH)
    for s in ("BU10 Portfolio Review", "Decisions this month", "1 milestones passed", "Decision needed:", "Milestones, next 8 weeks",
              "Timeline, next 6 months", "Forecast vs capacity", "Data health", "Project appendix", "Aug: 1 BU tasks, 1 FU tasks, 3.7 FTE",
              "Headcount, assumed same as Aug"):
        assert s in html, s
    assert "TOMY" in html and "no dates yet" in html
    assert html.count("<details><summary") == 1 and "<details open" not in html
    assert "·" not in html.replace(re.search(r"<script>\s*/\*.*?</script>", html, re.S).group(0), "") and "→" not in html
    assert 'lang="en"' in html
    gantt = re.search(r'id="c-gantt-data">(.*?)</script>', html).group(1)
    assert "Q11" not in gantt and "KOS" not in gantt                     # inactive projects are kept out of the timeline
    assert '<span class="pill bad">Passed</span>' in html                 # THORPE DVT 09/08, in milestones_passed
    assert '<span class="pill mute">Passed</span>' in html                # AX200 PVT 09/08, stage moved on
    assert "Second identity, likely the same project under another code" in html
    assert "1 suspended of 5 briefed, 0 still charging manpower, 1 booked under a second code" in html
    assert "terminated and" not in html                                            # terminated total lives in the stage strip only
    assert "KOS (BR5) is terminated in the briefing" in html                       # twin line uses the real category
    assert "Suspended but no manpower since Jul" in html and "Q11: peak 12.2 FTE in May" in html   # suspended wound = question
    assert "Terminated and closed out" not in html and "Sabre" not in html         # terminated + zero manpower is normal: not shown
    assert "No manpower all year" not in html                                      # all-zero list dropped (only suspended ones matter)
    assert "Terminated projects should carry no manpower" in html                 # ask
    assert "Briefing stage column; Resource Summary; Control List" in html         # source
    assert "% of the portfolio" not in html
    assert re.search(r'<div class="sig">[^<]*TR_BU10_IPC_KOS[^<]*</div>', html)


def test_render_refuses_a_snapshot_with_no_manpower_month():
    s = snap(); s["meta"]["latest_month"] = 0
    with pytest.raises(ValueError, match="no manpower month"):
        render_page(s, "en", "2026-09-12", TH)


def test_zh_renders_without_missing_keys():
    html = render_page(snap(), "zh", "2026-09-12", TH)
    assert "本月要決定的事" in html and 'lang="zh-Hant"' in html


def test_find_pii():
    assert find_pii("ok LA0801557 x") == ["LA0801557"]
    assert find_pii("Jiayu Ong(翁家瑜)") == ["Jiayu Ong(翁家瑜)"]
    assert find_pii("BILLY_CHEN(陳澤明)") == ["BILLY_CHEN(陳澤明)"]
    assert find_pii("Billy(陳澤明)") == ["Billy(陳澤明)"]
    assert find_pii("CRICKET(維護單價) and THORPE(維護)") == []
    assert find_pii("nothing here", {"SECRET"}) == []
    assert find_pii("by SECRET person", {"SECRET"}) == ["SECRET"]


def test_appendix_meta_shows_biz_type_only_when_present():
    """新版 Briefing 的 Type（JDM/ODM/EMS）顯示在附錄卡片的 meta 列；舊版面沒有時不留空隙。product 已含 Category+Panel，不重複列。"""
    html = render_page(snap(), "en", "2026-09-12", TH)
    assert "BR1  Trimble  ODM  Tablet 10&quot;" in html or 'BR1  Trimble  ODM  Tablet 10"' in html
    assert "BR2  Trimble" in html and "BR2  Trimble  " not in html.split("BR2  Trimble")[1][:2]


def test_appendix_is_sorted_by_project_name_case_insensitively():
    """附錄的下拉選單與卡片都依專案名稱字母排序（不分大小寫），不再依 FTE 或 stage 分群。"""
    import re
    html = render_page(snap(), "en", "2026-09-12", TH)
    names = re.findall(r'<option value="\d+">([^<,]+)', html.split('id="pick"')[1].split("</select>")[0])
    assert names == sorted(names, key=str.casefold)
    assert names[:3] == ["AX200", "KOS", "Q11"]


def test_kpis_count_stages_and_at_risk():
    html = render_page(snap(), "en", "2026-09-12", TH)
    kp = html[html.index('<div class="kpis">'):html.index('<div class="grid-2">')]
    assert '<span class="k-label">Total projects</span><b class="k-value">6</b><span class="k-sub">5 in Briefing, 2 terminated or suspended</span>' in kp
    assert '<a class="kpi bad" href="#decisions"><span class="k-label">At risk</span><b class="k-value">1</b>' in kp    # BR1：passed 且 MP 延後 291 天


def test_exception_two_shows_terminated_only_when_still_charging_and_suspended_zero_rows():
    """Terminated 案只在仍掛帳時出現（Still charging 段）；Suspended 案即使全年無人力也列出（暫停卻沒人是要問的）。"""
    sn = snap()
    ex2 = sn["exceptions"][1]
    ex2["extra"].update({"charging": 1, "charging_list": [{"name": "ZOMBIE", "code": "BRZ", "cat": "Terminated", "fte": 0.8}],
                         "zero_list": [{"name": "KOS", "code": "BR5", "cat": "Terminated"}, {"name": "NAP", "code": "BRN", "cat": "Suspended"}]})
    html = render_page(sn, "en", "2026-09-12", TH)
    assert "Still charging in Aug" in html and "ZOMBIE 0.8 FTE (terminated)" in html
    assert "Suspended with no manpower all year" in html and "NAP" in html
    assert "KOS, NAP" not in html and "No manpower all year (" not in html


def test_render_tolerates_snapshot_ingested_before_terminated_split():
    """VM 上由舊程式 ingest 的快照：extra 沒有 terminated/suspended/briefed，rows 沒有 cat。render 不得 500，
    標題退回不分結案/暫停的寫法。（真實事故 2026-10-01：/ui/202608/ 回 500）"""
    sn = snap()
    ex2 = sn["exceptions"][1]
    ex2["extra"] = {"pct": 20, "charging": 0, "twins": 1, "charging_list": [], "wound_list": [{"name": "Q11", "code": "BR3", "peak": 12.2, "peak_month": "May", "zero_since": "Jul"}],
                    "zero_list": [{"name": "KOS", "code": "BR5"}], "twin_list": [{k: v for k, v in sn["exceptions"][1]["extra"]["twin_list"][0].items() if k != "cat"}]}
    html = render_page(sn, "en", "2026-09-12", TH)
    assert "1 inactive (snapshot predates the terminated/suspended split)" in html
    assert "KOS (BR5) is inactive in the briefing" in html
    assert "Q11: peak 12.2 FTE in May" in html          # 無 cat 的 wound/zero 視為「要問的」，不靜默丟掉


def test_in_briefing_no_cl_label_matches_inactive_rule():
    """規則用 _active（排除 Terminated 與 Suspended）；標籤要講同一件事，不能只說 suspended。"""
    from src.portfolio.render.strings import t
    assert "not terminated or suspended" in t("en", "hc_in_briefing_no_cl")
    assert "非結案或暫停" in t("zh", "hc_in_briefing_no_cl") and "停案" not in t("zh", "hc_in_briefing_no_cl")


def test_report_is_v2_layout_with_inline_echarts():
    html = render_page(snap(), "en", "2026-09-12", TH)
    assert '<nav class="side" aria-label="BU10 Portfolio Review">' in html and 'href="#decisions"' in html
    assert html.index('id="overview"') < html.index('id="decisions"') < html.index('id="health"') < html.index('id="appendix"')
    assert "<script src=" not in html and "Apache Software Foundation" in html     # 內嵌，零外部腳本
    for cid in ("stage", "customer", "gantt", "heat-function", "forecast", "pva-0-burd"):
        assert f'id="c-{cid}"' in html, cid


def test_every_chart_has_a_data_table():
    html = render_page(snap(), "en", "2026-09-12", TH)
    assert html.count('class="chart"') == html.count('<details class="data">') > 5
    stage_table = html[html.index('id="c-stage-data"'):].split('<details class="data">', 1)[1].split("</details>", 1)[0]
    assert "<td>Execution</td><td>1</td>" in stage_table and "<td>Not in Briefing</td><td>1</td>" in stage_table


def test_appendix_picker_initialises_charts_when_shown():
    html = render_page(snap(), "en", "2026-09-12", TH)
    picker = html[html.rindex("<script>(function(){var s=document.getElementById('pick')"):]
    assert "window.eisCharts.init(document.getElementById('projects'))" in picker


def test_customer_name_cannot_break_the_page():
    sn = snap()
    sn["projects"][0]["customer"] = "</script><script>alert(1)</script>"
    html = render_page(sn, "en", "2026-09-12", TH)
    assert "<script>alert(1)" not in html
    assert find_pii(html) == []


def test_report_survives_snapshot_without_capacity():
    sn = snap()
    del sn["capacity"]
    html = render_page(sn, "en", "2026-09-12", TH)
    assert "Not in this snapshot." in html and 'id="c-stage"' in html


def test_appendix_task_tables_scroll_instead_of_widening_the_page():
    """375px 實測：任務描述欄把單案頁撐到 887px；表格要包在 .wide（overflow-x:auto）裡。"""
    html = render_page(snap(), "en", "2026-09-12", TH)
    assert '</span></summary><div class="wide"><table><thead><tr><th>Side</th>' in html     # 任務表（不是圖表的資料表）


def test_milestones_get_a_full_width_card():
    """瀏覽器實測：里程碑表放在三欄裡，Status 標籤被截斷；負載與預估兩欄，里程碑獨占一列。"""
    html = render_page(snap(), "en", "2026-09-12", TH)
    assert "grid-3" not in html.split("<style>")[1].split("</style>")[1]
    ov = html[html.index('id="overview"'):html.index('id="decisions"')]
    assert ov.count('<div class="grid-2">') == 3          # stage/customer、category/type、load/forecast


def test_decisions_section_lists_the_at_risk_projects():
    """Review：At Risk KPI 連到 Decisions，落地處必須列得出是哪幾案（含只在健康度追蹤的 MP 延後）。"""
    html = render_page(snap(), "en", "2026-09-12", TH)
    dec = html[html.index('id="decisions"'):html.index('id="health"')]
    assert "At risk (1):" in dec and "THORPE" in dec.split("At risk (1):")[1][:200]


def test_report_has_category_and_type_charts():
    html = render_page(snap(), "en", "2026-09-12", TH)
    assert 'id="c-category"' in html and 'id="c-type"' in html


def test_report_has_fu_plan_chart():
    html = render_page(snap(), "en", "2026-09-12", TH)
    assert 'id="c-fu"' in html
