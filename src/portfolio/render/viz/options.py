"""快照 → 圖（Chart）。只讀 snapshot dict；數字全部在這裡算好，圖與資料表共用同一份結果。"""
from __future__ import annotations
import datetime as dt
from types import SimpleNamespace
from ...entities import INACTIVE
from ...model.rules import mp_slipped
from ..charts import _add_months
from ..strings import t
from . import tokens as T
from .embed import Chart

STAGE_ORDER = ("RFQ / RFI", "POC", "Execution", "MP", "Sustain / EOP", "Terminated", "Suspended", "Other")


def late_codes(snap: dict) -> set[str]:
    return {c for x in snap.get("exceptions", []) if x["title"] == "milestones_passed" for c in x["codes"]}


def at_risk_codes(snap: dict, mp_slip_days: int) -> list[str]:
    """不是新規則：Decisions 的 milestones_passed ∪ 健康度的 mp_slipped（同一個 rules 函式）。"""
    passed = [c for x in snap.get("exceptions", []) if x["title"] == "milestones_passed" for c in x["codes"]]
    slipped = [p.code for p, _ in mp_slipped([SimpleNamespace(**p) for p in snap["projects"]], mp_slip_days)]
    return list(dict.fromkeys(passed + slipped))


def kpis(snap: dict, lang: str, th: dict) -> list[dict]:
    ps = snap["projects"]
    cat = lambda c: sum(1 for p in ps if p["stage_cat"] == c)  # noqa: E731
    risk = at_risk_codes(snap, th["mp_slip_days"])
    k = lambda key, label, value, sub="", tone="": {"key": key, "label": label, "value": value, "sub": sub, "tone": tone}  # noqa: E731
    return [k("total", t(lang, "v_kpi_total"), len(ps), t(lang, "v_kpi_total_sub", briefed=sum(1 for p in ps if p["in_briefing"]),
                                                          inactive=sum(1 for p in ps if p["stage_cat"] in INACTIVE))),
            k("rfq", t(lang, "v_kpi_rfq"), cat("RFQ / RFI")), k("poc", t(lang, "v_kpi_poc"), cat("POC")),
            k("exec", t(lang, "v_kpi_exec"), cat("Execution")),
            k("mp", t(lang, "v_kpi_mp"), cat("MP") + cat("Sustain / EOP"), t(lang, "v_kpi_mp_sub", mp=cat("MP"), sustain=cat("Sustain / EOP"))),
            {**k("risk", t(lang, "v_kpi_risk"), len(risk), t(lang, "v_kpi_risk_sub", days=th["mp_slip_days"]), "bad" if risk else ""), "codes": risk}]


def _stage_key(p: dict) -> str:
    if not p["in_briefing"]:
        return T.NOT_IN_BRIEFING
    return p["stage_cat"] or "Other"


def stage_donut(snap: dict, lang: str) -> Chart:
    counts: dict[str, int] = {}
    for p in snap["projects"]:
        key = _stage_key(p)
        counts[key] = counts.get(key, 0) + 1
    known = (*STAGE_ORDER, T.NOT_IN_BRIEFING)
    order = [k for k in known if counts.get(k)] + sorted(k for k in counts if k not in known)
    label = lambda k: t(lang, "v_cat_not_in_briefing") if k == T.NOT_IN_BRIEFING else k  # noqa: E731
    total = len(snap["projects"])
    data = [{"name": f"{label(k)}  {counts[k]}", "value": counts[k], "itemStyle": {"color": T.STAGE_COLORS.get(k, T.INK3)}} for k in order]
    option = {"tooltip": {"trigger": "item", "formatter": "{b} ({d}%)"},
              "legend": {"orient": "vertical", "right": 0, "top": "middle", "itemWidth": 10, "itemHeight": 10, "textStyle": {"color": T.INK2}},
              "title": {"text": str(total), "subtext": t(lang, "v_total"), "left": "29%", "top": "36%", "textAlign": "center",
                        "textStyle": {"fontSize": 26, "fontWeight": 700, "color": T.INK}, "subtextStyle": {"color": T.INK2}},
              "series": [{"type": "pie", "radius": ["52%", "74%"], "center": ["30%", "50%"], "label": {"show": False}, "data": data}]}
    rows = tuple((label(k), counts[k], f"{counts[k] / max(total, 1) * 100:.0f}%") for k in order)
    return Chart("stage", t(lang, "v_c_stage"), option, (t(lang, "col_stage"), t(lang, "v_col_projects"), "%"), rows, height=240)


def customer_bars(snap: dict, lang: str, top: int = 8) -> Chart:
    counts: dict[str, int] = {}
    for p in snap["projects"]:
        c = (p.get("customer") or "").strip() or t(lang, "v_cat_blank")
        counts[c] = counts.get(c, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].casefold()))
    head = list(ranked[:top])
    if ranked[top:]:
        head.append((t(lang, "v_cat_others"), sum(n for _, n in ranked[top:])))
    option = {"grid": {"left": 8, "right": 36, "top": 4, "bottom": 4, "containLabel": True}, "tooltip": {"trigger": "item"},
              "xAxis": {"type": "value", "show": False},
              "yAxis": {"type": "category", "data": [k for k, _ in head][::-1], "axisTick": {"show": False}, "axisLine": {"show": False},
                        "axisLabel": {"color": T.INK}},
              "series": [{"type": "bar", "data": [n for _, n in head][::-1], "barWidth": 12, "itemStyle": {"color": T.ACCENT, "borderRadius": [0, 3, 3, 0]},
                          "label": {"show": True, "position": "right", "color": T.INK}}]}
    return Chart("customer", t(lang, "v_c_customer"), option, (t(lang, "col_customer"), t(lang, "v_col_projects")), tuple(head),
                 height=max(160, 26 * len(head) + 20))


MS = ("evt", "dvt", "pvt", "mp")
SYMBOL = {"evt": "emptyRect", "dvt": "rect", "pvt": "triangle", "mp": "circle"}


def _ms(iso: str) -> int:
    """日期 → UTC 午夜毫秒（ECharts time 軸）。"""
    return int(dt.datetime.fromisoformat(iso[:10]).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def _gantt_rows(snap: dict, today: str, months: int) -> tuple[dt.date, dt.date, list[dict]]:
    """與舊 timeline_svg 同一個選列條件：在 Briefing、非結案／暫停，且視窗內有里程碑，或是還沒有 MP 日期的 RFQ / RFI。"""
    t0 = dt.date.fromisoformat(today[:7] + "-01")
    t1 = _add_months(t0, months)
    in_win = lambda s: bool(s) and t0 <= dt.date.fromisoformat(s) < t1  # noqa: E731
    rows = [p for p in snap["projects"] if p["in_briefing"] and p["stage_cat"] not in INACTIVE
            and (any(in_win(p["dates"].get(k)) for k in MS) or (p["stage_cat"] == "RFQ / RFI" and not p["dates"].get("mp")))]
    rows.sort(key=lambda p: (p["dates"].get("mp") or p["dates"].get("pvt") or p["dates"].get("dvt") or p["dates"].get("evt") or "9", p["name"].casefold()))
    return t0, t1, rows


def _gantt_option(rows: list[dict], t0: dt.date, t1: dt.date, today: str, late: set[str], lang: str) -> dict:
    n = len(rows)
    bars, marks = [], []
    for i, p in enumerate(rows):
        y = n - 1 - i
        ds = [p["dates"][k] for k in ("kickoff", *MS) if p["dates"].get(k)]
        if len(ds) >= 2:
            bars.append([y, _ms(min(ds)), _ms(max(ds))])
        for k in MS:
            d = p["dates"].get(k)
            if not d or not t0 <= dt.date.fromisoformat(d) < t1:
                continue
            c = T.BAD if p["code"] in late and d < today else T.ACCENT
            marks.append({"value": [_ms(d), y], "symbol": SYMBOL[k], "symbolSize": 10, "itemStyle": {"color": c, "borderColor": c},
                          "label": {"show": True, "position": "right", "formatter": f"{k.upper()} {d[5:7]}/{d[8:10]}", "color": c, "fontSize": 11}})
        if not ds:
            marks.append({"value": [_ms(today), y], "symbol": "none",
                          "label": {"show": True, "position": "right", "formatter": t(lang, "no_dates", stage=p["stage"]), "color": T.INK3, "fontSize": 11}})
    return {"grid": {"left": 8, "right": 90, "top": 28, "bottom": 8, "containLabel": True}, "tooltip": {"trigger": "item"},
            "xAxis": {"type": "time", "position": "top", "min": _ms(t0.isoformat()), "max": _ms(t1.isoformat()),
                      "splitLine": {"show": True, "lineStyle": {"color": T.RULE}}, "axisLabel": {"color": T.INK2}},
            "yAxis": {"type": "category", "data": [p["name"] for p in rows][::-1], "axisTick": {"show": False},
                      "axisLabel": {"color": T.INK, "fontWeight": 600}},
            "series": [{"type": "custom", "renderItem": {"$fn": "ganttBar"}, "encode": {"x": [1, 2], "y": 0}, "data": bars,
                        "itemStyle": {"color": T.ACCENT}, "clip": True, "silent": True},
                       {"type": "scatter", "data": marks, "clip": True, "z": 3,
                        "markLine": {"silent": True, "symbol": "none", "lineStyle": {"color": T.INK, "type": "dashed"},
                                     "label": {"formatter": t(lang, "v_today"), "color": T.INK2}, "data": [{"xAxis": _ms(today)}]}}]}


def gantt(snap: dict, lang: str, today: str, months: int) -> Chart:
    t0, t1, rows = _gantt_rows(snap, today, months)
    late = late_codes(snap)
    customers = sorted({p["customer"] for p in rows if p["customer"]}, key=str.casefold)
    variants = {c: _gantt_option([p for p in rows if p["customer"] == c], t0, t1, today, late, lang) for c in customers}
    table = tuple((p["name"], p["customer"], p["stage"], *(p["dates"].get(k) or "" for k in MS)) for p in rows)
    return Chart("gantt", t(lang, "v_c_gantt", months=months), _gantt_option(rows, t0, t1, today, late, lang),
                 (t(lang, "col_project"), t(lang, "col_customer"), t(lang, "col_stage"), "EVT", "DVT", "PVT", "MP"), table,
                 height=max(160, 30 * len(rows) + 50), variants=variants, note=t(lang, "v_gantt_note"))
