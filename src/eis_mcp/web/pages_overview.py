"""月份清單與總覽頁的 body。所有數字來自 snapshot / store.months()。"""
from __future__ import annotations
from html import escape as e
from .shell import fmt_month


def months_body(months: list[dict]) -> str:
    """store.months() 的列表：不含原始檔名（Control List 檔名內嵌 PM 姓名）。最新 ok 月份標 latest。"""
    if not months:
        return '<section><p class="empty">Nothing ingested yet. An uploader must upload a month and call ingest_month first.</p></section>'
    latest = next((m["month"] for m in months if m["status"] == "ok"), None)
    rows = []
    for m in months:
        mo = m["month"]; ing = m.get("last_ingest") or {}
        name = f'<a href="/ui/{mo}/">{fmt_month(mo)}</a>' if m["status"] == "ok" else fmt_month(mo)
        tag = '<span class="tag">latest</span>' if mo == latest else ""
        cats = ", ".join(sorted({u["category"] or "?" for u in m["uploads"]})) or "–"
        rows.append(f'<tr><td><b>{name}</b>{tag}</td><td>{e(m["status"])}</td><td>{e(str(ing.get("at", "–")))}</td>'
                    f'<td>{e(str(ing.get("by", "–")))}</td><td>{e(str(ing.get("status", "–")))}</td><td class="num">{len(m["uploads"])}</td><td class="dim">{e(cats)}</td></tr>')
    return (f'<section><h2>Months</h2><p class="lead">Every month the server knows. Only months with status ok can be browsed.</p>'
            f'<div class="wide"><table><thead><tr><th>Month</th><th>Status</th><th>Last ingest</th><th>By</th><th>Ingest status</th>'
            f'<th class="num">Files</th><th>Categories</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>')
