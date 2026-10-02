"""快照 → 圖（Chart）。只讀 snapshot dict；數字全部在這裡算好，圖與資料表共用同一份結果。"""
from __future__ import annotations
import datetime as dt
from types import SimpleNamespace
from ...entities import INACTIVE, MONTHS
from ...model.rules import mp_slipped
from ..charts import _add_months, _sum, carry_forward
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


def load_heatmap(snap: dict, lang: str, spare_pct: float, by: str = "function") -> Chart:
    """負載 = Σallocated ÷ Σkeyed_in。無人填報（Σkeyed_in = 0）的格放在第二個 series，灰底、不寫 0%。"""
    loads = snap["loads"]
    if by == "function":
        groups: dict[str, list[dict]] = {}
        for r in loads:
            groups.setdefault((r.get("function") or "").strip() or "(none)", []).append(r)
        keys = sorted(groups, key=str.casefold)
        names = {k: k for k in keys}
        cid, title, first = "heat-function", t(lang, "v_c_heat"), t(lang, "col_function")
    else:
        ordered = sorted(loads, key=lambda r: ((r.get("function") or "").casefold(), r["dept_code"]))
        groups = {r["dept_code"]: [r] for r in ordered}
        keys = list(groups)
        names = {r["dept_code"]: f'{r.get("function") or "–"}  {r["dept_name"]}' for r in ordered}
        cid, title, first = "heat-dept", t(lang, "v_c_heat_dept"), t(lang, "col_dept")
    ypos = {k: len(keys) - 1 - i for i, k in enumerate(keys)}          # 第一個在最上面
    cells, nodata, table = [], [], []
    for k in keys:
        pcts = []
        for m in range(12):
            kin = sum(r["keyed_in"][m] or 0 for r in groups[k])
            alloc = sum(r["allocated"][m] or 0 for r in groups[k])
            if kin <= 0:
                nodata.append([m, ypos[k], 0]); pcts.append(None)
            else:
                v = round(alloc / kin * 100); cells.append([m, ypos[k], v]); pcts.append(v)
        table.append((names[k], *pcts))
    option = {"grid": {"left": 8, "right": 8, "top": 8, "bottom": 46, "containLabel": True}, "tooltip": {"position": "top"},
              "xAxis": {"type": "category", "data": list(MONTHS), "axisTick": {"show": False}, "axisLabel": {"color": T.INK2}},
              "yAxis": {"type": "category", "data": [names[k] for k in reversed(keys)], "axisTick": {"show": False}, "axisLabel": {"color": T.INK}},
              "visualMap": {"type": "piecewise", "seriesIndex": 0, "orient": "horizontal", "left": "center", "bottom": 0,
                            "itemWidth": 12, "itemHeight": 12, "textStyle": {"color": T.INK2},
                            "pieces": [{"lt": spare_pct, "label": f"<{spare_pct:g}%", "color": T.HEAT_LOW},
                                       {"gte": spare_pct, "lt": T.HEAT_HIGH, "label": f"{spare_pct:g}-{T.HEAT_HIGH - 1}%", "color": T.HEAT_MID},
                                       {"gte": T.HEAT_HIGH, "label": f">={T.HEAT_HIGH}%", "color": T.HEAT_HI}]},
              "series": [{"type": "heatmap", "data": cells, "label": {"show": True, "formatter": "{@[2]}%", "fontSize": 10, "color": T.INK},
                          "itemStyle": {"borderColor": "#fff", "borderWidth": 2}},
                         {"type": "heatmap", "name": t(lang, "v_no_data"), "data": nodata, "label": {"show": False},
                          "itemStyle": {"color": T.NODATA, "borderColor": "#fff", "borderWidth": 2}, "tooltip": {"formatter": t(lang, "v_no_data")}}]}
    return Chart(cid, title, option, (first, *MONTHS), tuple(table), height=24 * len(keys) + 80, note=t(lang, "v_heat_note"))


def forecast_capacity(snap: dict, lang: str) -> Chart:
    """與舊 capacity_svg 同口徑：actual／plan＝有 Control List 的專案 BU RD＋PM；plan 只算 has_plan 的專案；最新月之後的人數沿用最新月（虛線）。"""
    ps, lm = snap["projects"], snap["meta"]["latest_month"]
    raw = snap["capacity"]
    cap = carry_forward(raw, lm)
    cl = [p for p in ps if p.get("pva")]
    wp = [p for p in cl if p["has_plan"]]
    add = lambda a, b: [round(x + y, 2) for x, y in zip(a, b)]  # noqa: E731
    actual = add(_sum(cl, "BU RD", "actual", lm), _sum(cl, "PM", "actual", lm))
    plan = add(_sum(wp, "BU RD", "plan", only_plan=True), _sum(wp, "PM", "plan", only_plan=True))
    fu = [round(v, 2) for v in _sum(cl, "FU RD", "actual", lm)]
    pad = lambda xs: xs + [None] * (12 - len(xs))  # noqa: E731
    mon = MONTHS[lm - 1]
    series = [{"name": t(lang, "v_lg_cap"), "type": "line", "data": [v if i < lm else None for i, v in enumerate(cap)], "symbol": "none",
               "lineStyle": {"color": T.INK, "width": 2.5}, "itemStyle": {"color": T.INK}},
              {"name": t(lang, "v_lg_cap_carried", mon=mon), "type": "line", "data": [v if i >= lm - 1 else None for i, v in enumerate(cap)],
               "symbol": "none", "lineStyle": {"color": T.INK, "width": 2, "type": "dashed"}, "itemStyle": {"color": T.INK}},
              {"name": t(lang, "v_lg_actual"), "type": "bar", "data": pad(actual), "barWidth": "45%", "itemStyle": {"color": T.ACCENT}},
              {"name": t(lang, "v_lg_plan"), "type": "line", "data": plan, "symbol": "circle", "symbolSize": 5,
               "lineStyle": {"color": T.PLAN, "type": "dashed", "width": 2}, "itemStyle": {"color": T.PLAN}},
              {"name": t(lang, "v_lg_fu"), "type": "line", "data": pad(fu), "symbol": "none", "lineStyle": {"color": T.FU, "width": 2},
               "itemStyle": {"color": T.FU}}]
    option = {"grid": {"left": 8, "right": 12, "top": 16, "bottom": 64, "containLabel": True}, "tooltip": {"trigger": "axis"},
              "legend": {"bottom": 0, "itemWidth": 14, "itemHeight": 8, "textStyle": {"color": T.INK2, "fontSize": 11}},
              "xAxis": {"type": "category", "data": list(MONTHS), "axisTick": {"show": False}, "axisLabel": {"color": T.INK2}},
              "yAxis": {"type": "value", "splitLine": {"lineStyle": {"color": T.RULE}}, "axisLabel": {"color": T.INK3}}, "series": series}
    rows = tuple((m, raw[i] if i < lm else None, actual[i] if i < lm else None, plan[i] if wp else None, fu[i] if i < lm else None)
                 for i, m in enumerate(MONTHS))
    return Chart("forecast", t(lang, "v_c_forecast"), option,
                 (t(lang, "v_col_month"), t(lang, "v_lg_cap"), t(lang, "v_lg_actual"), t(lang, "v_lg_plan"), t(lang, "v_lg_fu")), rows,
                 height=300, note=t(lang, "cap_budget_note", covered=len(wp), total=len(cl)))


def pva(p: dict, role: str, latest_month: int, lang: str, idx: int) -> Chart:
    v = (p.get("pva") or {}).get(role) or {}
    plan = [round(x, 2) for x in v.get("plan", [0.0] * 12)]
    act = [round(x, 2) for x in v.get("actual", [0.0] * 12)]
    has_plan = any(plan)
    series = [{"name": t(lang, "v_lg_pva_actual"), "type": "bar", "data": [a if i < latest_month else None for i, a in enumerate(act)],
               "barWidth": "50%", "itemStyle": {"color": T.FU if role == "FU RD" else T.ACCENT}}]
    if has_plan:
        series.append({"name": t(lang, "v_lg_pva_plan"), "type": "line", "data": plan, "symbol": "circle", "symbolSize": 4,
                       "lineStyle": {"color": T.PLAN, "type": "dashed"}, "itemStyle": {"color": T.PLAN}})
    option = {"grid": {"left": 4, "right": 4, "top": 24, "bottom": 4, "containLabel": True}, "tooltip": {"trigger": "axis"},
              "legend": {"top": 0, "right": 0, "itemWidth": 10, "itemHeight": 6, "textStyle": {"fontSize": 10, "color": T.INK2}},
              "xAxis": {"type": "category", "data": list(MONTHS), "axisTick": {"show": False}, "axisLabel": {"fontSize": 10, "color": T.INK3, "interval": 1}},
              "yAxis": {"type": "value", "splitLine": {"lineStyle": {"color": T.RULE}}, "axisLabel": {"fontSize": 10, "color": T.INK3}}, "series": series}
    rows = tuple((m, act[i] if i < latest_month else None, plan[i] if has_plan else None) for i, m in enumerate(MONTHS))
    return Chart(f"pva-{idx}-{role.lower().replace(' ', '')}", role, option,
                 (t(lang, "v_col_month"), t(lang, "v_lg_pva_actual"), t(lang, "v_lg_pva_plan")), rows, height=150,
                 note="" if has_plan else t(lang, "v_pva_no_plan"))
