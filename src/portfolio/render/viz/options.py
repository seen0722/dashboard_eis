"""快照 → 圖（Chart）。只讀 snapshot dict；數字全部在這裡算好，圖與資料表共用同一份結果。"""
from __future__ import annotations
import datetime as dt
from html import escape
from types import SimpleNamespace
from ...entities import INACTIVE, MONTHS
from ...model.rules import milestones_passed, mp_slipped
from ..charts import _add_months, _sum, carry_forward
from ..strings import t
from . import tokens as T
from .embed import Chart

SHIPPED = ("MP", "Sustain / EOP")
STAGE_ORDER = ("RFQ / RFI", "POC", "Execution", "MP", "Sustain / EOP", "Terminated", "Suspended", "Other")


def late_codes(snap: dict) -> set[str]:
    return {c for x in snap.get("exceptions", []) if x["title"] == "milestones_passed" for c in x["codes"]}


def at_risk_codes(snap: dict, mp_slip_days: int) -> list[str]:
    """不是新規則：Decisions 的 milestones_passed ∪ 健康度的 mp_slipped（同一個 rules 函式），
    但 mp_slipped 只算尚未量產的：已在 MP / Sustain 的延後是歷史，沒有 action（使用者 2026-10-03 拍板），只留在健康度。"""
    passed = [c for x in snap.get("exceptions", []) if x["title"] == "milestones_passed" for c in x["codes"]]
    slipped = [p.code for p, _ in mp_slipped([SimpleNamespace(**p) for p in snap["projects"]], mp_slip_days) if p.stage_cat not in SHIPPED]
    return list(dict.fromkeys(passed + slipped))


def at_risk_rows(snap: dict, mp_slip_days: int) -> list[dict]:
    """At Risk 每一案為何列入：與 at_risk_codes 同一份名單，逐案附命中的規則與日期。
    「已過」的天數以快照產生日（generated，例外清單算的那一天）計；重算不到的只寫規則名，不補日期。"""
    ps = [SimpleNamespace(**p) for p in snap["projects"]]
    today = snap["meta"].get("generated", "")
    passed = {p.code: (ms, d, n) for p, ms, d, n in (milestones_passed(ps, today) if today else [])}
    slipped = {p.code: n for p, n in mp_slipped(ps, mp_slip_days)}
    late = late_codes(snap)
    by = {p["code"]: p for p in snap["projects"]}
    out = []
    for c in at_risk_codes(snap, mp_slip_days):
        p = by.get(c, {"code": c, "name": c, "stage": "", "stage_cat": "", "dates": {}})
        why = []
        if c in late:
            why.append({"rule": "passed", **({"ms": passed[c][0].upper(), "date": passed[c][1], "days": passed[c][2]} if c in passed else {})})
        if c in slipped:
            why.append({"rule": "slipped", "orig": p["dates"].get("mp_orig"), "mp": p["dates"].get("mp"), "days": slipped[c]})
        out.append({"code": c, "name": p["name"], "stage": p["stage"], "why": why})
    return out


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
              "title": {"text": str(total), "subtext": t(lang, "v_total"), "left": "center", "top": "34%",
                        "textStyle": {"fontSize": 20, "fontWeight": 700, "color": T.INK}, "subtextStyle": {"color": T.INK2}},
              "series": [{"type": "pie", "radius": ["58%", "82%"], "center": ["50%", "50%"], "label": {"show": False}, "data": data}]}
    rows = tuple((label(k), counts[k], f"{counts[k] / max(total, 1) * 100:.0f}%") for k in order)
    return Chart("stage", t(lang, "v_c_stage"), option, (t(lang, "col_stage"), t(lang, "v_col_projects"), "%"), rows, height=128)


def _donut(cid: str, title: str, first_col: str, slices: list[tuple[str, int, str]], total: int, lang: str, note: str = "") -> Chart:
    """slices = [(標籤, 數量, 顏色)]，順序即顯示順序。與 stage_donut 同一個版型。"""
    data = [{"name": f"{k}  {n}", "value": n, "itemStyle": {"color": c}} for k, n, c in slices]
    option = {"tooltip": {"trigger": "item", "formatter": "{b} ({d}%)"},
              "title": {"text": str(total), "subtext": t(lang, "v_total"), "left": "center", "top": "34%",
                        "textStyle": {"fontSize": 20, "fontWeight": 700, "color": T.INK}, "subtextStyle": {"color": T.INK2}},
              "series": [{"type": "pie", "radius": ["58%", "82%"], "center": ["50%", "50%"], "label": {"show": False}, "data": data}]}
    rows = tuple((k, n, f"{n / max(total, 1) * 100:.0f}%") for k, n, _ in slices)
    return Chart(cid, title, option, (first_col, t(lang, "v_col_projects"), "%"), rows, height=128, note=note)


def _briefing_field_counts(snap: dict, field: str) -> tuple[dict[str, int], int, int]:
    """Briefing 內各值的計數；空白與不在 Briefing 分開數，不參與排名。"""
    counts: dict[str, int] = {}
    blank = outside = 0
    for p in snap["projects"]:
        if not p["in_briefing"]:
            outside += 1
            continue
        v = (p.get(field) or "").strip()
        if not v:
            blank += 1
        else:
            counts[v] = counts.get(v, 0) + 1
    return counts, blank, outside


def _tail_slices(blank: int, outside: int, lang: str) -> list[tuple[str, int, str]]:
    return ([(t(lang, "v_cat_blank"), blank, T.INK3)] if blank else []) + \
           ([(t(lang, "v_cat_not_in_briefing"), outside, T.STAGE_COLORS[T.NOT_IN_BRIEFING])] if outside else [])


def category_donut(snap: dict, lang: str, top: int = 7) -> Chart:
    """Briefing 的 Category 欄（2026-09 改版後新增）。前 top 類以外併成 Others，並在圖下寫明 Others 含哪些。"""
    counts, blank, outside = _briefing_field_counts(snap, "category")
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].casefold()))
    head, rest = ranked[:top], ranked[top:]
    slices = [(k, n, T.PALETTE[i % len(T.PALETTE)]) for i, (k, n) in enumerate(head)]
    note = ""
    if rest:
        slices.append((t(lang, "v_cat_others"), sum(n for _, n in rest), "#CBD5E1"))
        note = t(lang, "v_others_note", names=", ".join(k for k, _ in sorted(rest, key=lambda kv: kv[0].casefold())))
    slices += _tail_slices(blank, outside, lang)
    return _donut("category", t(lang, "v_c_category"), t(lang, "v_col_category"), slices, len(snap["projects"]), lang, note)


def type_donut(snap: dict, lang: str) -> Chart:
    """Briefing 的 Type 欄（JDM／ODM／EMS）。"""
    counts, blank, outside = _briefing_field_counts(snap, "biz_type")
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].casefold()))
    slices = [(k, n, T.TYPE_COLORS.get(k, T.PALETTE[i % len(T.PALETTE)])) for i, (k, n) in enumerate(ranked)]
    return _donut("type", t(lang, "v_c_type"), t(lang, "v_col_type"), slices + _tail_slices(blank, outside, lang), len(snap["projects"]), lang)


def customer_bars(snap: dict, lang: str, top: int = 8) -> Chart:
    counts: dict[str, int] = {}
    for p in snap["projects"]:
        # 不在 Briefing 的專案本來就沒有客戶欄：歸成與甜甜圈同一類，(blank) 只留給 Briefing 內真正空白的
        c = t(lang, "v_cat_not_in_briefing") if not p["in_briefing"] else ((p.get("customer") or "").strip() or t(lang, "v_cat_blank"))
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
STAR = "path://M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 21 12 17.27 5.82 21 7 14.14l-5-4.87 6.91-1.01z"
SYMBOL = {"evt": "emptyDiamond", "dvt": "diamond", "pvt": "triangle", "mp": STAR}   # 照 mock：◇ ◆ ▲ ★
MS_SIZE = {"evt": 12, "dvt": 12, "pvt": 11, "mp": 14}
LABEL_GAP_DAYS = 30     # 同一列兩個標記相距不到這麼多天，前一個的標籤改放上方（2/3 寬時會被下一個圓點蓋住）


def _ms(iso: str) -> int:
    """日期 → UTC 午夜毫秒（ECharts time 軸）。"""
    return int(dt.datetime.fromisoformat(iso[:10]).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def _overdue(snap: dict, today: str) -> dict[str, tuple[str, str, int]]:
    """里程碑已過、階段沒推進的專案 → (里程碑, 日期, 逾期天數)。名單取 Decisions 的 milestones_passed（late_codes），
    里程碑與天數用同一個 rules 函式算，與 At Risk 表一致。"""
    late = late_codes(snap)
    return {p.code: (ms, d, n) for p, ms, d, n in milestones_passed([SimpleNamespace(**q) for q in snap["projects"]], today) if p.code in late}


def _reached_mp(p: dict, t0: dt.date, today: str) -> bool:
    """階段已是 MP，且 Briefing 的 MP Date 落在報告月份起點到 Briefing 日之間＝本月進入 MP。"""
    mp = p["dates"].get("mp")
    return p["stage_cat"] == "MP" and bool(mp) and t0.isoformat() <= mp <= today


def _gantt_rows(snap: dict, today: str, months: int, overdue: dict | None = None) -> tuple[dt.date, dt.date, list[dict]]:
    """在 Briefing、非結案／暫停，且視窗內有里程碑，或是還沒有 MP 日期的 RFQ / RFI；
    另外逾期的專案（overdue）一律納入並排最上面——否則逾期越久越會從圖上消失（需求方 2026-10-03，THORPE）。"""
    overdue = overdue or {}
    t0 = dt.date.fromisoformat(today[:7] + "-01")
    t1 = _add_months(t0, months)
    in_win = lambda s: bool(s) and t0 <= dt.date.fromisoformat(s) < t1  # noqa: E731
    # 已量產（MP、Sustain / EOP）通常不列：沒有下一個里程碑可追。例外是「本月進入 MP」——每月 review 要看到它（需求方 2026-10-03，Brandy）
    rows = [p for p in snap["projects"] if p["in_briefing"] and p["stage_cat"] not in INACTIVE
            and (p["stage_cat"] not in SHIPPED or _reached_mp(p, t0, today))
            and (p["code"] in overdue or any(in_win(p["dates"].get(k)) for k in MS) or (p["stage_cat"] == "RFQ / RFI" and not p["dates"].get("mp")))]
    rows.sort(key=lambda p: (p["code"] not in overdue, -overdue[p["code"]][2] if p["code"] in overdue else 0,
                             p["dates"].get("mp") or p["dates"].get("pvt") or p["dates"].get("dvt") or p["dates"].get("evt") or "9", p["name"].casefold()))
    return t0, t1, rows


def _gantt_option(rows: list[dict], t0: dt.date, t1: dt.date, today: str, late: set[str], lang: str, pinned: dict | None = None) -> dict:
    pinned = pinned or {}                                           # 逾期專案 → (里程碑, 日期, 天數)；迴圈內的 overdue 是另一個布林
    n = len(rows)
    bars: dict[str, list] = {k: [] for k in MS}
    marks = []
    for i, p in enumerate(rows):
        y = n - 1 - i
        ds = [p["dates"][k] for k in ("kickoff", *MS) if p["dates"].get(k)]
        seq = sorted((p["dates"][k], k) for k in ("kickoff", *MS) if p["dates"].get(k))
        for (d0, _), (d1, k1) in zip(seq, seq[1:]):          # 每一段依「下一個里程碑」上色（照 mock）
            if k1 != "kickoff" and d1 > d0:
                bars[k1].append([y, _ms(d0), _ms(d1)])
        shown = sorted(p["dates"][k] for k in MS if p["dates"].get(k) and t0 <= dt.date.fromisoformat(p["dates"][k]) < t1)
        for k in MS:
            d = p["dates"].get(k)
            if not d or not t0 <= dt.date.fromisoformat(d) < t1:
                continue
            overdue = p["code"] in late and d < today            # 逾期用紅色粗體標籤表示；圖示顏色只代表里程碑種類
            reached = k == "mp" and _reached_mp(p, t0, today)        # 本月進入 MP：綠色標籤
            c = T.MS_COLORS[k]
            close = any(0 < (dt.date.fromisoformat(x) - dt.date.fromisoformat(d)).days <= LABEL_GAP_DAYS for x in shown)   # 下一個標記太近：標籤放上方
            marks.append({"value": [_ms(d), y], "symbol": SYMBOL[k], "symbolSize": MS_SIZE[k], "itemStyle": {"color": c, "borderColor": c},
                          "tooltip": {"formatter": f"{escape(p['name'])}: {k.upper()} {d}"},   # 預設 tooltip 會顯示時區換算後的時間與內部 y 索引
                          "label": {"show": True, "position": "top" if close else "right",
                                    "formatter": t(lang, "v_gantt_reached", ms=k.upper(), d=f"{d[5:7]}/{d[8:10]}") if reached else f"{k.upper()} {d[5:7]}/{d[8:10]}",
                                    "color": T.BAD if overdue else T.OK if reached else T.INK, "fontWeight": 700 if overdue or reached else 400, "fontSize": 11}})
        od = pinned.get(p["code"])
        if od and dt.date.fromisoformat(od[1]) < t0:                # 逾期的里程碑在圖的左邊界之外：釘在左邊界，標出日期與天數
            ms, d, n_days = od
            label = t(lang, "v_gantt_overdue", ms=ms.upper(), d=f"{d[5:7]}/{d[8:10]}", n=n_days)
            marks.append({"value": [_ms(t0.isoformat()), y], "symbol": SYMBOL[ms], "symbolSize": MS_SIZE[ms],
                          "itemStyle": {"color": T.MS_COLORS[ms], "borderColor": T.MS_COLORS[ms]},
                          "tooltip": {"formatter": f"{escape(p['name'])}: {ms.upper()} {d}, {label}"},
                          "label": {"show": True, "position": "right", "formatter": label, "color": T.BAD, "fontWeight": 700, "fontSize": 11}})
        if not ds:
            marks.append({"value": [_ms(today), y], "symbol": "emptyCircle", "symbolSize": 8, "itemStyle": {"color": T.INK3},   # symbol none 會連標籤一起藏掉
                          "tooltip": {"formatter": f"{escape(p['name'])}: {escape(t(lang, 'no_dates', stage=p['stage']))}"},
                          "label": {"show": True, "position": "right", "formatter": t(lang, "no_dates", stage=p["stage"]), "color": T.INK3, "fontSize": 11}})
    return {"useUTC": True, "grid": {"left": 8, "right": 90, "top": 28, "bottom": 24, "containLabel": True}, "tooltip": {"trigger": "item"},
            "xAxis": {"type": "time", "position": "top", "min": _ms(t0.isoformat()), "max": _ms(t1.isoformat()),
                      "splitLine": {"show": True, "lineStyle": {"color": T.RULE}}, "axisLabel": {"color": T.INK2}},
            "yAxis": {"type": "category", "data": [p["name"] for p in rows][::-1], "axisTick": {"show": False},
                      "axisLabel": {"color": T.INK, "fontWeight": 600}},
            "series": [*({"name": f"to {k.upper()}", "type": "custom", "renderItem": {"$fn": "ganttBar"}, "encode": {"x": [1, 2], "y": 0},
                          "data": bars[k], "itemStyle": {"color": T.MS_COLORS[k]}, "clip": True, "silent": True} for k in MS),
                       {"type": "scatter", "data": marks, "clip": True, "z": 3,
                        "markLine": {"silent": True, "symbol": "none", "lineStyle": {"color": T.BAD, "type": "dashed"},
                                     "label": {"formatter": t(lang, "v_today", d=today[5:].replace("-", "/")), "color": T.INK2, "position": "start"}, "data": [{"xAxis": _ms(today)}]}}]}


def gantt(snap: dict, lang: str, today: str, months: int) -> Chart:
    late = late_codes(snap)
    overdue = _overdue(snap, today)
    t0, t1, rows = _gantt_rows(snap, today, months, overdue)
    customers = sorted({p["customer"] for p in rows if p["customer"]}, key=str.casefold)
    variants = {c: _gantt_option([p for p in rows if p["customer"] == c], t0, t1, today, late, lang, overdue) for c in customers}
    # MP 欄是 Briefing 的「MP Date」（目前預計），旁邊附「Original MP Date」；客戶已在篩選器，不另列（需求方 2026-10-03）
    table = tuple((p["name"], p["stage"], *(p["dates"].get(k) or "" for k in MS), p["dates"].get("mp_orig") or "") for p in rows)
    return Chart("gantt", t(lang, "v_c_gantt", months=months), _gantt_option(rows, t0, t1, today, late, lang, overdue),
                 (t(lang, "col_project"), t(lang, "col_stage"), "EVT", "DVT", "PVT", t(lang, "v_col_mp_current"), t(lang, "v_col_mp_orig")), table,
                 height=max(160, 30 * len(rows) + 50), variants=variants, note=t(lang, "v_gantt_note"), min_width=720,
                 legend=tuple((g, k.upper(), T.MS_COLORS[k]) for g, k in zip(("◇", "◆", "▲", "★"), MS)))


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
    option = {"grid": {"left": 8, "right": 16, "top": 8, "bottom": 46, "containLabel": True}, "tooltip": {"position": "top"},
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
    return Chart(cid, title, option, (first, *MONTHS), tuple(table), height=24 * len(keys) + 80, note=t(lang, "v_heat_note"), min_width=560)


# ---- plan vs actual 的共用設計語言（Forecast、FU、單案 PVA）：actual 長條、plan 紫色短橫、最新月直接標數字、無圖例 ----
def _label_last(values: list, idx: int, text: str, color: str) -> list:
    out = list(values) + [None] * (12 - len(values))
    if 0 <= idx < len(out) and out[idx] is not None:
        out[idx] = {"value": out[idx], "label": {"show": True, "position": "right", "formatter": text, "color": color, "fontWeight": 600}}
    return out


PLAN_FRAC = 0.55       # plan 短橫寬度＝月份格寬的比例（固定像素在寬螢幕上會比長條窄很多）


def _plan_series(name: str, plan: list[float], lang: str, label: bool = True) -> dict:
    """plan 以 custom series 畫短橫（INIT_JS 的 planMark）：寬度隨格寬縮放，最後一個月旁標「Plan N」。"""
    text = f"{t(lang, 'v_fc_plan_label')} {plan[-1]:.0f}" if label and any(plan) else ""
    return {"name": name, "type": "custom", "renderItem": {"$fn": "planMark", "args": [PLAN_FRAC, text, T.PLAN_MARK, len(plan) - 1, T.PLAN_TEXT]},
            "encode": {"x": 0, "y": 1}, "data": [[i, v] for i, v in enumerate(plan)], "itemStyle": {"color": T.PLAN_MARK}, "z": 4}


def _tip(glyphs: list[str], hide: dict | None = None) -> dict:
    """tooltip 圖示與圖上形狀一致（bar／mark／line／dashed），1 位小數；hide = {被隱藏的序號: 有值時就隱藏它的序號}。"""
    return {"trigger": "axis", "formatter": {"$fn": "axisTip", "args": [glyphs, hide or {}, 1]}}


def forecast_capacity(snap: dict, lang: str) -> Chart:
    """BU RD＋PM 的人力去哪了：長條拆成「有 budget 的專案」與「沒有 budget 的專案」兩段（加總＝實際），
    plan 以短橫線標在有 budget 那段上（同一批專案），天花板是 BU 填報人數（最新月之後沿用，虛線）。
    FU RD 不在這張圖：天花板是 BU 人數，FU 的 plan 與 actual 在 fu_plan_actual。"""
    ps, lm = snap["projects"], snap["meta"]["latest_month"]
    raw = snap["capacity"]
    cap = carry_forward(raw, lm)
    cl = [p for p in ps if p.get("pva")]
    wp = [p for p in cl if p["has_plan"]]
    add = lambda a, b: [round(x + y, 2) for x, y in zip(a, b)]  # noqa: E731
    actual = add(_sum(cl, "BU RD", "actual", lm), _sum(cl, "PM", "actual", lm))
    withb = add(_sum(wp, "BU RD", "actual", lm), _sum(wp, "PM", "actual", lm))
    nob = [round(a - w, 2) for a, w in zip(actual, withb)]
    plan = add(_sum(wp, "BU RD", "plan", only_plan=True), _sum(wp, "PM", "plan", only_plan=True))
    mon = MONTHS[lm - 1]

    def bars(values: list[float], short: str, color: str) -> list:
        out = [v for v in values] + [None] * (12 - len(values))
        last = lm - 1
        out[last] = {"value": values[last], "label": {"show": True, "position": "right", "formatter": f"{short} {values[last]:.0f}",
                                                      "color": color, "fontWeight": 600}}
        return out

    # 標籤掛在最後一點；endLabel 遇到前段 null 會在瀏覽器算出 NaN 座標
    carried: list = [v if i >= lm - 1 else None for i, v in enumerate(cap)]
    carried[-1] = {"value": cap[-1], "symbol": "circle", "symbolSize": 5, "label": {"show": True, "position": "top", "align": "right", "formatter": t(lang, "v_fc_cap_assumed", mon=MONTHS[lm - 1], n=f"{cap[-1]:.0f}"), "color": T.INK2}}
    series = [{"name": t(lang, "v_fc_with", n=len(wp)), "type": "bar", "stack": "actual", "barWidth": "45%",
               "data": bars(withb, t(lang, "v_fc_with_short"), T.ACCENT), "itemStyle": {"color": T.ACCENT}},
              {"name": t(lang, "v_fc_without", n=len(cl) - len(wp)), "type": "bar", "stack": "actual",
               "data": bars(nob, t(lang, "v_fc_without_short"), T.SIGNAL), "itemStyle": {"color": T.SIGNAL}},
              _plan_series(t(lang, "v_lg_plan"), plan, lang, label=bool(wp)),
              {"name": t(lang, "v_lg_cap"), "type": "line", "data": [v if i < lm else None for i, v in enumerate(cap)], "symbol": "none",
               "lineStyle": {"color": T.INK, "width": 2.5}, "itemStyle": {"color": T.INK}},
              {"name": t(lang, "v_lg_cap_carried", mon=mon), "type": "line", "data": carried, "symbol": "none",
               "lineStyle": {"color": T.INK, "width": 2, "type": "dashed"}, "itemStyle": {"color": T.INK}}]
    # tooltip 圖示與圖上形狀一致（長條／短橫／實線／虛線）；推算人數（第 5 條）在實線（第 4 條）有值的月份不列；1 位小數
    tip = _tip(["bar", "bar", "mark", "line", "dashed"], {"4": 3})
    option = {"grid": {"left": 8, "right": 96, "top": 24, "bottom": 8, "containLabel": True}, "tooltip": tip,
              "xAxis": {"type": "category", "data": list(MONTHS), "axisTick": {"show": False}, "axisLabel": {"color": T.INK2}},
              "yAxis": {"type": "value", "splitLine": {"lineStyle": {"color": T.RULE}}, "axisLabel": {"color": T.INK3}}, "series": series}
    used, ceiling = actual[lm - 1], raw[lm - 1]
    headline = ""
    if ceiling:
        key, kw = ("v_fc_left", {"left": f"{ceiling - used:.0f}"}) if used <= ceiling else ("v_fc_over", {"over": f"{used - ceiling:.0f}"})
        headline = t(lang, key, mon=mon, used=f"{used:.0f}", cap=f"{ceiling:.0f}", **kw)
    rows = tuple((m, raw[i] if i < lm else None, actual[i] if i < lm else None, withb[i] if i < lm and wp else None,
                  nob[i] if i < lm else None, plan[i] if wp else None) for i, m in enumerate(MONTHS))
    return Chart("forecast", t(lang, "v_c_forecast"), option,
                 (t(lang, "v_col_month"), t(lang, "v_lg_cap"), t(lang, "v_lg_actual"), t(lang, "v_fc_with", n=len(wp)),
                  t(lang, "v_fc_without", n=len(cl) - len(wp)), t(lang, "v_lg_plan")), rows,
                 height=300, note=t(lang, "cap_budget_note", covered=len(wp), total=len(cl)), headline=headline)


def fu_plan_actual(snap: dict, lang: str) -> Chart:
    """FU RD 的 plan 只有部分專案有填：plan 與 actual 都只算這些專案（同分母）；全部專案的 FU actual 另列為參考，不與 plan 比。"""
    ps, lm = snap["projects"], snap["meta"]["latest_month"]
    cl = [p for p in ps if p.get("pva")]
    fp = [p for p in cl if any((p["pva"].get("FU RD") or {}).get("plan", [0.0] * 12))]
    fu = lambda group, field, n=12: [round(sum((p["pva"].get("FU RD") or {}).get(field, [0.0] * 12)[i] for p in group), 2) for i in range(n)]  # noqa: E731
    plan, same, every = fu(fp, "plan"), fu(fp, "actual", lm), fu(cl, "actual", lm)
    mon = MONTHS[lm - 1]
    series = [{"name": t(lang, "v_lg_fu_same"), "type": "bar", "barWidth": "45%", "itemStyle": {"color": T.FU},
               "data": _label_last(same, lm - 1, f"{t(lang, 'v_fc_actual_label')} {same[lm - 1]:.0f}", T.FU)},
              _plan_series(t(lang, "v_lg_fu_plan"), plan, lang)] if fp else []
    option = {"grid": {"left": 8, "right": 96, "top": 24, "bottom": 8, "containLabel": True}, "tooltip": _tip(["bar", "mark"]),
              "xAxis": {"type": "category", "data": list(MONTHS), "axisTick": {"show": False}, "axisLabel": {"color": T.INK2}},
              "yAxis": {"type": "value", "splitLine": {"lineStyle": {"color": T.RULE}}, "axisLabel": {"color": T.INK3}}, "series": series}
    headline = (t(lang, "v_fu_headline", mon=mon, act=f"{same[lm - 1]:.0f}", plan=f"{plan[lm - 1]:.0f}", pct=round(same[lm - 1] / plan[lm - 1] * 100))
                if fp and plan[lm - 1] else "")
    rows = tuple((m, plan[i] if fp else None, same[i] if fp and i < lm else None, every[i] if i < lm else None) for i, m in enumerate(MONTHS))
    note = t(lang, "v_fu_note", covered=len(fp), total=len(cl), mon=MONTHS[lm - 1], all=f"{every[lm - 1]:.1f}")
    return Chart("fu", t(lang, "v_c_fu"), option, (t(lang, "v_col_month"), t(lang, "v_lg_fu_plan"), t(lang, "v_lg_fu_same"), t(lang, "v_lg_fu_all")),
                 rows, height=300, note=note, headline=headline)


def pva(p: dict, role: str, latest_month: int, lang: str, idx: int) -> Chart:
    v = (p.get("pva") or {}).get(role) or {}
    plan = [round(x, 2) for x in v.get("plan", [0.0] * 12)]
    act = [round(x, 2) for x in v.get("actual", [0.0] * 12)]
    has_plan = any(plan)
    series = [{"name": t(lang, "v_lg_pva_actual"), "type": "bar", "data": [a if i < latest_month else None for i, a in enumerate(act)],
               "barWidth": "50%", "itemStyle": {"color": T.FU if role == "FU RD" else T.ACCENT}}]
    if has_plan:
        series.append(_plan_series(t(lang, "v_lg_pva_plan"), plan, lang, label=False))
    option = {"grid": {"left": 4, "right": 4, "top": 8, "bottom": 4, "containLabel": True}, "tooltip": _tip(["bar", "mark"] if has_plan else ["bar"]),
              "xAxis": {"type": "category", "data": list(MONTHS), "axisTick": {"show": False}, "axisLabel": {"fontSize": 10, "color": T.INK3, "interval": 1}},
              "yAxis": {"type": "value", "splitLine": {"lineStyle": {"color": T.RULE}}, "axisLabel": {"fontSize": 10, "color": T.INK3}}, "series": series}
    rows = tuple((m, act[i] if i < latest_month else None, plan[i] if has_plan else None) for i, m in enumerate(MONTHS))
    return Chart(f"pva-{idx}-{role.lower().replace(' ', '')}", role, option,
                 (t(lang, "v_col_month"), t(lang, "v_lg_pva_actual"), t(lang, "v_lg_pva_plan")), rows, height=150,
                 note="" if has_plan else t(lang, "v_pva_no_plan"))



def milestone_rows(snap: dict, today: str, weeks: int) -> list[dict]:
    """Overview 里程碑卡：過去 7 天到未來 weeks 週；階段沒推進的過期項目（milestones_passed）在過去 weeks 週內一律保留。
    只看 Briefing 內、非結案／暫停的專案。"""
    late = late_codes(snap)
    t0 = dt.date.fromisoformat(today)
    out = []
    for p in snap["projects"]:
        if not p["in_briefing"] or p["stage_cat"] in INACTIVE:
            continue
        for k in MS:
            d = p["dates"].get(k)
            if not d:
                continue
            left = (dt.date.fromisoformat(d) - t0).days
            is_late = p["code"] in late and left < 0
            if -7 <= left <= weeks * 7 or (is_late and left >= -weeks * 7):
                out.append({"date": d, "name": p["name"], "code": p["code"], "customer": p["customer"], "milestone": k,
                            "days_left": left, "late": is_late})
    return sorted(out, key=lambda r: (r["date"], r["name"]))
