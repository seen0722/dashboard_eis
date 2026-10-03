"""專案列表（2026-10-03 review）：依狀態分段，結案／暫停與不在 Briefing 的收合；每列帶 At risk、下一個里程碑、FTE 趨勢、同期 plan 達成率。
數字全部來自快照與 viz/project.py；查不到就寫明原因，不補 0。"""
from __future__ import annotations
from html import escape as e
from urllib.parse import urlencode
from ...portfolio.entities import INACTIVE, MONTHS
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
    when = "today" if n and n["days"] == 0 else f'in {n["days"]} days' if n else ""
    return f'{e(n["key"].upper())} {e(n["date"])}<small>{when}</small>' if n else '<span class="dim">–</span>'


def _plan_cell(p: dict, lm: int) -> str:
    pt = plan_to_date(p, lm)
    if pt is None:
        return '<td class="num dim" title="No plan in the Control List">–</td>'
    plan, act = pt
    return f'<td class="num" title="Jan–{MONTHS[lm - 1]} plan {plan:.1f}, actual {act:.1f}">{round(act / plan * 100)}%</td>'


def _row(month: str, p: dict, lm: int, today: str, risk: dict, passed: dict) -> str:
    risk_cell = (f'<span class="chip" title="{e("; ".join(risk[p["code"]]))}">At risk</span>' if p["code"] in risk else "")
    if p["in_briefing"]:
        same = (p["stage"] or "").casefold() == (p["stage_cat"] or "").casefold()
        stage = f'{e(p["stage"] or "–")}' + ("" if same or not p["stage_cat"] else f'<small>{e(p["stage_cat"])}</small>')
        kind = ", ".join(x for x in (p.get("biz_type", ""), p.get("category", "") + (f' {p["panel_size"]}' if p.get("panel_size") and p["panel_size"].upper() != "NA" else "")) if x.strip())
    else:
        stage, kind = '<span class="dim">Not in Briefing</span>', ""
    return (f'<tr><td><a class="row-link" href="/ui/{month}/projects/{e(p["code"])}">{e(p["name"])}</a></td><td>{risk_cell}</td>'
            f'<td>{stage}</td><td class="nx">{_next_cell(p, today, passed)}</td><td>{e(p["customer"]) or "–"}</td><td>{e(kind) or "–"}</td><td>{e(p["group"]) or "–"}</td>'
            f'<td>{sparkline_svg(p["fte"], lm)}</td><td class="num">{p["fte"][lm - 1]:.1f}</td>{_plan_cell(p, lm)}<td class="code" title="{e(p["code"])}">{e(p["code"])}</td></tr>')


COLS = "".join(f'<col style="width:{w}%">' for w in (12, 7, 8, 12, 8, 13, 7, 9, 6, 7, 11))
HEAD = (f'<colgroup>{COLS}</colgroup>' '<thead><tr><th>Project</th><th>Risk</th><th>Stage</th><th>Next milestone</th><th>Customer</th><th>Type, category</th><th>Group</th>'
        '<th title="Each line is scaled to the project peak; compare shapes, not heights">FTE, Jan to {mon}</th><th class="num">FTE {mon}</th><th class="num" title="Actual over plan, Jan to the latest month, all roles">Plan to date</th><th>Code</th></tr></thead>')


def projects_body(month: str, snap: dict, codes: list[str], filters: dict, th: dict, today: str,
                  groups: list[str], customers: list[str], categories: list[str]) -> str:
    """codes：符合篩選的專案（queries.search 的結果）。各段依最新月 FTE 由大到小，同 FTE 依名稱（不分大小寫）。"""
    lm = snap["meta"]["latest_month"]
    rows = {r["code"]: r for r in at_risk_rows(snap, th["mp_slip_days"])}
    risk = {c: [risk_reason(w, "en", r["stage"]) for w in r["why"]] for c, r in rows.items()}
    late = late_codes(snap)
    passed = {c: w for c, r in rows.items() if c in late for w in r["why"] if w["rule"] == "passed" and "date" in w}
    keep = set(codes)
    ps = [p for p in snap["projects"] if p["code"] in keep]
    filtered = any(filters.get(k) for k in ("stage_cat", "biz_type", "category", "group", "customer", "q"))
    head = HEAD.format(mon=MONTHS[lm - 1])
    parts = []
    for label, test, folded in GROUPS:
        g = sorted((p for p in ps if test(p)), key=lambda p: (-p["fte"][lm - 1], p["name"].casefold()))
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

