"""月份清單與總覽頁的 body。所有數字來自 snapshot / store.months()。"""
from __future__ import annotations
from html import escape as e
from ...portfolio.render.strings import t
from ...portfolio.render.viz.dash import card, kpi_cards, milestone_table, safe_chart_card, status_html
from ...portfolio.render.viz.options import category_donut, composition, customer_bars, forecast_capacity, fu_plan_actual, gantt, kpis, late_codes, load_heatmap, stage_donut, type_donut
from .. import queries
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


def _milestone_card(month: str, snap: dict, today: str, weeks: int) -> str:
    up = queries.upcoming(snap, today, weeks)
    late = late_codes(snap)
    by_code = {p["code"]: p for p in snap["projects"]}
    rows = [{**r, "customer": by_code[r["code"]]["customer"], "late": r["code"] in late} for r in up["milestones"]]
    form = (f'<form method="get" class="filters"><label>Weeks <input type="number" name="weeks" value="{weeks}" min="1" max="52"></label>'
            f'<label>Today <input type="text" name="today" value="{e(today)}" size="10"></label><button>Apply</button></form>')
    table = (milestone_table(rows, "en", link=lambda c: f"/ui/{month}/projects/{c}") if rows
             else f'<p class="empty">No EVT/DVT/PVT/MP within ±{weeks} weeks of {e(today)}.</p>')
    return card(f"Milestones within {weeks} weeks", form + table +
                '<p class="dim">Negative days left = already passed. Active projects only (in briefing, not terminated or suspended).</p>')


def overview_body(snap: dict, th: dict, today: str, weeks: int) -> str:
    month = snap["meta"]["report_month"]
    months = int(th.get("timeline_months", 6)); spare = float(th.get("spare_capacity_pct", 85))
    link = lambda c: f"/ui/{month}/projects/{c}"  # noqa: E731
    strip = kpi_cards([k for k in kpis(snap, "en", th) if k["key"] != "risk"], cls="strip")
    return (f'<section>{status_html(snap, "en", th, link=link, decisions_href=f"/ui/{month}/decisions")}{strip}'
            f'<div class="grid-2">{safe_chart_card(t("en", "v_c_forecast"), lambda: forecast_capacity(snap, "en"), "en")}'
            f'{safe_chart_card(t("en", "v_c_fu"), lambda: fu_plan_actual(snap, "en"), "en")}</div>'
            f'{safe_chart_card("Portfolio mix", lambda: composition(snap, "en"), "en")}'
            f'<div class="grid-2">{safe_chart_card("Projects by customer", lambda: customer_bars(snap, "en"), "en")}'
            f'{_milestone_card(month, snap, today, weeks)}</div>'
            f'{safe_chart_card(f"Timeline, next {months} months", lambda: gantt(snap, "en", today, months), "en")}'
            f'{safe_chart_card("Resource load by function", lambda: load_heatmap(snap, "en", spare), "en")}</section>')
