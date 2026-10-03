"""單一專案的衍生數字（單案頁與專案列表共用）。只讀快照的 project dict；沒有資料就回 None，不補 0。"""
from __future__ import annotations
import datetime as dt
from html import escape
from ...entities import MONTHS
from ..strings import t
from . import tokens as T
from .embed import Chart

MILESTONES = ("evt", "dvt", "pvt", "mp")


def _days(a: str, b: str) -> int:
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def next_milestone(p: dict, today: str) -> dict | None:
    """Briefing 上第一個 >= today 的里程碑。"""
    for k in MILESTONES:
        d = p["dates"].get(k)
        if d and d >= today:
            return {"key": k, "date": d, "days": _days(today, d)}
    return None


def plan_to_date(p: dict, lm: int) -> tuple[float, float] | None:
    """(Jan..lm 的 plan 合計, 同期 actual 合計)，跨 BU RD / FU RD / PM。沒有 Control List 或 plan 全為 0 → None（未知，不是 0%）。"""
    pva = p.get("pva") or {}
    plan = sum(sum(v.get("plan", [])[:lm]) for v in pva.values())
    if not pva or plan <= 0:
        return None
    return round(plan, 2), round(sum(sum(v.get("actual", [])[:lm]) for v in pva.values()), 2)


def pva_line(v: dict, lm: int, lang: str) -> str:
    """單一角色的 plan vs actual 一句話：同期（Jan..lm）相比，全年 plan 另列。"""
    plan, act, full = sum(v.get("plan", [])[:lm]), sum(v.get("actual", [])[:lm]), sum(v.get("plan", []))
    if full <= 0:
        return t(lang, "pva_line_noplan", mon=MONTHS[lm - 1], actual=f"{act:.1f}")
    return t(lang, "pva_line", mon=MONTHS[lm - 1], plan=f"{plan:.1f}", actual=f"{act:.1f}", full=f"{full:.1f}")


def sparkline_svg(values: list[float], lm: int, w: int = 88, h: int = 22) -> str:
    """Jan..lm 的 FTE 迷你折線（伺服器端畫好的 SVG，62 列不各開一個 ECharts）。<title> 給逐月數字。"""
    vs = [float(v or 0) for v in values[:lm]] or [0.0]
    top = max(vs) or 1.0
    step = (w - 4) / max(len(vs) - 1, 1)
    pts = " ".join(f"{2 + i * step:.1f},{h - 2 - (v / top) * (h - 4):.1f}" for i, v in enumerate(vs))
    tip = ", ".join(f"{MONTHS[i]} {v:.1f}" for i, v in enumerate(vs))
    return (f'<svg class="spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(tip)}"><title>{escape(tip)}</title>'
            f'<polyline points="{pts}" fill="none" stroke="{T.ACCENT}" stroke-width="1.5" stroke-linejoin="round"/></svg>')


def task_groups(tasks: list[dict], month: int) -> list[dict]:
    """某月任務依 (Side, Function) 彙總；同一段任務文字合併成一項，列出部門與合計 FTE。BU 在前，各組依 FTE 由大到小。"""
    groups: dict[tuple[str, str], dict] = {}
    for x in tasks:
        if x["month"] != month:
            continue
        g = groups.setdefault((x["side"], x["function"]), {"side": x["side"], "function": x["function"], "fte": 0.0, "_depts": [], "_items": {}})
        g["fte"] += x["fte"]
        if x["dept"] not in g["_depts"]:
            g["_depts"].append(x["dept"])
        it = g["_items"].setdefault(x["description"], {"text": x["description"], "fte": 0.0, "depts": []})
        it["fte"] += x["fte"]
        if x["dept"] not in it["depts"]:
            it["depts"].append(x["dept"])
    out = [{"side": g["side"], "function": g["function"], "fte": g["fte"], "depts": len(g["_depts"]),
            "items": sorted(g["_items"].values(), key=lambda i: -i["fte"])} for g in groups.values()]
    return sorted(out, key=lambda g: (g["side"] != "BU", -g["fte"]))


def _change(lang: str, d: int | None) -> str:
    return "–" if d is None else t(lang, "v_days_change", d=f"{d:+d}" if d else "0")


def mp_drift(p: dict, lang: str) -> Chart | None:
    """每份 Briefing 快照填的 MP 日期（階梯線）對照原訂 MP（虛線）。沒有任何一份有 MP 日期 → None。"""
    hist = [h for h in p.get("history") or [] if h.get("snap")]
    pts = [h for h in hist if h.get("mp")]
    if not pts:
        return None
    iso = lambda s: f"{s[:4]}-{s[4:6]}-{s[6:]}"  # noqa: E731
    orig, now = p["dates"].get("mp_orig"), pts[-1]["mp"]
    data = [{"value": [iso(h["snap"]), h["mp"]], "name": t(lang, "v_drift_tip", snap=iso(h["snap"]), mp=h["mp"], stage=h.get("stage") or "–")} for h in pts]
    data[-1]["label"] = {"show": True, "formatter": f"MP {now}", "position": "top", "align": "right", "distance": 8, "color": T.INK, "fontWeight": 600}
    series = {"type": "line", "step": "end", "data": data, "symbolSize": 6, "lineStyle": {"color": T.MS_COLORS["mp"], "width": 2},
              "itemStyle": {"color": T.MS_COLORS["mp"]}}
    if orig:
        series["markLine"] = {"symbol": "none", "silent": True, "lineStyle": {"type": "dashed", "color": T.INK3},
                              "label": {"formatter": t(lang, "v_drift_orig", d=orig), "position": "insideStartTop", "color": T.INK2},
                              "data": [{"yAxis": orig}]}
    option = {"grid": {"left": 4, "right": 24, "top": 28, "bottom": 4, "containLabel": True}, "tooltip": {"trigger": "item", "formatter": "{b}"},
              "xAxis": {"type": "time", "axisLabel": {"fontSize": 10, "color": T.INK3}, "splitLine": {"show": False}},
              "yAxis": {"type": "time", "scale": True, "axisLabel": {"fontSize": 10, "color": T.INK3}, "splitLine": {"lineStyle": {"color": T.RULE}},
                        **({"min": min(orig, pts[0]["mp"])} if orig else {})},
              "series": [series]}
    rows, prev = [], None
    for h in hist:
        mp = h.get("mp")
        rows.append((iso(h["snap"]), h.get("stage") or "–", mp or "–", _change(lang, _days(prev, mp) if prev and mp else None)))
        prev = mp or prev
    head = t(lang, "v_drift_head", now=now, d=f"{_days(orig, now):+d}", orig=orig) if orig else t(lang, "v_drift_head_noorig", now=now)
    return Chart("mp-drift", t(lang, "v_drift_title"), option,
                 (t(lang, "v_col_briefing"), t(lang, "v_col_stage"), "MP", t(lang, "v_col_change")), tuple(rows), height=220, headline=head,
                 note=t(lang, "v_drift_note", a=iso(hist[0]["snap"]), b=iso(hist[-1]["snap"])))
