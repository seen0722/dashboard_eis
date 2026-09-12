from src.portfolio.config import load_config
from src.portfolio.entities import MasterProject, BriefingRow, MonthlyFTE, ControlList, PlanVsActual, Task
from src.portfolio.model.normalize import build_projects


def make_inputs():
    master = [MasterProject("BR0000015346", "THORPE", "Trenton", "BU10_IPC"), MasterProject("BR0000016203", "ABLE", "Othes", "BU10_NB")]
    briefing = [
        BriefingRow("20260831", "AERIS", None, "POC-DVT-1", "AMD", "NB (14\")", {"kickoff": None, "evt": None, "dvt": "2026-07-24", "pvt": "2026-10-29", "mp": None, "mp_orig": None}),
        BriefingRow("20260907", "AERIS", "BR0000016203", "POC-DVT-1", "AMD", "NB (14\")", {"kickoff": None, "evt": None, "dvt": "2026-07-24", "pvt": "2026-10-29", "mp": None, "mp_orig": None}),
        BriefingRow("20260907", "THORPE", "BR0000015346", "PVT", "Trimble", "Tablet", {"kickoff": "2024-04-02", "evt": "2024-04-02", "dvt": "2025-03-06", "pvt": "2026-03-21", "mp": "2026-07-31", "mp_orig": "2025-10-13"}),
        BriefingRow("20260907", "GHOST", None, "RFQ", "X", "Y"),
    ]
    summary = [MonthlyFTE("THORPE", "Trenton", [12.0] * 8 + [0] * 4, [1e6] * 8 + [0] * 4), MonthlyFTE("Aeris", "Othes", [7.8] * 8 + [0] * 4)]
    cl = ControlList("THORPE", "x.xlsx", codes=["BR0000015346"],
                     pva={"BU RD": PlanVsActual("BU RD", plan=[14.5] * 12, actual=[18.0] * 8 + [0] * 4)},
                     tasks=[Task(8, "BU", "BSP", "研發三部", 3.1, "Thorpe SW release by BILLY_CHEN(陳澤明)")])
    cl2 = ControlList("ABLE", "y.xlsx", codes=["BR0000016203"], pva={"BU RD": PlanVsActual("BU RD")})
    return master, briefing, summary, [cl, cl2]


def test_merge_by_code_with_alias_and_history():
    projects, issues, latest = build_projects(*make_inputs(), load_config())
    by = {p.code: p for p in projects}
    assert latest == "20260907"
    t = by["BR0000015346"]
    assert t.name == "THORPE" and t.group == "Trenton" and t.stage == "PVT" and t.stage_cat == "Execution"
    assert t.dates["mp"] == "2026-07-31" and t.fte[0] == 12.0 and t.ntd[0] == 1e6
    assert t.in_briefing and t.in_control_list and t.has_plan
    assert t.pva["BU RD"].plan[0] == 14.5
    assert t.tasks[0].description == "Thorpe SW release by [name]"
    a = by["BR0000016203"]
    assert a.name == "ABLE" and a.customer == "AMD" and a.fte[0] == 7.8 and a.has_plan is False
    assert [h["snap"] for h in a.history] == ["20260831", "20260907"]
    g = by["NAME:GHOST"]
    assert g.in_briefing and not g.in_control_list
    checks = [i.check for i in issues]
    assert checks.count("name_unresolved") == 1 and "names_masked" in checks


def test_control_list_with_two_codes_is_flagged():
    master, briefing, summary, cls = make_inputs()
    cls[0].codes = ["BR0000015346", "BR0000099999"]
    projects, issues, _ = build_projects(master, briefing, summary, cls, load_config())
    assert any(i.check == "cl_multiple_codes" for i in issues)
    assert {p.code for p in projects} >= {"BR0000015346"}


def test_does_not_mutate_caller_tasks():
    master, briefing, summary, cls = make_inputs()
    original_desc = cls[0].tasks[0].description
    projects, issues, _ = build_projects(master, briefing, summary, cls, load_config())
    by = {p.code: p for p in projects}
    t = by["BR0000015346"]
    assert cls[0].tasks[0].description == original_desc
    assert t.tasks[0] is not cls[0].tasks[0]
    assert t.tasks[0].description == "Thorpe SW release by [name]"
