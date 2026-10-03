"""2026-10-03 全站一致性 review（/loop）：連結、色彩語意、長表收合、Decisions 層級、健康度排序。"""
import re
from tests.eis_mcp.conftest import TODAY
from tests.eis_mcp.test_web import html


def test_plain_links_are_not_underlined_until_hovered():
    from src.portfolio.render.css import CSS
    assert ".main a:not([class]){text-decoration:none}" in CSS and ".main a:not([class]):hover{text-decoration:underline}" in CSS


def test_heatmap_reads_full_load_as_normal_and_spare_capacity_as_the_signal():
    """≥95% 是正常滿載，不該用紅色；<85% 是報告要指出的閒置產能，用與部門表相同的橘色系。"""
    from src.portfolio.render.viz import tokens as T
    assert T.HEAT_HI.upper() not in ("#FCA5A5", "#F87171", "#EF4444", "#DC2626")
    assert T.HEAT_LOW.upper() == "#FED7AA"


def test_department_table_is_folded_under_the_heatmap(ingested):
    t = html(ingested, "/ui/202609/loads")
    assert '<details class="group"><summary data-expand="expand" data-collapse="collapse"><span>All ' in t
    t2 = html(ingested, "/ui/202609/loads?min_util=50")
    assert '<details class="group" open>' in t2                                         # 有篩選時自動展開


def test_decision_evidence_is_quieter_than_the_ask():
    from tests.portfolio.test_page import snap, TH
    from src.portfolio.render.page import exceptions_html
    h = exceptions_html(snap(), "en", TH)
    assert '<b class="sig">' not in h and '<div class="sig">' not in h                 # 橘色只留給 Decision needed 與排名


def test_at_risk_heading_uses_the_same_red_as_the_kpi():
    from tests.portfolio.test_page import snap, TH
    from src.portfolio.render.viz.dash import at_risk_html
    h = at_risk_html(snap(), "en", TH)
    assert '<b class="risk-h">At risk (1)</b>' in h and 'class="sig"' not in h


def test_health_lists_problems_first_and_folds_empty_checks(ingested):
    t = html(ingested, "/ui/202609/health")
    main = t[t.index('<div class="card">'):]
    assert re.search(r'<details class="group"><summary[^>]*><span>\d+ checks? found nothing</span>', main)


def test_health_level_and_source_cells_do_not_wrap_and_in_card_folds_match():
    from src.portfolio.render.css import CSS
    assert ".health-t td:first-child,.health-t td:last-child{white-space:nowrap}" in CSS
    assert ".card details.group>summary{font-size:var(--fs-sm);font-weight:400;color:var(--ink-2)}" in CSS


def test_health_table_carries_its_class(ingested):
    t = html(ingested, "/ui/202609/health")
    assert '<table class="health-t">' in t


# ---- 2026-10-03：基準日是 Briefing 快照日，畫面要明說，不寫「Today」 ----
def test_timeline_marker_names_the_briefing_date_not_today():
    from tests.portfolio.test_page import snap
    from src.portfolio.render.viz.options import gantt
    ch = gantt(snap(), "en", "2026-09-29", 6)
    ml = ch.option["series"][-1]["markLine"]
    assert ml["label"]["formatter"] == "Briefing 09/29"


def test_milestone_card_says_which_briefing_it_counts_from():
    from src.portfolio.render.viz.dash import milestone_card
    h = milestone_card([], "en", 8, asof="2026-09-29")
    assert "Past 7 days to 8 weeks after the 09/29 Briefing" in h


def test_same_day_reads_as_briefing_day_in_list_and_project_page():
    from src.eis_mcp.web.pages_projects import _next_cell
    from src.eis_mcp.web.pages_project import _milestones, _top_cards
    p = {"code": "B1", "name": "X", "in_briefing": True, "stage": "PVT", "stage_cat": "Execution", "customer": "C", "biz_type": "", "category": "",
         "fte": [1.0] * 12, "dates": {"kickoff": None, "evt": None, "dvt": None, "pvt": None, "mp": "2026-09-29", "mp_orig": None}}
    assert "on Briefing day" in _next_cell(p, "2026-09-29", {}) and "today" not in _next_cell(p, "2026-09-29", {})
    assert "on Briefing day" in _top_cards(p, 8, "2026-09-29", None) and "in 0 days" not in _top_cards(p, 8, "2026-09-29", None)
    assert "on Briefing day" in _milestones(p, "2026-09-29", None)
