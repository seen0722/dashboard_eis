"""月份清單與總覽頁的 body。所有數字來自 snapshot / store.months()。"""
from __future__ import annotations
from html import escape as e
from ...portfolio.render.page import stage_strip_html
from .. import queries
from .pages_decisions import linked_exceptions
from .pages_health import health_section
from .shell import fmt_month


def months_body(months: list[dict], heading: bool = True) -> str:
    """store.months() 的列表：不含原始檔名（Control List 檔名內嵌 PM 姓名）。最新 ok 月份標 latest。"""
    if not months:
        return '<section><p class="empty">Nothing ingested yet. An uploader must upload a month and call ingest_month first.</p></section>'
    latest = next((m["month"] for m in months if m["status"] == "ok"), None)
    rows = []
    for m in months:
        mo = m["month"]; ing = m.get("last_ingest") or {}
        name = f'<a href="/ui/{e(mo)}/">{fmt_month(mo)}</a>' if m["status"] == "ok" else fmt_month(mo)
        tag = '<span class="tag">latest</span>' if mo == latest else ""
        cats = ", ".join(sorted({u["category"] or "?" for u in m["uploads"]})) or "–"
        size_kb = f'{sum(u["size"] for u in m["uploads"]) / 1024:,.0f} KB'
        rows.append(f'<tr><td><b>{name}</b>{tag}</td><td>{e(m["status"])}</td><td>{e(str(ing.get("at", "–")))}</td>'
                    f'<td>{e(str(ing.get("status", "–")))}</td><td class="num">{len(m["uploads"])}</td><td class="num">{size_kb}</td><td class="dim">{e(cats)}</td></tr>')
    head = "<h2>Months</h2>" if heading else ""
    return (f'<section>{head}<p class="lead">Every month the server knows. Only months with status ok can be browsed.</p>'
            f'<div class="wide"><table><thead><tr><th>Month</th><th>Status</th><th>Last ingest</th><th>Ingest status</th>'
            f'<th class="num">Files</th><th class="num">Size</th><th>Categories</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>')


def _milestones(month: str, res: dict) -> str:
    rows = "".join(f'<tr><td>{e(r["date"])}</td><td class="num {"sig" if r["days_left"] < 0 else ""}">{r["days_left"]}</td>'
                   f'<td><a href="/ui/{month}/projects/{e(r["code"])}">{e(r["name"])}</a></td><td>{e(r["stage_cat"])}</td><td>{r["milestone"].upper()}</td></tr>'
                   for r in res["milestones"])
    if not rows:
        return f'<p class="empty">No EVT/DVT/PVT/MP within ±{res["weeks"]} weeks of {e(res["today"])}.</p>'
    return (f'<div class="wide"><table><thead><tr><th>Date</th><th class="num">Days left</th><th>Project</th><th>Stage</th><th>Milestone</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div><p class="dim">Negative days left = already passed. Active projects only (in briefing, not terminated or suspended).</p>')


def overview_body(snap: dict, th: dict, today: str, weeks: int) -> str:
    month = snap["meta"]["report_month"]; lm = snap["meta"]["latest_month"]
    up = queries.upcoming(snap, today, weeks)
    form = (f'<form method="get" class="filters"><label>Weeks <input type="number" name="weeks" value="{weeks}" min="1" max="52"></label>'
            f'<label>Today <input type="text" name="today" value="{e(today)}" size="10"></label><button>Apply</button></form>')
    return (f'<section><h2>Decisions this month</h2><p class="lead">Exceptions the rules found, ranked; each names the decision asked for.</p>{linked_exceptions(snap, th)}</section>'
            f'<section>{stage_strip_html(snap, "en", lm)}<h2>Milestones within {weeks} weeks</h2>{form}{_milestones(month, up)}</section>'
            f'<section><h2>Data health</h2><p class="lead">What the source files could not answer.</p>{health_section(snap)}</section>')
