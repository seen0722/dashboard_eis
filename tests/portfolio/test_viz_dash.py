from src.portfolio.render.viz.dash import card, chart_card, kpi_cards, milestone_status, milestone_table, pill, safe_chart_card, side_nav
from src.portfolio.render.viz.embed import Chart

CH = Chart("stage", "Projects by stage", {"series": []}, ("Stage", "Projects"), (("MP", 1),))


def test_kpi_cards_escape_link_and_tone():
    h = kpi_cards([{"key": "total", "label": "Total", "value": 7, "sub": "6 in Briefing", "tone": ""},
                   {"key": "risk", "label": "At risk", "value": "<2>", "sub": "", "tone": "bad"}], {"risk": "/ui/202609/decisions"})
    assert h.startswith('<div class="kpis">')
    assert '<div class="kpi"><span class="k-label">Total</span><b class="k-value">7</b><span class="k-sub">6 in Briefing</span></div>' in h
    assert '<a class="kpi bad" href="/ui/202609/decisions"><span class="k-label">At risk</span><b class="k-value">&lt;2&gt;</b></a>' in h
    assert kpi_cards([], cls="four").startswith('<div class="kpis four">')


def test_cards_and_side_nav():
    assert card("A & B", "<p>x</p>", sub="src") == '<div class="card"><div class="card-h"><h3>A &amp; B</h3><span class="card-sub">src</span></div><p>x</p></div>'
    assert chart_card(CH, "en").startswith('<div class="card"><div class="card-h"><h3>Projects by stage</h3></div><div class="chart" id="c-stage"')
    nav = side_nav('<a class="brand" href="/ui/">B</a>', '<a href="#x">X</a>', "Menu")
    assert nav.startswith('<nav class="side" aria-label="EIS"><a class="brand" href="/ui/">B</a><input type="checkbox" id="navt" class="navt">')
    assert '<label for="navt" class="navbtn">Menu</label><div class="links"><a href="#x">X</a></div></nav>' in nav


def test_safe_chart_card_reports_missing_data():
    def broken():
        raise KeyError("capacity")
    h = safe_chart_card("Forecast vs capacity", broken, "en")
    assert "<h3>Forecast vs capacity</h3>" in h and "Not in this snapshot." in h and "data-chart" not in h
    assert 'id="c-stage"' in safe_chart_card("x", lambda: CH, "en")


def test_milestone_status_pills_and_table():
    assert [milestone_status(d) for d in (-1, 0, 14, 15)] == ["passed", "due", "due", "ok"]
    assert pill("passed", "en") == '<span class="pill bad">Passed</span>'
    assert pill("passed", "en", late=False) == '<span class="pill mute">Passed</span>'
    rows = [{"date": "2026-09-08", "name": "N1X", "code": "BR6", "customer": "Dell", "milestone": "pvt", "days_left": -4, "late": True}]
    h = milestone_table(rows, "en", link=lambda c: f"/ui/202609/projects/{c}")
    assert h.startswith('<div class="wide"><table>')
    assert '<td>09/08</td><td><a href="/ui/202609/projects/BR6">N1X</a></td><td>Dell</td><td>PVT</td><td class="num">-4</td><td><span class="pill bad">Passed</span></td>' in h
    assert "<b>N1X</b>" in milestone_table(rows, "en")


def test_hidden_menu_checkbox_is_not_stretched_by_side_input_width():
    """375px 實測：.side input{width:100%} 蓋過 .navt{width:1px}，隱藏的 checkbox 撐成整個視窗寬，每頁都溢出到 565px。"""
    from src.portfolio.render.css import CSS
    assert ".side .navt{" in CSS and ".side .navt{position:absolute;opacity:0;width:1px;height:1px}" in CSS
    assert ".side .navbtn{display:none}" in CSS and ".side .navbtn{display:inline-block" in CSS   # .side label{display:flex} 曾讓桌面版也露出 Menu
