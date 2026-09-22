"""專案表、候選清單、單案頁、跨月 diff 的 body。數字全部來自快照；里程碑/PVA/tasks 卡片重用月報的 project_card_html。"""
from __future__ import annotations
from html import escape as e
from ...portfolio.entities import MONTHS
from ...portfolio.render.page import project_card_html

STAGE_CATS = ("RFQ / RFI", "POC", "Execution", "MP", "Sustain / EOP", "Suspended", "Other")


def _select(name: str, options: list[str], current: str) -> str:
    opts = "".join(f'<option value="{e(o)}"{" selected" if o == current else ""}>{e(o)}</option>' for o in options)
    return f'<select name="{name}"><option value="">any</option>{opts}</select>'


def projects_body(month: str, res: dict, filters: dict, groups: list[str], customers: list[str]) -> str:
    form = (f'<form method="get" class="filters">'
            f'<label>Stage {_select("stage_cat", list(STAGE_CATS), filters.get("stage_cat", ""))}</label>'
            f'<label>Group {_select("group", groups, filters.get("group", ""))}</label>'
            f'<label>Customer {_select("customer", customers, filters.get("customer", ""))}</label>'
            f'<label>Text <input type="text" name="q" value="{e(filters.get("q", ""))}" placeholder="name, customer or product"></label>'
            f'<button>Filter</button> <a href="/ui/{month}/projects">clear</a></form>')
    rows = "".join(f'<tr><td><a href="/ui/{month}/projects/{e(p["code"])}">{e(p["code"])}</a></td><td><b>{e(p["name"])}</b></td><td>{e(p["stage"])}</td>'
                   f'<td>{e(p["stage_cat"])}</td><td>{e(p["customer"])}</td><td>{e(p["group"])}</td><td class="num">{p["latest_fte"]:.1f}</td></tr>'
                   for p in res["projects"])
    n = res["count"]
    table = (f'<div class="wide"><table><thead><tr><th>Code</th><th>Project</th><th>Stage</th><th>Category</th><th>Customer</th><th>Group</th>'
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
    cmp_ = f'<p><a href="/ui/{month}/projects/{e(p["code"])}/diff?to={prev}">Compare with previous month ({prev[:4]}-{prev[4:]})</a></p>' if prev else ""
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
