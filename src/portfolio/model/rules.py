"""例外（本月要決定的事）與健康度。文字一律用 key，由 render 層查表；evidence 只含專案名與數字。"""
from __future__ import annotations
import datetime as dt
import re
from ..config import Config, normalize_name
from ..entities import INACTIVE, Project, Issue, Exception_, HealthRow, MONTHS
from .keys import segments
from .load import DeptLoad

EXEC_LIKE = re.compile(r"EVT|DVT|POC", re.I)


def days_between(a: str, b: str) -> int:
    return (dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days


def _active(projects: list[Project]) -> list[Project]:
    return [p for p in projects if p.in_briefing and p.stage_cat not in INACTIVE]


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


def suspended_lists(susp: list[Project], m: int, min_fte: float) -> tuple[list[dict], list[dict], list[dict]]:
    """把 Suspended 專案分三類：charging（本月仍掛帳）、wound（今年曾掛帳、現已歸零，附高峰月與歸零月）、
    zero（全年無人力）。wound 的存在本身就是一種訊號：Stage 改了但沒人去把人力也停掉，或反過來。"""
    charging, wound, zero = [], [], []
    for p in susp:
        if p.fte[m] > min_fte:
            charging.append({"name": p.name, "code": p.code, "cat": p.stage_cat, "fte": round(p.fte[m], 2)})
            continue
        history = p.fte[:m]
        active = [i for i, v in enumerate(history) if v > min_fte]
        if active:
            peak = max(history)
            wound.append({"name": p.name, "code": p.code, "cat": p.stage_cat, "peak": round(peak, 2),
                          "peak_month": MONTHS[history.index(peak)], "zero_since": MONTHS[active[-1] + 1]})
        else:
            zero.append({"name": p.name, "code": p.code, "cat": p.stage_cat})
    return charging, wound, zero


def find_second_identities(projects: list[Project], latest_month: int, cfg: Config) -> list[dict]:
    """真實案例：Briefing 裡 KOS 已 Suspended、0 FTE，但 Control List 與 Resource Summary 用另一個
    暫用代碼 TR_BU10_IPC_KOS 繼續掛帳——同一案兩個身分。比對規則：候選必須不在 Briefing 內，且名稱
    段尾與停案專案相同（segments 比對，避免 OKOS 誤配 ..._KOS），或正規化全名互為子字串；
    還要有實質存在（在某份 Control List 內，或今年曾掛過非零人力），純同名幽靈列不算。"""
    if latest_month < 1:
        return []
    m = latest_month - 1
    min_fte = cfg.thresholds["suspended_fte_min"]
    susp = [p for p in projects if p.in_briefing and p.stage_cat in INACTIVE]
    out = []
    for p in susp:
        p_segs = segments(p.name)
        p_norm = normalize_name(p.name)
        for q in projects:
            if q is p or q.in_briefing or not p_segs:
                continue
            q_segs = segments(q.name)
            suffix_hit = len(q_segs) >= len(p_segs) and q_segs[len(q_segs) - len(p_segs):] == p_segs
            substr_hit = p_norm in normalize_name(q.name)
            if not (suffix_hit or substr_hit):
                continue
            if not (q.in_control_list or sum(q.fte) > min_fte):
                continue
            out.append({"name": p.name, "code": p.code, "cat": p.stage_cat, "twin": q.name, "twin_code": q.code,
                        "twin_fte": round(q.fte[m], 2), "twin_in_cl": q.in_control_list})
    return out


def second_identity_issues(projects: list[Project], latest_month: int, cfg: Config) -> list[Issue]:
    return [Issue("decide", "suspended_second_identity",
                  f"{t['name']} ({t['code']}) also booked as {t['twin']} ({t['twin_code']}), {t['twin_fte']:.2f} FTE",
                  "cross", t["code"]) for t in find_second_identities(projects, latest_month, cfg)]


def build_exceptions(projects: list[Project], loads: list[DeptLoad], latest_month: int, cfg: Config, today: str) -> list[Exception_]:
    th = cfg.thresholds
    m = latest_month - 1
    has_month = latest_month >= 1   # no non-zero month in Resource Summary -> treat FTE/util data as absent, never index with m
    passed = milestones_passed(projects, today)
    susp = [p for p in projects if p.in_briefing and p.stage_cat in INACTIVE]
    if has_month:
        charging, wound, zero = suspended_lists(susp, m, th["suspended_fte_min"])
        twins = find_second_identities(projects, latest_month, cfg)
    else:
        charging, wound, zero, twins = [], [], [], []
    # codes 收的是「這條例外要決定的代碼」：仍在掛帳的停案代碼，加上每個第二身分本身的代碼
    # （要被併回主案的那個），所以用 twin_code 而不是 p.code——p.code 若也在 charging 早就收過了。
    susp_codes: list[str] = []
    for c in charging:
        if c["code"] not in susp_codes:
            susp_codes.append(c["code"])
    for tw in twins:
        if tw["twin_code"] not in susp_codes:
            susp_codes.append(tw["twin_code"])
    cls = [p for p in projects if p.in_control_list]
    noplan = [p for p in cls if not p.has_plan]
    slipped = mp_slipped(projects, th["mp_slip_days"])
    spare = [d for d in loads if d.util[m] is not None and d.util[m] < th["spare_capacity_pct"]] if has_month else []
    full = (len([d for d in loads if d.util[m] is not None]) - len(spare)) if has_month else 0
    ex = [
        Exception_(1, "milestones_passed", "; ".join(f"{p.name} {k.upper()} {d} (+{n}d, stage {p.stage})" for p, k, d, n in passed),
                   "milestones_passed", "briefing", [p.code for p, *_ in passed]),
        Exception_(2, "suspended_charging", ", ".join(f"{c['name']} {c['fte']:.1f} FTE" for c in charging),
                   "suspended_charging", "briefing_summary", susp_codes),
        Exception_(3, "budget_missing", ", ".join(sorted(p.name for p in noplan)),
                   "budget_missing", "control_list_pva", [p.code for p in noplan]),
        Exception_(4, "mp_slipped", "; ".join(f"{p.name} {p.dates['mp_orig']} -> {p.dates['mp']} ({n}d)" for p, n in slipped),
                   "mp_slipped", "briefing_mp", [p.code for p, _ in slipped]),
        Exception_(5, "spare_capacity", ", ".join(f"{d.function} {d.dept_name} ({d.keyed_in[m]} people, {d.util[m]}%)" for d in sorted(spare, key=lambda d: d.util[m])),
                   "spare_capacity", "control_list_month", []),
    ]
    # By design: ex[1] (suspended_charging).count is the total number of suspended projects (len(susp)),
    # while its codes/evidence list only those still charging (charging) plus any second-identity codes —
    # the title template uses both numbers ("{n} projects suspended, {charging} still charging, {twins}
    # booked under a second code" via extra below). Do not "fix" count to len(charging); that would drop
    # the total-suspended figure the template needs.
    for e, n in zip(ex, (len(passed), len(susp), len(noplan), len(slipped), len(spare))):
        e.count = n
    briefed = len([p for p in projects if p.in_briefing])
    ex[1].extra = {"pct": round(len(susp) * 100 / max(1, briefed)), "briefed": briefed,
                    "charging": len(charging), "twins": len(twins), "charging_list": charging,
                    "terminated": sum(1 for p in susp if p.stage_cat == "Terminated"), "suspended": sum(1 for p in susp if p.stage_cat == "Suspended"),
                    "wound_list": wound, "zero_list": zero, "twin_list": twins}
    # 涵蓋率是數字，不是證據：走 extra 讓 render 直接取用，evidence 只留專案名。
    ex[2].extra = {"covered": len(cls) - len(noplan), "total": len(cls)}
    ex[4].ask_data = str(full)
    return ex


# (check, level, source_key, from_issues)
CHECKS = [
    ("budget_missing", "decide", "control_list", False), ("milestones_passed", "decide", "briefing", False),
    ("suspended_second_identity", "decide", "cross", True),
    ("in_briefing_no_cl", "track", "cross", False), ("in_cl_no_briefing", "track", "cross", False),
    ("mp_typo", "track", "briefing", False), ("customer_blank", "track", "briefing", False),
    ("name_unresolved", "track", "cross", True), ("task_description_blank", "track", "control_list", False),
    ("briefing_stale", "track", "briefing", True), ("cl_unreadable", "track", "control_list", True),
    ("cl_format_drift", "track", "control_list", True), ("duplicate_source", "track", "cross", True),
    ("dept_denominator_inconsistent", "track", "control_list", True),
    ("dept_function_inconsistent", "track", "control_list", True),
    ("cross_month_correction", "track", "snapshot", True), ("names_masked", "ok", "control_list", True),
]
DRIFT_CHECKS = {"cl_no_plan_vs_actual", "cl_pva_role_missing", "cl_no_task_sheet", "cl_no_month_sheets", "briefing_sheet_unreadable",
                "summary_block_without_ntd", "cl_multiple_codes", "master_row_without_code"}


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
    }   # briefing_stale 需要 BriefingRow.updated，由 cli 放進 issues，走 from_issues 這條路
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
