import re
from dataclasses import asdict
from src.portfolio.entities import Project, PlanVsActual, Task, Exception_, HealthRow, Issue
from src.portfolio.model.load import DeptLoad
from src.portfolio.model.snapshot import build_snapshot
from src.portfolio.render.page import render_page
from src.portfolio.render.pii import find_pii

TH = {"mp_slip_days": 60, "mp_typo_days": 300, "spare_capacity_pct": 85, "suspended_fte_min": 0.05, "briefing_stale_days": 60, "upcoming_weeks": 8, "timeline_months": 6}


def snap():
    a = Project(code="BR1", name="THORPE", stage="PVT", stage_cat="Execution", customer="Trimble", in_briefing=True, in_control_list=True, has_plan=True)
    a.dates.update({"kickoff": "2024-04-02", "dvt": "2026-09-08", "pvt": "2026-03-21", "mp": "2026-07-31", "mp_orig": "2025-10-13"}); a.fte[7] = 12.4
    a.pva = {"BU RD": PlanVsActual("BU RD", plan=[14.5] * 12, actual=[18] * 8 + [0] * 4)}
    a.tasks = [Task(8, "BU", "BSP", "研發三部", 3.1, "SW release"), Task(8, "FU", "SQA", "軟體三處", 0.6, "SQA")]
    b = Project(code="BR2", name="TOMY", stage="RFQ", stage_cat="RFQ / RFI", customer="Trimble", in_briefing=True)
    c = Project(code="BR3", name="Q11", stage="suspended", stage_cat="Suspended", customer="TBD", in_briefing=True)
    c.dates.update({"evt": "2026-09-10"})
    d = Project(code="BR4", name="AX200", stage="MP", stage_cat="MP", customer="Axelera", in_briefing=True)
    d.dates.update({"pvt": "2026-09-08"})
    ex = [Exception_(1, "milestones_passed", "THORPE MP 2026-07-31 (+43d, stage PVT)", "milestones_passed", "briefing", ["BR1"], count=1),
          Exception_(2, "suspended_charging", "", "suspended_charging", "briefing_summary", [], count=0, extra={"pct": 0, "charging": 0}),
          Exception_(3, "budget_missing", " | 1 / 1", "budget_missing", "control_list_pva", [], count=0),
          Exception_(4, "mp_slipped", "THORPE 2025-10-13 -> 2026-07-31 (291d)", "mp_slipped", "briefing_mp", ["BR1"], count=1),
          Exception_(5, "spare_capacity", "", "spare_capacity", "control_list_month", [], count=0, ask_data="2")]
    hl = [HealthRow("decide", "budget_missing", "budget_missing", 0, [], "control_list"), HealthRow("ok", "names_masked", "names_masked", 3, [], "control_list")]
    return build_snapshot("202609", 8, "20260907", "2026-09-12", [a, b, c, d], [DeptLoad("D", "x", "BSP", keyed_in=[5] * 12, util=[100] * 12)], [207] * 12, ex, hl, [])


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
