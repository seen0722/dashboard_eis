"""上月快照 vs 本月：過去月份的數字若被改了，就是 PM 事後更正，要列出來。"""
from __future__ import annotations
from ..entities import Project, Issue, MONTHS


def cross_month_corrections(prev: dict | None, projects: list[Project], latest_month: int, tol: float = 0.05) -> list[Issue]:
    if not prev:
        return []
    old = {p["code"]: p for p in prev.get("projects", [])}
    out = []
    for p in projects:
        o = old.get(p.code)
        if not o:
            continue
        for m in range(min(latest_month - 1, prev["meta"].get("latest_month", 12))):
            a, b = o["fte"][m], p.fte[m]
            if abs(a - b) > tol:
                out.append(Issue("track", "cross_month_correction", f"{p.name} {MONTHS[m]} FTE {a:.1f} -> {b:.1f}", "snapshot", p.code))
    return out
