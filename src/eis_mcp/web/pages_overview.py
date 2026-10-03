"""月份清單與總覽頁的 body。所有數字來自 snapshot / store.months()。"""
from __future__ import annotations
from html import escape as e
from ...portfolio.render.strings import t
from ...portfolio.render.viz.dash import bar_list_card, donut_card, kpi_cards, milestone_card, safe_chart_card
from ...portfolio.render.viz.options import category_donut, customer_bars, forecast_capacity, fu_plan_actual, gantt, kpis, milestone_rows, stage_donut
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


def overview_body(snap: dict, th: dict, today: str, weeks: int) -> str:
    """與月報同一順序：6 張 KPI → Stage｜Customer｜Category → Timeline(2/3)｜Milestones(1/3) → BU｜FU。?weeks= 與 ?today= 仍有效（不放表單）。"""
    month = snap["meta"]["report_month"]
    months = int(th.get("timeline_months", 6))
    link = lambda c: f"/ui/{month}/projects/{c}"  # noqa: E731
    return (f'<section>{kpi_cards(kpis(snap, "en", th), {"risk": f"/ui/{month}/decisions"})}'
            f'<div class="grid-3">{donut_card(stage_donut(snap, "en"), "en", t("en", "v_src_stage"))}'
            f'{bar_list_card(customer_bars(snap, "en"), "en", t("en", "v_src_customer"))}'
            f'{donut_card(category_donut(snap, "en"), "en", t("en", "v_src_category"))}</div>'
            f'<div class="tl-row eq">{safe_chart_card(f"Timeline, next {months} months", lambda: gantt(snap, "en", today, months), "en")}'
            f'{milestone_card(milestone_rows(snap, today, weeks), "en", weeks, link=link, asof=today)}</div>'
            f'<div class="grid-2 eq">{safe_chart_card(t("en", "v_c_forecast"), lambda: forecast_capacity(snap, "en"), "en")}'
            f'{safe_chart_card(t("en", "v_c_fu"), lambda: fu_plan_actual(snap, "en"), "en")}</div></section>')
