import re
from pathlib import Path
from src.portfolio.config import load_config
from src.portfolio.entities import Project, PlanVsActual, Task, Issue
from src.portfolio.model.load import DeptLoad
from src.portfolio.model.rules import CHECKS, DRIFT_CHECKS, milestones_passed, build_exceptions, build_health, task_description_gaps, second_identity_issues

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
    kos = proj("KOS", "suspended", "Suspended", in_cl=False)
    kos.fte[3] = 0.4; kos.fte[4] = 0.4   # charged Apr-May, zero since Jun -> "wound", not "still charging"
    tr_kos = Project(code="TR_KOS", name="TR_BU10_IPC_KOS", in_control_list=True, has_plan=True)
    tr_kos.fte[7] = 0.49                # same project, booked under a second (non-briefing) code
    ps = [proj("THORPE", mp="2026-07-31", plan=14.5), kos, tr_kos, proj("NOPLAN"),
          proj("KILO12", "RFQ", "RFQ / RFI", mp="2028-08-12", mp_orig="2027-08-26", plan=1)]
    loads = [DeptLoad("D1", "研發三部", "BSP", keyed_in=[5] * 12, util=[100] * 12), DeptLoad("D2", "研發二課", "SW", keyed_in=[8] * 12, util=[68] * 12)]
    ex = build_exceptions(ps, loads, 8, cfg, TODAY)
    assert [e.title for e in ex] == ["milestones_passed", "suspended_charging", "budget_missing", "mp_slipped", "spare_capacity"]
    assert ex[0].codes == ["BRTHORPE"] and "43" in ex[0].evidence
    assert ex[1].count == 1 and ex[1].evidence == ""   # KOS is the only suspended project, and it isn't charging this month
    assert ex[1].extra["twins"] == 1 and ex[1].extra["twin_list"][0]["twin_code"] == "TR_KOS"
    assert ex[1].extra["wound_list"][0]["peak_month"] == "Apr" and ex[1].extra["wound_list"][0]["zero_since"] == "Jun"
    assert "TR_KOS" in ex[1].codes
    # THORPE、TR_KOS、KILO12 有 plan，共 4 份 Control List（THORPE, TR_KOS, NOPLAN, KILO12）。涵蓋率走 extra，不混進 evidence。
    assert ex[2].codes == ["BRNOPLAN"] and ex[2].evidence == "NOPLAN" and ex[2].extra == {"covered": 3, "total": 4}
    assert ex[3].codes == ["BRKILO12"] and "352" in ex[3].evidence
    assert ex[4].codes == [] and "SW 研發二課" in ex[4].evidence and "1" in ex[4].ask_data


def test_second_identity_issues_and_health_row():
    cfg = load_config()
    kos = proj("KOS", "suspended", "Suspended", in_cl=False)
    kos.fte[3] = 0.4; kos.fte[4] = 0.4
    tr_kos = Project(code="TR_KOS", name="TR_BU10_IPC_KOS", in_control_list=True)
    tr_kos.fte[7] = 0.49
    ps = [kos, tr_kos]
    issues = second_identity_issues(ps, 8, cfg)
    assert len(issues) == 1 and issues[0].check == "suspended_second_identity" and issues[0].code == "BRKOS"
    assert "TR_BU10_IPC_KOS" in issues[0].detail and "0.49" in issues[0].detail
    rows = {r.check: r for r in build_health(ps, [], issues, cfg, TODAY, "20260907")}
    assert rows["suspended_second_identity"].count == 1


def test_exceptions_when_no_latest_month():
    cfg = load_config()
    ps = [proj("THORPE", mp="2026-07-31", plan=14.5), proj("KOS", "suspended", "Suspended", fte8=0.5, in_cl=False), proj("NOPLAN"),
          proj("KILO12", "RFQ", "RFQ / RFI", mp="2028-08-12", mp_orig="2027-08-26", plan=1)]
    loads = [DeptLoad("D1", "研發三部", "BSP", keyed_in=[5] * 12, util=[100] * 12), DeptLoad("D2", "研發二課", "SW", keyed_in=[8] * 12, util=[68] * 12)]
    ex = build_exceptions(ps, loads, 0, cfg, TODAY)
    assert ex[0].codes == ["BRTHORPE"]
    assert ex[1].codes == []
    assert ex[4].evidence == ""
    assert ex[4].ask_data == "0"


def test_health_rows_and_task_gaps():
    cfg = load_config()
    t_ok, t_blank = Task(7, "BU", "BSP", "x", 1.0, "do stuff"), Task(8, "BU", "BSP", "x", 1.0, "")
    ps = [proj("THORPE", mp="2026-07-31", plan=14.5, tasks=[t_ok, t_blank]), proj("NOCL", in_cl=False), proj("NOBRIEF", in_brief=False, plan=1),
          proj("NA", customer="NA", plan=1), proj("KILO12", "RFQ", "RFQ / RFI", mp="2028-08-12", mp_orig="2027-08-26", plan=1)]
    issues = [Issue("track", "name_unresolved", "GHOST", "Briefing"), Issue("track", "cl_unreadable", "CPL22B", "Control List"),
              Issue("track", "cross_month_correction", "THORPE Jul FU 17.0 -> 3.7", "snapshot"), Issue("ok", "names_masked", "3", "Control List"),
              Issue("track", "dept_function_inconsistent", "D1: function differs", "Control List"),
              Issue("track", "duplicate_source", "KOS: second Resource Summary block for BR9", "Resource Summary", "BR9")]
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
    assert rows["duplicate_source"].count == 1 and rows["duplicate_source"].source == "cross"


def test_briefing_stale_is_counted_from_issues_only():
    cfg = load_config()
    issues = [Issue("track", "briefing_stale", "THORPE last updated 2026-05-01", "Briefing", "BR1")]
    rows = {r.check: r for r in build_health([], [], issues, cfg, TODAY, "20260907")}
    assert rows["briefing_stale"].count == 1 and rows["briefing_stale"].names == ["THORPE last updated 2026-05-01"]


def test_every_issue_check_in_the_source_is_wired_into_the_health_table():
    """任何 Issue(...) 的 check 字面值都必須被健康度算到，否則問題會無聲消失。"""
    root = Path(__file__).resolve().parents[2] / "src" / "portfolio"
    known = {c for c, *_ in CHECKS} | DRIFT_CHECKS
    found: dict[str, str] = {}
    for f in sorted(root.rglob("*.py")):
        for m in re.finditer(r"""Issue\(\s*["'][a-z]+["']\s*,\s*["']([a-z_]+)["']""", f.read_text(encoding="utf-8")):
            found.setdefault(m.group(1), str(f.relative_to(root)))
    assert found, "no Issue( literals found — the regex stopped matching"
    unwired = {c: where for c, where in found.items() if c not in known}
    assert unwired == {}, f"Issue checks not in CHECKS or DRIFT_CHECKS: {unwired}"


def test_terminated_is_inactive_and_counted_with_suspended():
    """Terminated（結案）與 Suspended（暫停）都不算活躍：不進逾期里程碑；都進 suspended_charging 的 susp 集合。"""
    from src.portfolio.model.rules import milestones_passed, build_exceptions
    cfg = load_config()
    ps = [proj("DEAD", "Terminate", "Terminated", mp="2026-01-01", fte8=0.3), proj("PAUSE", "Suspend", "Suspended", mp="2026-01-01"),
          proj("LIVE", "PVT", "Execution", mp="2026-07-31")]
    assert [p.name for p, *_ in milestones_passed(ps, "2026-09-12")] == ["LIVE"]
    ex = build_exceptions(ps, [], 8, cfg, "2026-09-12")
    sc = [e for e in ex if e.title == "suspended_charging"][0]
    assert sc.count == 2 and sc.extra["charging"] == 1 and sc.extra["charging_list"][0]["name"] == "DEAD"
    assert sc.extra["terminated"] == 1 and sc.extra["suspended"] == 1
    assert sc.extra["charging_list"][0]["cat"] == "Terminated"
    assert [(w["name"], w["cat"]) for w in sc.extra["wound_list"]] == [] and [(z["name"], z["cat"]) for z in sc.extra["zero_list"]] == [("PAUSE", "Suspended")]
    assert sc.extra["briefed"] == 3


def test_second_identity_carries_stage_cat():
    cfg = load_config()
    kos = proj("KOS", "Terminate", "Terminated", in_cl=False)
    tr = Project(code="TR_KOS", name="TR_BU10_IPC_KOS", in_control_list=True); tr.fte[7] = 0.49
    ex = build_exceptions([kos, tr], [], 8, cfg, TODAY)
    tw = ex[1].extra["twin_list"][0]
    assert tw["cat"] == "Terminated" and tw["twin"] == "TR_BU10_IPC_KOS"
