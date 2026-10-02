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
    assert '<td>09/08</td><td><a class="plain" href="/ui/202609/projects/BR6">N1X</a></td><td>Dell</td><td>PVT</td><td class="num">-4</td><td><span class="pill bad">Passed</span></td>' in h
    assert "<b>N1X</b>" in milestone_table(rows, "en")


def test_hidden_menu_checkbox_is_not_stretched_by_side_input_width():
    """375px 實測：.side input{width:100%} 蓋過 .navt{width:1px}，隱藏的 checkbox 撐成整個視窗寬，每頁都溢出到 565px。"""
    from src.portfolio.render.css import CSS
    assert ".side .navt{" in CSS and ".side .navt{position:absolute;opacity:0;width:1px;height:1px}" in CSS
    assert ".side .navbtn{display:none}" in CSS and ".side .navbtn{display:inline-block" in CSS   # .side label{display:flex} 曾讓桌面版也露出 Menu


def test_upcoming_pill_does_not_claim_on_track():
    """Review：資料只知道「超過 14 天」，不知道是否正常；標籤不能推論。"""
    assert pill("ok", "en") == '<span class="pill mute">Upcoming</span>'


def test_chart_card_shows_the_chart_headline():
    ch = Chart("x", "T", {"series": []}, ("a",), (), headline="Aug: 205 of 209 in use, 4 left")
    assert '<span class="card-sub">Aug: 205 of 209 in use, 4 left</span>' in chart_card(ch, "en")


def test_status_cards_lead_with_at_risk_and_decisions():
    from tests.portfolio.test_page import snap, TH
    from src.portfolio.render.viz.dash import status_html
    h = status_html(snap(), "en", TH, link=lambda c: f"/p/{c}", decisions_href="#decisions")
    assert h.startswith('<div class="status">')
    risk = h[:h.index('class="status-card dec"')]
    assert 'class="status-card risk"' in risk and '<b class="s-num">1</b>' in risk and '<a class="chip" href="/p/BR1">THORPE</a>' in risk
    dec = h[h.index('class="status-card dec"'):]
    assert '<b class="s-num">5</b>' in dec and "1 milestones passed without a stage change" in dec and 'href="#decisions"' in dec


def test_donut_card_has_an_html_legend_with_counts_and_shares():
    """2026-10-03：回到 mock 的三卡一列；圖例是 HTML 表格（色塊、名稱、數量、百分比），甜甜圈本身不帶圖例。"""
    from tests.portfolio.test_page import snap
    from src.portfolio.render.viz.dash import donut_card
    from src.portfolio.render.viz.options import stage_donut
    ch = stage_donut(snap(), "en")
    assert "legend" not in ch.option
    h = donut_card(ch, "en", sub="Briefing Stage column")
    assert '<span class="card-sub">Briefing Stage column</span>' in h and 'id="c-stage"' in h
    assert '<table class="legend-t">' in h
    assert '<td title="Execution"><i style="background:#2563EB"></i>Execution</td><td class="num"><b>1</b> <span class="dim">(17%)</span></td>' in h
    # 實機 1440（有側欄）每卡約 370px：名稱曾換行、色塊落單；改為不換行＋省略號（title 留全名），甜甜圈 128px
    from src.portfolio.render.css import CSS
    assert "table.legend-t{table-layout:fixed" in CSS and "text-overflow:ellipsis" in CSS and ch.height == 128


def test_bar_list_card_is_plain_html():
    from tests.portfolio.test_page import snap
    from src.portfolio.render.viz.dash import bar_list_card
    from src.portfolio.render.viz.options import customer_bars
    h = bar_list_card(customer_bars(snap(), "en"), "en", sub="Briefing Customer column")
    assert "data-chart" not in h and '<table class="bars-t">' in h
    assert '<td>Trimble</td><td class="bar"><span style="width:100%"></span></td><td class="num"><b>2</b></td>' in h



def test_chart_legend_sits_top_right_in_symbol_colours():
    """2026-10-03 需求方：Timeline legend 位置與顏色要照 mock——右上角、符號與圖上同色。"""
    ch = Chart("gantt", "Timeline", {"series": []}, ("a",), (), legend=(("◇", "EVT", "#3B82F6"), ("★", "MP", "#DC2626")))
    h = chart_card(ch, "en")
    assert '<div class="card-h has-legend"><h3>Timeline</h3><span class="lg-i">' in h
    assert '<span><i style="color:#3B82F6">◇</i>EVT</span><span><i style="color:#DC2626">★</i>MP</span>' in h
    from src.portfolio.render.css import CSS
    assert ".eq .card-h.has-legend{flex-direction:row" in CSS
