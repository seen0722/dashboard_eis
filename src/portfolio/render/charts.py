"""月份序列的小工具。圖本身由 viz/options.py 產生 ECharts option；2026-10-02 起不再手畫 SVG。"""
from __future__ import annotations
import datetime as dt


def _add_months(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.month - 1 + n, 12)
    return d.replace(year=d.year + y, month=m + 1, day=1)


def _sum(projects: list[dict], role: str, field: str, n: int = 12, only_plan: bool = False) -> list[float]:
    ps = [p for p in projects if p.get("pva") and (p["has_plan"] or not only_plan)]
    return [sum((p["pva"].get(role) or {}).get(field, [0] * 12)[i] for p in ps) for i in range(n)]


def carry_forward(capacity: list[int], latest_month: int) -> list[int]:
    """latest_month 之後還沒有填報人數，畫成 0 會讓天花板看起來消失。沿用最後一個非零月的值。
    只改畫出來的序列，snapshot 的 capacity 保持原始值（0 代表「還沒填報」）。"""
    out = list(capacity)
    cut = max(0, min(latest_month, len(out)))
    last = next((v for v in reversed(out[:cut]) if v), 0)
    return out[:cut] + [last] * (len(out) - cut)
