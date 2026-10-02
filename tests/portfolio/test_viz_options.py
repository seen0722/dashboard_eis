from src.portfolio.entities import Exception_, PlanVsActual, Project
from src.portfolio.model.load import DeptLoad
from src.portfolio.model.snapshot import build_snapshot
from src.portfolio.render.viz import options as O

TH = {"mp_slip_days": 60, "spare_capacity_pct": 85, "upcoming_weeks": 8, "timeline_months": 6}
TODAY = "2026-09-12"


def snap():
    a = Project(code="BR1", name="THORPE", stage="PVT", stage_cat="Execution", customer="Trimble", in_briefing=True, in_control_list=True, has_plan=True)
    a.dates.update({"kickoff": "2024-04-02", "pvt": "2026-09-08", "mp": "2026-10-20", "mp_orig": "2026-06-01"})
    a.pva = {"BU RD": PlanVsActual("BU RD", plan=[10] * 12, actual=[9] * 8 + [0] * 4), "PM": PlanVsActual("PM", plan=[1] * 12, actual=[1] * 8 + [0] * 4),
             "FU RD": PlanVsActual("FU RD", actual=[2] * 8 + [0] * 4)}
    b = Project(code="BR2", name="TOMY", stage="RFQ", stage_cat="RFQ / RFI", customer="Trimble", in_briefing=True)
    c = Project(code="BR3", name="Q11", stage="suspended", stage_cat="Suspended", customer="TBD", in_briefing=True)
    c.dates.update({"evt": "2026-09-20"})
    d = Project(code="BR4", name="AX200", stage="MP", stage_cat="MP", customer="Axelera", in_briefing=True)
    d.dates.update({"pvt": "2026-09-08", "mp": "2026-10-30"})
    e = Project(code="BR5", name="KOS", stage="Terminate", stage_cat="Terminated", customer="NA", in_briefing=True)
    f = Project(code="TR_KOS", name="TR_BU10_IPC_KOS", in_control_list=True)
    f.pva = {"BU RD": PlanVsActual("BU RD", actual=[3] * 8 + [0] * 4)}
    g = Project(code="BR6", name="N1X", stage="EVT", stage_cat="Execution", customer="Dell", in_briefing=True)
    g.dates.update({"pvt": "2026-09-02"})
    ex = [Exception_(1, "milestones_passed", "N1X PVT 2026-09-02 (+10d, stage EVT)", "milestones_passed", "briefing", ["BR6"], count=1)]
    loads = [DeptLoad("D1", "研發一課", "ME", keyed_in=[4] * 8 + [0] * 4, allocated=[4.0] * 8 + [0.0] * 4),
             DeptLoad("D2", "研發二課", "ME", keyed_in=[6] * 8 + [0] * 4, allocated=[3.0] * 8 + [0.0] * 4),
             DeptLoad("D3", "測試課", "QTC")]
    return build_snapshot("202609", 8, "20260907", TODAY, [a, b, c, d, e, f, g], loads, [10] * 8 + [0] * 4, ex, [], [])


def test_kpis_and_at_risk_reuse_existing_rules():
    k = {x["key"]: x for x in O.kpis(snap(), "en", TH)}
    assert k["total"]["value"] == 7 and k["total"]["sub"] == "6 in Briefing, 2 terminated or suspended"
    assert (k["rfq"]["value"], k["poc"]["value"], k["exec"]["value"], k["mp"]["value"]) == (1, 0, 2, 1)
    assert k["mp"]["sub"] == "1 MP, 0 sustain / EOP"
    assert k["risk"]["codes"] == ["BR6", "BR1"] and k["risk"]["value"] == 2 and k["risk"]["tone"] == "bad"   # passed ∪ mp slipped 141d
    assert O.late_codes(snap()) == {"BR6"}


def test_stage_donut_keeps_not_in_briefing_as_its_own_slice():
    ch = O.stage_donut(snap(), "en")
    data = ch.option["series"][0]["data"]
    assert [d["name"] for d in data] == ["RFQ / RFI  1", "Execution  2", "MP  1", "Terminated  1", "Suspended  1", "Not in Briefing  1"]
    assert sum(d["value"] for d in data) == 7 and ch.option["title"]["text"] == "7"
    assert ch.rows[-1] == ("Not in Briefing", 1, "14%")


def test_customer_bars_keep_blank_and_na_separate_and_fold_the_tail():
    ch = O.customer_bars(snap(), "en")
    assert dict(ch.rows) == {"Trimble": 2, "(blank)": 1, "Axelera": 1, "Dell": 1, "NA": 1, "TBD": 1}
    assert ch.option["yAxis"]["data"][-1] == "Trimble"                      # 最大的在最上面
    top3 = O.customer_bars(snap(), "en", top=3)
    assert top3.rows == (("Trimble", 2), ("(blank)", 1), ("Axelera", 1), ("Others", 3))


def test_gantt_rows_markers_and_customer_variants():
    ch = O.gantt(snap(), "en", TODAY, 6)
    assert ch.option["yAxis"]["data"] == ["TOMY", "AX200", "THORPE", "N1X"]      # 依里程碑先後；第一列在最上面
    assert [r[0] for r in ch.rows] == ["N1X", "THORPE", "AX200", "TOMY"]         # Q11（暫停）、KOS（結案）、不在 Briefing 的都不列
    marks = ch.option["series"][1]["data"]
    n1x = next(m for m in marks if m["label"]["formatter"] == "PVT 09/02")
    assert n1x["itemStyle"]["color"] == "#DC2626"                                 # 已過且階段未前進 → 紅
    thorpe = next(m for m in marks if m["label"]["formatter"] == "PVT 09/08")
    assert thorpe["itemStyle"]["color"] == "#2563EB"                              # 已過但不在 milestones_passed → 不標紅
    assert any(m["label"]["formatter"] == "RFQ, no dates yet" for m in marks)
    assert ch.option["series"][0]["renderItem"] == {"$fn": "ganttBar"}
    assert set(ch.variants) == {"Axelera", "Dell", "Trimble"}
    assert ch.variants["Trimble"]["yAxis"]["data"] == ["TOMY", "THORPE"]
    assert ch.note.startswith("Red marks a milestone")
