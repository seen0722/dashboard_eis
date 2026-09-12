"""Resource Summary：每案逐月 Total EIS 人力與 NTD。"""
from __future__ import annotations
from pathlib import Path
from ..entities import MonthlyFTE, Issue, empty_months
from .workbook import open_workbook

SKIP_SHEETS = {"Summary", "2026 佔比"}


def _num(v) -> float:
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return 0.0


def _months(r) -> list[float]:
    vals = [_num(x) for x in list(r)[1:13]]
    return (vals + empty_months())[:12]


def read_resource_summary(path: str | Path) -> tuple[list[MonthlyFTE], list[Issue]]:
    with open_workbook(path) as wb:
        data = {}
        for sheet in wb.sheetnames:
            if sheet in SKIP_SHEETS:
                continue
            data[sheet] = list(wb.rows(sheet))

    out, issues = [], []
    for sheet, rows in data.items():
        for i, r in enumerate(rows):
            if not r or r[0] is None or i + 1 >= len(rows):
                continue
            nxt = rows[i + 1]
            if not nxt or not str(nxt[0] or "").startswith("Total EIS"):
                continue
            name = str(r[0]).strip()
            if "SUMMARY" in name.upper():
                continue
            rec = MonthlyFTE(name=name, group=sheet, fte=_months(nxt))
            third = rows[i + 2] if i + 2 < len(rows) else None
            if third and str(third[0] or "").startswith("Total Amount"):
                rec.ntd = _months(third)
            else:
                issues.append(Issue("track", "summary_block_without_ntd", f"{sheet}/{name}: no 'Total Amount NTD' row", "Resource Summary"))
            out.append(rec)
    return out, issues


def latest_month(rows: list[MonthlyFTE]) -> int:
    for m in range(11, -1, -1):
        if sum(r.fte[m] for r in rows) > 0:
            return m + 1
    return 0
