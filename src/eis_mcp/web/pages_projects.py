"""專案列表（2026-10-03 review）：依狀態分段，結案／暫停與不在 Briefing 的收合；每列帶 At risk、下一個里程碑、FTE 趨勢、同期 plan 達成率。
數字全部來自快照與 viz/project.py；查不到就寫明原因，不補 0。"""
from __future__ import annotations
from html import escape as e
from urllib.parse import urlencode
from ...portfolio.entities import INACTIVE, MONTHS
from ...portfolio.render.viz.category_icons import category_icon
from ...portfolio.render.viz.dash import risk_reason
from ...portfolio.render.viz.options import at_risk_rows, late_codes
from ...portfolio.render.viz.project import next_milestone, plan_to_date, sparkline_svg

BIZ_TYPES = ("JDM", "ODM", "EMS")
STAGE_CHIPS = ("RFQ / RFI", "POC", "Execution", "MP", "Sustain / EOP", "Terminated", "Suspended")
GROUPS = (("Active", lambda p: p["in_briefing"] and p["stage_cat"] not in INACTIVE and p["stage_cat"] not in ("MP", "Sustain / EOP"), False),
          ("In production", lambda p: p["in_briefing"] and p["stage_cat"] in ("MP", "Sustain / EOP"), False),
          ("Closed or on hold", lambda p: p["in_briefing"] and p["stage_cat"] in INACTIVE, True),
          ("Not in Briefing", lambda p: not p["in_briefing"], True))
NOT_IN_BRIEFING = "RFQ cost pools, second codes, and projects the Briefing does not list."


def _select(name: str, label: str, options: list[str], current: str) -> str:
    opts = "".join(f'<option value="{e(o)}"{" selected" if o == current else ""}>{e(o)}</option>' for o in options)
    return f'<label>{e(label)} <select name="{name}"><option value="">any</option>{opts}</select></label>'


def _href(month: str, **params: str) -> str:
    q = urlencode({k: v for k, v in params.items() if v})
    return f"/ui/{month}/projects" + (f"?{q}" if q else "")


def _filters(month: str, snap: dict, filters: dict, groups: list[str], customers: list[str], categories: list[str]) -> str:
    """Stage 是一排計數標籤（點了就篩），其餘篩選收在 More filters；文字搜尋只用側欄那一格，這裡以 hidden 保留。"""
    keep = {k: filters.get(k, "") for k in ("biz_type", "category", "group", "customer", "q")}
    cur = filters.get("stage_cat", "")
    counts = {c: sum(1 for p in snap["projects"] if p["stage_cat"] == c) for c in STAGE_CHIPS}
    chip = lambda label, value, n: (f'<a class="fchip"{" aria-current=\"true\"" if value == cur else ""} href="{e(_href(month, stage_cat=value, **keep))}">'  # noqa: E731
                                    f'{e(label)} <b>{n}</b></a>')
    chips = chip("All", "", len(snap["projects"])) + "".join(chip(c, c, counts[c]) for c in STAGE_CHIPS if counts[c])
    more_on = any(filters.get(k) for k in ("biz_type", "category", "group", "customer"))
    more = (f'<details class="more-f"{" open" if more_on else ""}><summary>More filters</summary>'
            f'<form method="get" class="filters"><input type="hidden" name="stage_cat" value="{e(cur)}"><input type="hidden" name="q" value="{e(filters.get("q", ""))}">'
            f'{_select("biz_type", "Type", list(BIZ_TYPES), filters.get("biz_type", ""))}{_select("category", "Category", categories, filters.get("category", ""))}'
            f'{_select("group", "Group", groups, filters.get("group", ""))}{_select("customer", "Customer", customers, filters.get("customer", ""))}'
            f'<button>Apply</button> <a href="/ui/{month}/projects">Clear all</a></form></details>')
    q = filters.get("q", "")
    search = (f'<p class="lead">Matches for "{e(q)}". <a href="{e(_href(month, **{**keep, "q": "", "stage_cat": cur}))}">Clear search</a></p>' if q else "")
    return f'<div class="fbar"><nav class="fchips" aria-label="Stage">{chips}</nav>{more}</div>{search}'


def _next_cell(p: dict, today: str, passed: dict) -> str:
    if p["code"] in passed:
        w = passed[p["code"]]
        return f'<b class="sig">{e(w["ms"])} {e(w["date"])}</b><small class="sig">overdue {w["days"]} days</small>'
    n = next_milestone(p, today) if p["in_briefing"] else None
    when = "on Briefing day" if n and n["days"] == 0 else f'in {n["days"]} days' if n else ""
    return f'{e(n["key"].upper())} {e(n["date"])}<small>{when}</small>' if n else '<span class="dim">–</span>'


def _plan_cell(p: dict, lm: int) -> str:
    pt = plan_to_date(p, lm)
    if pt is None:
        return '<td class="num dim" title="No plan in the Control List">–</td>'
    plan, act = pt
    return f'<td class="num" title="Jan to {MONTHS[lm - 1]}: planned FTE {plan:.1f}, actual FTE {act:.1f} (Control List)">{_two(f"{round(act / plan * 100)}%", f"plan {plan:.1f}")}</td>'


def _two(top: str, sub: str = "") -> str:
    """每格固定兩行：上行主資訊、下行次要資訊（空的也佔位，列高一致）。兩個參數都已跳脫。"""
    return f'{top}<small>{sub or "&nbsp;"}</small>'


def _row(month: str, p: dict, lm: int, today: str, risk: dict, passed: dict) -> str:
    code = f'<span class="code" title="{e(p["code"])}">{e(p["code"])}</span>'
    flag = f'<span class="chip" title="{e("; ".join(risk[p["code"]]))}">At risk</span> ' if p["code"] in risk else ""
    name = _two(f'<a class="row-link" href="/ui/{month}/projects/{e(p["code"])}">{e(p["name"])}</a>', flag + code)
    if p["in_briefing"]:
        same = (p["stage"] or "").casefold() == (p["stage_cat"] or "").casefold()
        stage = _two(e(p["stage"] or "–"), "" if same else e(p["stage_cat"] or ""))
        size = f' {p["panel_size"]}' if p.get("panel_size") and p["panel_size"].upper() != "NA" else ""
        product = _two(e(p.get("biz_type") or "–"), e((p.get("category") or "") + size))
        icon = category_icon(p.get("category"))                       # 對不上的類別不畫，只留文字
        product = f'<div class="prod">{icon}<div>{product}</div></div>' if icon else product
    else:
        stage, product = _two('<span class="dim">Not in Briefing</span>'), _two("–")
    return (f'<tr><td>{name}</td><td>{_two(e(p["customer"]) or "–", e(p["group"]))}</td><td>{product}</td>'
            f'<td class="g">{stage}</td><td class="nx">{_next_cell(p, today, passed)}</td>'
            f'<td class="g">{sparkline_svg(p["fte"], lm)}</td><td class="num">{p["fte"][lm - 1]:.1f}</td><td class="num">{sum(p["fte"][:lm]):.1f}</td>{_plan_cell(p, lm)}</tr>')


# 欄位：(key, 表頭, 可排序鍵, 預設方向, class)。g = 每組第一欄（左側分隔線）
COLUMNS = (("name", "Name", True, "asc", ""), ("customer", "Customer", True, "asc", ""), ("product", "Product", False, "", ""),
           ("stage", "Stage", True, "asc", "g"), ("next", "Next milestone", True, "asc", ""),
           ("trend", "Trend, Jan to {mon}", False, "", "g"), ("fte", "FTE {mon}", True, "desc", "num"),
           ("total", "FTE, Jan to {mon}", True, "desc", "num"), ("plan", "% of planned FTE, Jan to {mon}", True, "asc", "num"))
SORTS = {c[0]: c[3] for c in COLUMNS if c[2]}
DEFAULT_SORT = "fte"
COLS = "".join(f'<col style="width:{w}%">' for w in (13, 10, 11, 8, 13, 11, 8, 11, 15))
TIPS = {"trend": "Each line is scaled to the project peak; compare shapes, not heights",
        "plan": "Actual FTE as a share of planned FTE, summed over Jan to {mon}, all roles",
        "total": "FTE summed over Jan to {mon} (Resource Summary)", "next": "Overdue first, then the nearest date"}


def _head(month: str, mon: str, filters: dict, sort: str, dir_: str) -> str:
    keep = {k: filters.get(k, "") for k in ("stage_cat", "biz_type", "category", "group", "customer", "q")}
    ths = []
    for key, label, sortable, default, cls in COLUMNS:
        text = e(label.format(mon=mon))
        if key == "plan":                                       # 在逗號後斷行，不讓月份單獨掉到第二行
            text = text.replace(", Jan", ",<br>Jan")
        attrs = f' class="{cls}"' if cls else ""
        if key in TIPS:
            attrs += f' title="{e(TIPS[key].format(mon=mon))}"'
        if sortable:
            on = key == sort
            nxt = ("desc" if dir_ == "asc" else "asc") if on else default
            q = {**keep, "sort": key, **({"dir": nxt} if nxt != default else {})}
            arrow = (" ▴" if dir_ == "asc" else " ▾") if on else ""
            attrs += f' aria-sort="{"ascending" if dir_ == "asc" else "descending"}"' if on else ""
            text = f'<a class="sort" href="{e(_href(month, **q))}">{text}{arrow}</a>'
        ths.append(f"<th{attrs}>{text}</th>")
    grp = '<tr class="grp"><th colspan="3">Project</th><th colspan="2" class="g">Schedule</th><th colspan="4" class="g">Manpower</th></tr>'
    return f'<colgroup>{COLS}</colgroup><thead>{grp}<tr>{"".join(ths)}</tr></thead>'


STAGE_RANK = {c: i for i, c in enumerate(("RFQ / RFI", "POC", "Execution", "MP", "Sustain / EOP", "Terminated", "Suspended"))}


def _sort_key(key: str, p: dict, lm: int, today: str, passed: dict):
    """回傳 None 表示這列沒有這個值：不論方向一律排最後（未知不是最小也不是最大）。"""
    if key == "name":
        return p["name"].casefold()
    if key == "customer":
        return (p["customer"] or "").casefold() or None
    if key == "stage":
        return (STAGE_RANK.get(p["stage_cat"], 99), (p["stage"] or "").casefold()) if p["in_briefing"] else None
    if key == "next":
        if p["code"] in passed:
            return (0, -passed[p["code"]]["days"], "")
        n = next_milestone(p, today) if p["in_briefing"] else None
        return (1, 0, n["date"]) if n else None
    if key == "plan":
        pt = plan_to_date(p, lm)
        return pt[1] / pt[0] if pt else None
    if key == "total":
        return sum(p["fte"][:lm])
    return p["fte"][lm - 1]


def _sorted(ps: list[dict], key: str, dir_: str, lm: int, today: str, passed: dict) -> list[dict]:
    base = sorted(ps, key=lambda p: p["name"].casefold())                               # 同值時依名稱，結果穩定
    have = [p for p in base if _sort_key(key, p, lm, today, passed) is not None]
    miss = [p for p in base if _sort_key(key, p, lm, today, passed) is None]
    return sorted(have, key=lambda p: _sort_key(key, p, lm, today, passed), reverse=dir_ == "desc") + miss


def projects_body(month: str, snap: dict, codes: list[str], filters: dict, th: dict, today: str,
                  groups: list[str], customers: list[str], categories: list[str]) -> str:
    """codes：符合篩選的專案（queries.search 的結果）。filters 的 sort/dir 決定各段內的順序；不認得的值回到預設（本月 FTE 由大到小）。"""
    lm = snap["meta"]["latest_month"]
    rows = {r["code"]: r for r in at_risk_rows(snap, th["mp_slip_days"])}
    risk = {c: [risk_reason(w, "en", r["stage"]) for w in r["why"]] for c, r in rows.items()}
    late = late_codes(snap)
    passed = {c: w for c, r in rows.items() if c in late for w in r["why"] if w["rule"] == "passed" and "date" in w}
    keep = set(codes)
    ps = [p for p in snap["projects"] if p["code"] in keep]
    filtered = any(filters.get(k) for k in ("stage_cat", "biz_type", "category", "group", "customer", "q"))
    sort = filters.get("sort") if filters.get("sort") in SORTS else DEFAULT_SORT
    dir_ = filters.get("dir") if filters.get("dir") in ("asc", "desc") else SORTS[sort]
    head = _head(month, MONTHS[lm - 1], filters, sort, dir_)
    parts = []
    for label, test, folded in GROUPS:
        g = _sorted([p for p in ps if test(p)], sort, dir_, lm, today, passed)
        if not g:
            continue
        table = f'<div class="wide"><table class="plist">{head}<tbody>{"".join(_row(month, p, lm, today, risk, passed) for p in g)}</tbody></table></div>'
        note = f'<p class="note">{e(NOT_IN_BRIEFING)}</p>' if label == "Not in Briefing" else ""
        if folded:
            parts.append(f'<details class="group"{" open" if filtered else ""}><summary data-expand="expand" data-collapse="collapse"><span>{e(label)} ({len(g)})</span></summary>{note}{table}</details>')
        else:
            parts.append(f'<h3>{e(label)} ({len(g)})</h3>{table}')
    n = len(ps)
    body = "".join(parts) or '<p class="empty">No project matches.</p>'
    return f'<section><h2>{n} project{"" if n == 1 else "s"}</h2>{_filters(month, snap, filters, groups, customers, categories)}{body}</section>'

