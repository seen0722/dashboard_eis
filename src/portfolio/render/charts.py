"""純 Python 產 SVG。座標與樣式都在這裡，page.py 只負責擺位。"""
from __future__ import annotations
import datetime as dt
from html import escape
from ..entities import MONTHS
from .strings import t

SLATE, SLATE2, TEAL, INK, INK2, INK3, SIGNAL, GRID, GRID2 = "#3D5A80", "#A9B8CC", "#5C8D89", "#22262A", "#5B6167", "#9AA3AB", "#E8590C", "#e6e9e6", "#c4c9c5"
TL_W, ROW_H = 590, 32


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _add_months(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.month - 1 + n, 12)
    return d.replace(year=d.year + y, month=m + 1, day=1)


def week_gridlines(start: str, months: int, width: int) -> str:
    t0, t1 = _d(start), _add_months(_d(start), months)
    x = lambda d: (d - t0).days / (t1 - t0).days * width
    out, d = [], t0
    while d < t1:
        if d.weekday() == 0:
            out.append(f'<line x1="{x(d):.1f}" x2="{x(d):.1f}" y1="0" y2="{ROW_H}" stroke="{GRID}"/>')
        if d.day == 1 and d != t0:
            out.append(f'<line x1="{x(d):.1f}" x2="{x(d):.1f}" y1="0" y2="{ROW_H}" stroke="{GRID2}"/>')
        d += dt.timedelta(days=1)
    return "".join(out)


def _marker(kind: str, px: float, c: str) -> str:
    return {"evt": f'<rect x="{px-4:.1f}" y="12" width="8" height="8" fill="#fff" stroke="{c}" stroke-width="1.5"/>',
            "dvt": f'<rect x="{px-4:.1f}" y="12" width="8" height="8" fill="{c}"/>',
            "pvt": f'<polygon points="{px:.1f},11 {px+5:.1f},20 {px-5:.1f},20" fill="{c}"/>',
            "mp": f'<circle cx="{px:.1f}" cy="16" r="5" fill="{c}"/>'}[kind]


def timeline_svg(projects: list[dict], today: str, start: str, months: int, late_codes: set[str], lang: str) -> tuple[str, str]:
    t0, t1 = _d(start), _add_months(_d(start), months)
    x = lambda s: (_d(s) - t0).days / (t1 - t0).days * TL_W
    in_win = lambda s: bool(s) and t0 <= _d(s) < t1
    grid = week_gridlines(start, months, TL_W)
    head, d = [], t0
    while d < t1:
        head.append(f'<text x="{x(d.isoformat())+4:.1f}" y="12" font-size="11" fill="{INK2}">{d.strftime("%Y-%m")}</text>'); d = _add_months(d, 1)
    rows = [p for p in projects if p["in_briefing"] and p["stage_cat"] != "Suspended"
            and (any(in_win(p["dates"][k]) for k in ("evt", "dvt", "pvt", "mp")) or (p["stage_cat"] == "RFQ / RFI" and not p["dates"]["mp"]))]
    rows.sort(key=lambda p: p["dates"]["mp"] or p["dates"]["pvt"] or p["dates"]["dvt"] or p["dates"]["evt"] or "9")
    out = []
    for p in rows:
        ms = [k for k in ("kickoff", "evt", "dvt", "pvt", "mp") if p["dates"][k]]
        s = grid + f'<line x1="{x(today):.1f}" x2="{x(today):.1f}" y1="0" y2="{ROW_H}" stroke="{INK}" stroke-dasharray="2 3"/>'
        for a, b in zip(ms, ms[1:]):
            xa, xb = max(0, x(p["dates"][a])), min(TL_W, x(p["dates"][b]))
            if xb > xa:
                s += f'<rect x="{xa:.1f}" y="14" width="{xb-xa:.1f}" height="4" fill="{SLATE}" opacity=".3"/>'
        for k in ms:
            if k == "kickoff" or not in_win(p["dates"][k]):
                continue
            px = x(p["dates"][k]); late = p["code"] in late_codes and _d(p["dates"][k]) < _d(today)
            c = SIGNAL if late else SLATE; right = px > TL_W - 70
            s += _marker(k, px, c) + (f'<text x="{px + (-9 if right else 9):.1f}" y="20" font-size="11" text-anchor="{"end" if right else "start"}" fill="{c}">'
                                      f'{k.upper()} {p["dates"][k][5:].replace("-", "/")}</text>')
        if not ms:
            s += f'<text x="{x(today)+8:.1f}" y="20" font-size="11" fill="{INK3}">{escape(t(lang, "no_dates", stage=p["stage"]))}</text>'
        out.append(f'<tr><td><b>{escape(p["name"])}</b></td><td>{escape(p["customer"])}</td><td>{escape(p["stage"])}</td>'
                   f'<td><svg width="{TL_W}" height="{ROW_H}">{s}</svg></td></tr>')
    return f'<svg width="{TL_W}" height="16">{"".join(head)}</svg>', "".join(out)


def _sum(projects: list[dict], role: str, field: str, n: int = 12, only_plan: bool = False) -> list[float]:
    ps = [p for p in projects if p.get("pva") and (p["has_plan"] or not only_plan)]
    return [sum((p["pva"].get(role) or {}).get(field, [0] * 12)[i] for p in ps) for i in range(n)]


def capacity_svg(projects: list[dict], capacity: list[int], latest_month: int, lang: str) -> str:
    cl = [p for p in projects if p.get("pva")]; wp = [p for p in cl if p["has_plan"]]
    act = [a + b for a, b in zip(_sum(cl, "BU RD", "actual", latest_month), _sum(cl, "PM", "actual", latest_month))]
    fu = _sum(cl, "FU RD", "actual", latest_month)
    plan = [a + b for a, b in zip(_sum(wp, "BU RD", "plan", only_plan=True), _sum(wp, "PM", "plan", only_plan=True))]
    W, H, pl, pb = 1100, 300, 40, 30; cw = (W - pl - 20) / 12
    mx = max(act + plan + capacity + [1]) * 1.12
    y = lambda v: H - pb - v / mx * (H - pb - 20); X = lambda i: pl + i * cw + cw / 2
    line = lambda arr, c, dash, w: f'<polyline fill="none" stroke="{c}" stroke-width="{w}" {f"stroke-dasharray=\"{dash}\"" if dash else ""} points="{" ".join(f"{X(i):.1f},{y(v):.1f}" for i, v in enumerate(arr))}"/>'
    ends = lambda arr, c, dy: "".join(f'<text x="{X(i):.1f}" y="{y(v)+dy:.1f}" font-size="11" text-anchor="middle" fill="{c}">{v:.0f}</text>' for i, v in enumerate(arr) if i in (0, len(arr) - 1))
    grid = "".join(f'<line x1="{pl}" x2="{W-10}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{GRID}"/><text x="{pl-6}" y="{y(v)+4:.1f}" font-size="11" text-anchor="end" fill="{INK3}">{v}</text>' for v in (50, 100, 150, 200, 250) if v < mx)
    fut = f'<rect x="{X(latest_month) - cw/2:.1f}" y="10" width="{cw*(12-latest_month):.1f}" height="{H-pb-10}" fill="#eceeeb"/>' if latest_month < 12 else ""
    note = f'<text x="{X(min(11, latest_month + 1)):.1f}" y="26" font-size="11" text-anchor="middle" fill="{INK2}">{escape(t(lang, "cap_budget_note", covered=len(wp), total=len(cl)))}</text>'
    axis = "".join(f'<text x="{X(i):.1f}" y="{H-8}" font-size="12" text-anchor="middle" fill="{INK2}">{m}</text>' for i, m in enumerate(MONTHS))
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" role="img">{grid}{fut}{note}'
            f'{line(capacity, INK, "5 4", 1.5)}{line(act, SLATE, None, 2.5)}{line(plan, SLATE, "3 4", 1.5)}{line(fu, TEAL, None, 2)}'
            f'{ends(capacity, INK, -9)}{ends(act, SLATE, 18)}{ends(fu, TEAL, -8)}{axis}</svg>')


def pva_svg(pva: dict, role: str, latest_month: int) -> str:
    v = pva.get(role) or {}; plan, act = v.get("plan", [0] * 12), v.get("actual", [0] * 12)
    W, H, pl = 360, 120, 10; cw = (W - pl) / 12; mx = max(plan + act + [0.1]); y = lambda q: H - 20 - q / mx * (H - 30)
    c = TEAL if role == "FU RD" else SLATE; out = []
    for i, m in enumerate(MONTHS):
        out.append(f'<rect x="{pl+i*cw+3:.1f}" y="{y(plan[i]):.1f}" width="{cw*0.35:.1f}" height="{H-20-y(plan[i]):.1f}" fill="{SLATE2}"/>')
        if i < latest_month:
            out.append(f'<rect x="{pl+i*cw+3+cw*0.38:.1f}" y="{y(act[i]):.1f}" width="{cw*0.45:.1f}" height="{H-20-y(act[i]):.1f}" fill="{c}"/>')
        out.append(f'<text x="{pl+i*cw+cw/2:.1f}" y="{H-6}" font-size="10" text-anchor="middle" fill="{INK3}">{m}</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img">{"".join(out)}</svg>'
