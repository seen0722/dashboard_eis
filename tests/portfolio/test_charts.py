from dataclasses import asdict
from src.portfolio.entities import Project, PlanVsActual
from src.portfolio.render.charts import timeline_svg, capacity_svg, pva_svg, week_gridlines


def p(name, stage, cat, **dates):
    x = Project(code="BR" + name, name=name, stage=stage, stage_cat=cat, in_briefing=True); x.dates.update(dates)
    return asdict(x)


def test_week_gridlines_count():
    svg = week_gridlines("2026-09-01", 6, 590)
    assert svg.count('stroke="#e6e9e6"') == 25          # 2026-09-07 起每週一，到 2027-02-22
    assert svg.count('stroke="#c4c9c5"') == 5           # 10/1 11/1 12/1 1/1 2/1


def test_timeline_rows_selection_and_late_marker():
    ps = [p("Foxtrot14", "DVT2", "Execution", pvt="2026-09-08", mp="2026-09-29"), p("Q11", "suspended", "Suspended", evt="2026-09-29"),
          p("TOMY", "RFQ", "RFQ / RFI"), p("OLD", "Sustain", "Sustain / EOP", mp="2024-01-01")]
    head, rows = timeline_svg(ps, "2026-09-12", "2026-09-01", 6, {"BRFoxtrot14"}, "en")
    assert "2026-09" in head and "2027-02" in head
    assert "Foxtrot14" in rows and "Q11" not in rows and "OLD" not in rows
    assert "TOMY" in rows and "no dates yet" in rows
    assert 'fill="#E8590C"' in rows                      # late marker for Foxtrot14 PVT


def test_capacity_svg_has_series_and_budget_note():
    x = Project(code="BR1", name="A", in_control_list=True, has_plan=True)
    x.pva = {"BU RD": PlanVsActual("BU RD", plan=[10] * 12, actual=[9] * 8 + [0] * 4), "PM": PlanVsActual("PM", plan=[1] * 12, actual=[1] * 8 + [0] * 4),
             "FU RD": PlanVsActual("FU RD", actual=[2] * 8 + [0] * 4)}
    svg = capacity_svg([asdict(x)], [12] * 12, 8, "en")
    assert svg.count("<polyline") == 4 and "Budget covers 1 / 1" in svg


def test_pva_svg_bars():
    svg = pva_svg({"BU RD": asdict(PlanVsActual("BU RD", plan=[1] * 12, actual=[2] * 8 + [0] * 4))}, "BU RD", 8)
    assert svg.count("<rect") == 20                      # 12 plan + 8 actual
