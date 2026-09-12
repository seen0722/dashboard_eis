"""上月快照 vs 本月：過去月份的數字若被改了，就是 PM 事後更正，要列出來。"""
from __future__ import annotations
from ..entities import Project, Issue, MONTHS


def cross_month_corrections(prev: dict | None, projects: list[Project], latest_month: int, tol: float = 0.05) -> list[Issue]:
    if not prev:
        return []
    old = {p.get("code"): p for p in prev.get("projects", []) if p.get("code")}
    out = []
    max_check_month = min(latest_month - 1, prev.get("meta", {}).get("latest_month", 12))
    for p in projects:
        o = old.get(p.code)
        if not o or "fte" not in o:
            continue
        old_fte = o["fte"]
        # Skip if fte list is too short to safely compare
        if len(old_fte) < max_check_month:
            continue
        for m in range(max_check_month):
            a, b = old_fte[m], p.fte[m]
            if abs(a - b) > tol:
                out.append(Issue("track", "cross_month_correction", f"{p.name} {MONTHS[m]} FTE {a:.1f} -> {b:.1f}", "snapshot", p.code))
    return out
