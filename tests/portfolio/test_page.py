import re
import pytest
from dataclasses import asdict
from src.portfolio.entities import Project, PlanVsActual, Task, Exception_, HealthRow, Issue
from src.portfolio.model.load import DeptLoad
from src.portfolio.model.snapshot import build_snapshot
from src.portfolio.render.page import render_page
from src.portfolio.render.pii import find_pii

TH = {"mp_slip_days": 60, "mp_typo_days": 300, "spare_capacity_pct": 85, "suspended_fte_min": 0.05, "briefing_stale_days": 60, "upcoming_weeks": 8, "timeline_months": 6}


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
    e = Project(code="BR5", name="KOS", stage="suspended", stage_cat="Suspended", customer="TBD", in_briefing=True)
    f = Project(code="TR_KOS", name="TR_BU10_IPC_KOS", in_control_list=True)
    f.fte[7] = 0.49   # same project as KOS, booked under a second (non-briefing) code
    twin = {"name": "KOS", "code": "BR5", "twin": "TR_BU10_IPC_KOS", "twin_code": "TR_KOS", "twin_fte": 0.49, "twin_in_cl": True}
    ex = [Exception_(1, "milestones_passed", "THORPE MP 2026-07-31 (+43d, stage PVT)", "milestones_passed", "briefing", ["BR1"], count=1),
          Exception_(2, "suspended_charging", "", "suspended_charging", "briefing_summary", ["TR_KOS"], count=1,
                     extra={"pct": 20, "charging": 0, "twins": 1, "charging_list": [], "wound_list": [],
                            "zero_list": [{"name": "KOS", "code": "BR5"}], "twin_list": [twin]}),
          Exception_(3, "budget_missing", "", "budget_missing", "control_list_pva", [], count=0, extra={"covered": 1, "total": 1}),
          Exception_(4, "mp_slipped", "THORPE 2025-10-13 -> 2026-07-31 (291d)", "mp_slipped", "briefing_mp", ["BR1"], count=1),
          Exception_(5, "spare_capacity", "", "spare_capacity", "control_list_month", [], count=0, ask_data="2")]
    hl = [HealthRow("decide", "budget_missing", "budget_missing", 0, [], "control_list"), HealthRow("ok", "names_masked", "names_masked", 3, [], "control_list")]
    return build_snapshot("202609", 8, "20260907", "2026-09-12", [a, b, c, d, e, f], [DeptLoad("D", "x", "BSP", keyed_in=[5] * 12, util=[100] * 12)], [207] * 12, ex, hl, [])


def test_page_sections_and_strings():
    html = render_page(snap(), "en", "2026-09-12", TH)
    for s in ("BU10 Portfolio Review", "Decisions this month", "1 milestones passed", "Decision needed:", "Milestones, next 8 weeks",
              "Six-month timeline", "Manpower and capacity", "Data health", "Project appendix", "Aug: 1 BU tasks, 1 FU tasks, 3.7 FTE",
              "later months carried from Aug"):
        assert s in html, s
    assert "TOMY" in html and "no dates yet" in html
    assert html.count("<details") == 1 and "<details open" not in html
    assert "·" not in html and "→" not in html
    assert 'lang="en"' in html
    assert "Q11" not in html.split("Six-month timeline")[0]
    assert '<span class="dim">passed</span>' in html
    assert '<span class="sig">passed</span>' in html
    assert "Second identity, likely the same project under another code" in html
    assert "1 projects suspended (" in html and "1 booked under a second code" in html
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
