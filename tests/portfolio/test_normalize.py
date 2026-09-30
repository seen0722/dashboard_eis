from src.portfolio.config import load_config
from src.portfolio.entities import MasterProject, BriefingRow, MonthlyFTE, ControlList, PlanVsActual, Task
from src.portfolio.model.normalize import build_projects


def make_inputs():
    master = [MasterProject("BR0000015346", "THORPE", "Trenton", "BU10_IPC"), MasterProject("BR0000016203", "ABLE", "Othes", "BU10_NB")]
    briefing = [
        BriefingRow("20260831", "AERIS", None, "POC-DVT-1", "AMD", "NB (14\")", {"kickoff": None, "evt": None, "dvt": "2026-07-24", "pvt": "2026-10-29", "mp": None, "mp_orig": None}),
        BriefingRow("20260907", "AERIS", "BR0000016203", "POC-DVT-1", "AMD", "NB (14\")", {"kickoff": None, "evt": None, "dvt": "2026-07-24", "pvt": "2026-10-29", "mp": None, "mp_orig": None}),
        BriefingRow("20260907", "THORPE", "BR0000015346", "PVT", "Trimble", "Tablet", {"kickoff": "2024-04-02", "evt": "2024-04-02", "dvt": "2025-03-06", "pvt": "2026-03-21", "mp": "2026-07-31", "mp_orig": "2025-10-13"},
                    biz_type="ODM", category="Tablet", panel_size='10"'),
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
    assert (t.biz_type, t.category, t.panel_size) == ("ODM", "Tablet", '10"')
    assert (by["BR0000016203"].biz_type, by["BR0000016203"].category, by["BR0000016203"].panel_size) == ("", "", "")
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


def test_two_summary_blocks_for_one_code_accumulate():
    master, briefing, _, cls = make_inputs()
    summary = [MonthlyFTE("KOS", "Unicorn", [12.0] * 8 + [0] * 4, [1e6] * 8 + [0] * 4),
               MonthlyFTE("KOS", "Othes", [3.0] * 8 + [0] * 4, [5e5] * 8 + [0] * 4)]
    projects, issues, _ = build_projects(master, briefing, summary, cls, load_config())
    kos = {p.code: p for p in projects}["NAME:KOS"]
    assert kos.fte[0] == 15.0 and kos.fte[8] == 0.0 and kos.ntd[0] == 1.5e6
    assert [i.check for i in issues].count("duplicate_source") == 1
    assert summary[0].fte[0] == 12.0 and summary[1].fte[0] == 3.0     # 不動呼叫端資料


def test_two_control_lists_for_one_code_merge():
    master, briefing, summary, cls = make_inputs()
    second = ControlList("THORPE 2nd", "z.xlsx", codes=["BR0000015346"],
                         pva={"BU RD": PlanVsActual("BU RD", plan=[0.5] * 12, actual=[2.0] * 8 + [0] * 4),
                              "PM": PlanVsActual("PM", plan=[1.0] * 12)},
                         tasks=[Task(9, "BU", "BSP", "研發三部", 1.0, "extra work")])
    projects, issues, _ = build_projects(master, briefing, summary, cls + [second], load_config())
    t = {p.code: p for p in projects}["BR0000015346"]
    assert t.pva["BU RD"].plan[0] == 15.0 and t.pva["BU RD"].actual[0] == 20.0
    assert t.pva["PM"].plan[0] == 1.0                                 # 只有第二份有 PM 區塊
    assert [(x.month, x.description) for x in t.tasks] == [(8, "Thorpe SW release by [name]"), (9, "extra work")]
    dups = [i for i in issues if i.check == "duplicate_source"]
    assert len(dups) == 1 and dups[0].code == "BR0000015346"
    assert cls[0].pva["BU RD"].plan[0] == 14.5 and second.pva["BU RD"].plan[0] == 0.5   # 不動呼叫端資料


def test_does_not_mutate_caller_tasks():
    master, briefing, summary, cls = make_inputs()
    original_desc = cls[0].tasks[0].description
    projects, issues, _ = build_projects(master, briefing, summary, cls, load_config())
    by = {p.code: p for p in projects}
    t = by["BR0000015346"]
    assert cls[0].tasks[0].description == original_desc
    assert t.tasks[0] is not cls[0].tasks[0]
    assert t.tasks[0].description == "Thorpe SW release by [name]"
