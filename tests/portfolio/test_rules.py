from src.portfolio.config import load_config
from src.portfolio.entities import Project, PlanVsActual, Task, Issue
from src.portfolio.model.load import DeptLoad
from src.portfolio.model.rules import milestones_passed, build_exceptions, build_health, task_description_gaps

TODAY = "2026-09-12"


def proj(name, stage="PVT", cat="Execution", mp=None, pvt=None, mp_orig=None, fte8=0.0, plan=None, in_cl=True, in_brief=True, tasks=None, customer="Dell"):
    p = Project(code="BR" + name, name=name, stage=stage, stage_cat=cat, customer=customer, in_briefing=in_brief, in_control_list=in_cl)
    p.dates.update({"mp": mp, "pvt": pvt, "mp_orig": mp_orig}); p.fte[7] = fte8
    if in_cl:
        p.pva = {"BU RD": PlanVsActual("BU RD", plan=[plan or 0] * 12)}; p.has_plan = bool(plan)
    p.tasks = tasks or []
    return p


def test_milestones_passed_rules():
    ps = [proj("THORPE", "PVT", "Execution", mp="2026-07-31"), proj("N1X", "EVT", "Execution", pvt="2026-09-02"),
          proj("DONE", "MP", "MP", mp="2026-07-31"), proj("Q11", "suspended", "Suspended", mp="2026-01-01"), proj("FUT", mp="2026-12-01")]
    got = [(p.name, k, d) for p, k, _, d in milestones_passed(ps, TODAY)]
    assert got == [("THORPE", "mp", 43), ("N1X", "pvt", 10)]


def test_exceptions_five_fixed_entries():
    cfg = load_config()
    ps = [proj("THORPE", mp="2026-07-31", plan=14.5), proj("KOS", "suspended", "Suspended", fte8=0.5, in_cl=False), proj("NOPLAN"),
          proj("KILO12", "RFQ", "RFQ / RFI", mp="2028-08-12", mp_orig="2027-08-26", plan=1)]
    loads = [DeptLoad("D1", "研發三部", "BSP", keyed_in=[5] * 12, util=[100] * 12), DeptLoad("D2", "研發二課", "SW", keyed_in=[8] * 12, util=[68] * 12)]
    ex = build_exceptions(ps, loads, 8, cfg, TODAY)
    assert [e.title for e in ex] == ["milestones_passed", "suspended_charging", "budget_missing", "mp_slipped", "spare_capacity"]
    assert ex[0].codes == ["BRTHORPE"] and "43" in ex[0].evidence
    assert ex[1].codes == ["BRKOS"] and "0.5" in ex[1].evidence
    assert ex[2].codes == ["BRNOPLAN"] and "2 / 3" in ex[2].evidence     # THORPE、KILO12 有 plan，共 3 份 Control List（THORPE, NOPLAN, KILO12）
    assert ex[3].codes == ["BRKILO12"] and "352" in ex[3].evidence
    assert ex[4].codes == [] and "SW 研發二課" in ex[4].evidence and "1" in ex[4].ask_data


def test_health_rows_and_task_gaps():
    cfg = load_config()
    t_ok, t_blank = Task(7, "BU", "BSP", "x", 1.0, "do stuff"), Task(8, "BU", "BSP", "x", 1.0, "")
    ps = [proj("THORPE", mp="2026-07-31", plan=14.5, tasks=[t_ok, t_blank]), proj("NOCL", in_cl=False), proj("NOBRIEF", in_brief=False, plan=1),
          proj("NA", customer="NA", plan=1), proj("KILO12", "RFQ", "RFQ / RFI", mp="2028-08-12", mp_orig="2027-08-26", plan=1)]
    issues = [Issue("track", "name_unresolved", "GHOST", "Briefing"), Issue("track", "cl_unreadable", "CPL22B", "Control List"),
              Issue("track", "cross_month_correction", "THORPE Jul FU 17.0 -> 3.7", "snapshot"), Issue("ok", "names_masked", "3", "Control List"),
              Issue("track", "dept_function_inconsistent", "D1: function differs", "Control List")]
    assert task_description_gaps(ps) == [("THORPE", [8])]
    rows = {r.check: r for r in build_health(ps, [], issues, cfg, TODAY, "20260907")}
    assert rows["budget_missing"].level == "decide"
    assert rows["budget_missing"].names == []            # 五個案子裡有 Control List 的都填了 plan
    assert rows["milestones_passed"].names == ["THORPE"]
    assert rows["in_briefing_no_cl"].names == ["NOCL"] and rows["in_cl_no_briefing"].names == ["NOBRIEF"]
    assert rows["mp_typo"].names == ["KILO12"] and rows["customer_blank"].count == 1
    assert rows["name_unresolved"].count == 1 and rows["cl_unreadable"].count == 1 and rows["cross_month_correction"].count == 1
    assert rows["task_description_blank"].names == ["THORPE (8)"]
    assert rows["names_masked"].level == "ok" and rows["names_masked"].count == 3
    assert rows["dept_function_inconsistent"].count == 1
