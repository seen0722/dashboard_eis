"""例外（本月要決定的事）與健康度。文字一律用 key，由 render 層查表；evidence 只含專案名與數字。"""
from __future__ import annotations
import datetime as dt
import re
from ..config import Config
from ..entities import Project, Issue, Exception_, HealthRow
from .load import DeptLoad

EXEC_LIKE = re.compile(r"EVT|DVT|POC", re.I)


def days_between(a: str, b: str) -> int:
    return (dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days


def _active(projects: list[Project]) -> list[Project]:
    return [p for p in projects if p.in_briefing and p.stage_cat != "Suspended"]


def milestones_passed(projects: list[Project], today: str) -> list[tuple[Project, str, str, int]]:
    out = []
    for p in _active(projects):
        mp, pvt = p.dates.get("mp"), p.dates.get("pvt")
        if mp and days_between(mp, today) < 0 and p.stage_cat not in ("MP", "Sustain / EOP"):
            out.append((p, "mp", mp, -days_between(mp, today)))
        elif pvt and days_between(pvt, today) < 0 and EXEC_LIKE.search(p.stage or ""):
            out.append((p, "pvt", pvt, -days_between(pvt, today)))
    return sorted(out, key=lambda x: -x[3])


def mp_slipped(projects: list[Project], min_days: int) -> list[tuple[Project, int]]:
    out = []
    for p in _active(projects):
        mp, mo = p.dates.get("mp"), p.dates.get("mp_orig")
        if mp and mo and days_between(mp, mo) > min_days:
            out.append((p, days_between(mp, mo)))
    return sorted(out, key=lambda x: -x[1])


def task_description_gaps(projects: list[Project]) -> list[tuple[str, list[int]]]:
    out = []
    for p in projects:
        months = sorted({t.month for t in p.tasks if t.side == "BU"})
        gaps = [m for m in months if not any(t.description for t in p.tasks if t.side == "BU" and t.month == m)]
        if gaps:
            out.append((p.name, gaps))
    return out


def build_exceptions(projects: list[Project], loads: list[DeptLoad], latest_month: int, cfg: Config, today: str) -> list[Exception_]:
    th = cfg.thresholds
    m = latest_month - 1
    has_month = latest_month >= 1   # no non-zero month in Resource Summary -> treat FTE/util data as absent, never index with m
    passed = milestones_passed(projects, today)
    susp = [p for p in projects if p.in_briefing and p.stage_cat == "Suspended"]
    susp_fte = [(p, p.fte[m]) for p in susp if p.fte[m] > th["suspended_fte_min"]] if has_month else []
    cls = [p for p in projects if p.in_control_list]
    noplan = [p for p in cls if not p.has_plan]
    slipped = mp_slipped(projects, th["mp_slip_days"])
    spare = [d for d in loads if d.util[m] is not None and d.util[m] < th["spare_capacity_pct"]] if has_month else []
    full = (len([d for d in loads if d.util[m] is not None]) - len(spare)) if has_month else 0
    ex = [
        Exception_(1, "milestones_passed", "; ".join(f"{p.name} {k.upper()} {d} (+{n}d, stage {p.stage})" for p, k, d, n in passed),
                   "milestones_passed", "briefing", [p.code for p, *_ in passed]),
        Exception_(2, "suspended_charging", ", ".join(f"{p.name} {v:.1f} FTE" for p, v in sorted(susp_fte, key=lambda x: -x[1])),
                   "suspended_charging", "briefing_summary", [p.code for p, _ in susp_fte]),
        Exception_(3, "budget_missing", ", ".join(sorted(p.name for p in noplan)) + f" | {len(cls) - len(noplan)} / {len(cls)}",
                   "budget_missing", "control_list_pva", [p.code for p in noplan]),
        Exception_(4, "mp_slipped", "; ".join(f"{p.name} {p.dates['mp_orig']} -> {p.dates['mp']} ({n}d)" for p, n in slipped),
                   "mp_slipped", "briefing_mp", [p.code for p, _ in slipped]),
        Exception_(5, "spare_capacity", ", ".join(f"{d.function} {d.dept_name} ({d.keyed_in[m]} people, {d.util[m]}%)" for d in sorted(spare, key=lambda d: d.util[m])),
                   "spare_capacity", "control_list_month", []),
    ]
    # By design: ex[1] (suspended_charging).count is the total number of suspended projects (len(susp)),
    # while its codes/evidence list only those still charging (susp_fte) — the title template uses both
    # numbers ("{n} projects suspended, {charging} still charging" via extra["charging"] below). Do not
    # "fix" count to len(susp_fte); that would drop the total-suspended figure the template needs.
    for e, n in zip(ex, (len(passed), len(susp), len(noplan), len(slipped), len(spare))):
        e.count = n
    ex[1].extra = {"pct": round(len(susp) * 100 / max(1, len([p for p in projects if p.in_briefing]))), "charging": len(susp_fte)}
    ex[4].ask_data = str(full)
    return ex


# (check, level, source_key, from_issues)
CHECKS = [
    ("budget_missing", "decide", "control_list", False), ("milestones_passed", "decide", "briefing", False),
    ("in_briefing_no_cl", "track", "cross", False), ("in_cl_no_briefing", "track", "cross", False),
    ("mp_typo", "track", "briefing", False), ("customer_blank", "track", "briefing", False),
    ("name_unresolved", "track", "cross", True), ("task_description_blank", "track", "control_list", False),
    ("briefing_stale", "track", "briefing", False), ("cl_unreadable", "track", "control_list", True),
    ("cl_format_drift", "track", "control_list", True), ("duplicate_source", "track", "cross", True),
    ("dept_denominator_inconsistent", "track", "control_list", True),
    ("dept_function_inconsistent", "track", "control_list", True),
    ("cross_month_correction", "track", "snapshot", True), ("names_masked", "ok", "control_list", True),
]
DRIFT_CHECKS = {"cl_no_plan_vs_actual", "cl_pva_role_missing", "cl_no_task_sheet", "cl_no_month_sheets", "briefing_sheet_unreadable", "summary_block_without_ntd", "cl_multiple_codes"}


def build_health(projects: list[Project], loads: list[DeptLoad], issues: list[Issue], cfg: Config, today: str, snap_date: str) -> list[HealthRow]:
    th = cfg.thresholds
    active = _active(projects)
    blank = {"", "NA", "TBD", "N/A"}
    derived: dict[str, list[str]] = {
        "budget_missing": sorted(p.name for p in projects if p.in_control_list and not p.has_plan),
        "milestones_passed": [p.name for p, *_ in milestones_passed(projects, today)],
        "in_briefing_no_cl": sorted(p.name for p in active if not p.in_control_list),
        "in_cl_no_briefing": sorted(p.name for p in projects if p.in_control_list and not p.in_briefing),
        "mp_typo": [p.name for p, n in mp_slipped(projects, th["mp_typo_days"])],
        "customer_blank": sorted(p.name for p in active if p.customer.strip().upper() in blank),
        "task_description_blank": [f"{n} ({','.join(map(str, ms))})" for n, ms in task_description_gaps(projects)],
        "briefing_stale": [],   # 需要 BriefingRow.updated；由 cli 傳入的 issues 提供（見 Task 15）
    }
    rows = []
    for check, level, src, from_issues in CHECKS:
        if from_issues:
            if check == "cl_format_drift":
                hits = [i for i in issues if i.check in DRIFT_CHECKS]
            else:
                hits = [i for i in issues if i.check == check]
            if check == "names_masked":
                count = sum(int(i.detail) for i in hits if i.detail.isdigit()); names = []
            else:
                count, names = len(hits), [i.detail for i in hits]
        else:
            names = derived[check]; count = len(names)
        rows.append(HealthRow(level=level, check=check, label=check, count=count, names=names, source=src))
    return rows
