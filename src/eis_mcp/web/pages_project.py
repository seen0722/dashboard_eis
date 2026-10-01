"""專案表、候選清單、單案頁、跨月 diff 的 body。數字全部來自快照；里程碑/PVA/tasks 卡片重用月報的 project_card_html。"""
from __future__ import annotations
from html import escape as e
from ...portfolio.entities import MONTHS
from ...portfolio.render.page import project_card_html

STAGE_CATS = ("RFQ / RFI", "POC", "Execution", "MP", "Sustain / EOP", "Terminated", "Suspended", "Other")
BIZ_TYPES = ("JDM", "ODM", "EMS")


def _select(name: str, options: list[str], current: str) -> str:
    opts = "".join(f'<option value="{e(o)}"{" selected" if o == current else ""}>{e(o)}</option>' for o in options)
    return f'<select name="{name}"><option value="">any</option>{opts}</select>'


def projects_body(month: str, res: dict, filters: dict, groups: list[str], customers: list[str], categories: list[str] | None = None) -> str:
    form = (f'<form method="get" class="filters">'
            f'<label>Stage {_select("stage_cat", list(STAGE_CATS), filters.get("stage_cat", ""))}</label>'
            f'<label>Type {_select("biz_type", list(BIZ_TYPES), filters.get("biz_type", ""))}</label>'
            f'<label>Category {_select("category", categories or [], filters.get("category", ""))}</label>'
            f'<label>Group {_select("group", groups, filters.get("group", ""))}</label>'
            f'<label>Customer {_select("customer", customers, filters.get("customer", ""))}</label>'
            f'<label>Text <input type="text" name="q" value="{e(filters.get("q", ""))}" placeholder="name, customer or product"></label>'
            f'<button>Filter</button> <a href="/ui/{month}/projects">clear</a></form>')
    rows = "".join(f'<tr><td><a href="/ui/{month}/projects/{e(p["code"])}">{e(p["code"])}</a></td><td><b>{e(p["name"])}</b></td><td>{e(p["stage"])}</td>'
                   f'<td>{e(p["stage_cat"])}</td><td>{e(p.get("biz_type", ""))}</td><td>{e(p.get("category", ""))}{(" " + e(p["panel_size"])) if p.get("panel_size") and p["panel_size"].upper() != "NA" else ""}</td>'
                   f'<td>{e(p["customer"])}</td><td>{e(p["group"])}</td><td class="num">{p["latest_fte"]:.1f}</td></tr>'
                   for p in res["projects"])
    n = res["count"]
    table = (f'<div class="wide"><table><thead><tr><th>Code</th><th>Project</th><th>Stage</th><th>Stage cat.</th><th>Type</th><th>Category</th><th>Customer</th><th>Group</th>'
             f'<th class="num">Latest FTE</th></tr></thead><tbody>{rows}</tbody></table></div>') if rows else '<p class="empty">No project matches.</p>'
    return f'<section><h2>{n} project{"" if n == 1 else "s"}</h2>{form}{table}</section>'


def candidates_body(month: str, cands: list[dict], query: str) -> str:
    rows = "".join(f'<tr><td><a href="/ui/{month}/projects/{e(c["code"])}">{e(c["code"])}</a></td><td><b>{e(c["name"])}</b></td><td>{e(c["stage"])}</td></tr>' for c in cands)
    return (f'<section><h2>Several projects match "{e(query)}"</h2><p class="lead">Pick one.</p>'
            f'<table><thead><tr><th>Code</th><th>Project</th><th>Stage</th></tr></thead><tbody>{rows}</tbody></table></section>')


def _twelve(label: str, values: list, fmt: str) -> str:
    return f'<tr><th>{e(label)}</th>' + "".join(f'<td class="num">{format(v, fmt) if v is not None else "–"}</td>' for v in values) + "</tr>"


def project_body(month: str, p: dict, today: str, lm: int, prev: str | None) -> str:
    yn = lambda b: "yes" if b else "no"  # noqa: E731
    kv = (f'<div class="kv"><span>Code</span><span>{e(p["code"])}</span><span>Customer</span><span>{e(p["customer"]) or "–"}</span>'
          f'<span>Product</span><span>{e(p["product"]) or "–"}</span><span>Group</span><span>{e(p["group"]) or "–"}</span>'
          f'<span>Family</span><span>{e(p["family"]) or "–"}</span><span>Stage</span><span>{e(p["stage"]) or "–"} ({e(p["stage_cat"])})</span>'
          f'<span>In briefing</span><span>{yn(p["in_briefing"])}</span><span>In control list</span><span>{yn(p["in_control_list"])}</span>'
          f'<span>Has plan</span><span>{yn(p["has_plan"])}</span><span>Original MP</span><span>{e(p["dates"].get("mp_orig") or "–")}</span></div>')
    cmp_ = f'<p><a href="/ui/{e(month)}/projects/{e(p["code"])}/diff?to={e(prev)}">Compare with previous month ({prev[:4]}-{prev[4:]})</a></p>' if prev else ""
    head = "".join(f'<th class="num">{m}</th>' for m in MONTHS)
    months_tbl = (f'<div class="wide"><table><thead><tr><th></th>{head}</tr></thead><tbody>{_twelve("FTE", p["fte"], ".1f")}{_twelve("NTD", p["ntd"], ",.0f")}</tbody></table></div>'
                  f'<p class="dim">latest_month = {MONTHS[lm - 1]}; later months are plan or zero.</p>')
    hist = "".join(f'<tr><td>{e(str(h.get("snap", "")))}</td><td>{e(str(h.get("stage") or "–"))}</td><td>{e(str(h.get("dvt") or "–"))}</td><td>{e(str(h.get("mp") or "–"))}</td></tr>' for h in p["history"])
    hist_tbl = (f'<table><thead><tr><th>Snapshot</th><th>Stage</th><th>DVT</th><th>MP</th></tr></thead><tbody>{hist}</tbody></table>'
                if hist else '<p class="empty">No earlier briefing snapshots.</p>')
    return (f'<section>{kv}{cmp_}</section>'
            f'<section><h2>Milestones, plan vs actual, tasks</h2>{project_card_html(p, "en", today, lm, 0)}</section>'
            f'<section><h2>FTE and NTD by month</h2>{months_tbl}</section>'
            f'<section><h2>Briefing history</h2>{hist_tbl}</section>')


def _fmt(v) -> str:
    if v is None:
        return "–"
    if isinstance(v, list):
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {_fmt(x)}" for k, x in v.items()) + "}"
    return str(v)


def flatten_changes(changed: dict, prefix: str = "") -> list[tuple[str, str, str]]:
    """queries.diff 的 changed 樹攤成 (欄位路徑, a, b)。葉節點是 {"a","b"} 或 {"a_count","b_count"}；其餘往下走。依路徑排序。"""
    out = []
    for k, v in changed.items():
        path = f"{prefix}{k}"
        if set(v) == {"a", "b"}:
            out.append((path, _fmt(v["a"]), _fmt(v["b"])))
        elif set(v) == {"a_count", "b_count"}:
            out.append((f"{path} (count)", str(v["a_count"]), str(v["b_count"])))
        else:
            out.extend(flatten_changes(v, path + "."))
    return sorted(out)


def diff_body(month: str, res: dict) -> str:
    a, b = res["month_a"], res["month_b"]
    rows = flatten_changes(res["changed"])
    if not rows:
        return f'<section><h2>{e(res["code"])}: identical in {a[:4]}-{a[4:]} and {b[:4]}-{b[4:]}</h2><p class="empty">No field differs (numeric lists compared with 0.05 tolerance).</p></section>'
    trs = "".join(f'<tr><td>{e(f)}</td><td>{e(x)}</td><td class="sig">{e(y)}</td></tr>' for f, x, y in rows)
    return (f'<section><h2>{e(res["code"])}: {len(rows)} change{"" if len(rows) == 1 else "s"}</h2>'
            f'<p class="lead"><a href="/ui/{month}/projects/{e(res["code"])}">Back to the project</a></p>'
            f'<div class="wide"><table><thead><tr><th>Field</th><th>{a[:4]}-{a[4:]} (a)</th><th>{b[:4]}-{b[4:]} (b)</th></tr></thead><tbody>{trs}</tbody></table></div>'
            f'<p class="dim">Only fields that differ are listed; task/history lists report a count change only.</p></section>')
