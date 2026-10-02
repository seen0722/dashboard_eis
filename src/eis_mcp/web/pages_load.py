"""部門負載/產能頁與 corrections 頁的 body。分母是「有填報的人數」不是編制——頁面要講。"""
from __future__ import annotations
from html import escape as e
from ...portfolio.entities import MONTHS
from ...portfolio.render.viz.dash import chart_card
from ...portfolio.render.viz.options import forecast_capacity, load_heatmap


def _cells(values: list, fmt: str) -> str:
    return "".join(f'<td class="num">{format(v, fmt) if v is not None else "–"}</td>' for v in values)


def loads_body(month: str, snap: dict, res: dict, min_util: float | None, spare_pct: float) -> str:
    """橘色標的是「低於 spare_pct 的閒置產能」，與月報「可調度部門」例外同一語意；>=100 的部門佔絕大多數，標了等於沒標。"""
    lm = res["latest_month"]
    form = (f'<form method="get" class="filters"><label>Min latest util (%) <input type="number" name="min_util" value="{"" if min_util is None else f"{min_util:g}"}" min="0" max="1000" step="1"></label>'
            f'<button>Filter</button> <a href="/ui/{month}/loads">clear</a></form>')
    head = "".join(f'<th class="num">{m}</th>' for m in MONTHS)
    rows = []
    for r in res["loads"]:
        lu = r["latest_util"]
        rows.append(f'<tr><td>{e(r["dept_code"])}</td><td>{e(r["dept_name"])}</td><td>{e(r["function"])}</td>'
                    f'<td class="num {"sig" if lu is not None and lu < spare_pct else ""}">{lu if lu is not None else "–"}</td>{_cells(r["util"], "d")}</tr>')
    table = (f'<div class="wide"><table><thead><tr><th>Dept</th><th>Name</th><th>Function</th><th class="num">Latest util %</th>{head}</tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table></div>') if rows else '<p class="empty">No department matches.</p>'
    return (f'<section><h2>Capacity</h2><p class="lead">Keyed-in people per month across departments; months after {MONTHS[lm - 1]} carry the last value forward.</p>'
            f'{chart_card(forecast_capacity(snap, "en"), "en")}</section>'
            f'<section><h2>Load by department</h2><p class="lead">Every department, every month. Pick a cell in the table below for the numbers.</p>'
            f'{chart_card(load_heatmap(snap, "en", spare_pct, by="dept"), "en")}</section>'
            f'<section><h2>{res["count"]} department{"" if res["count"] == 1 else "s"}</h2>'
            f'<p class="lead">util % = allocated FTE / people who keyed in (not headcount). Sorted by latest util ({MONTHS[lm - 1]}); departments with nobody keyed in come last and are dropped when a minimum is set. <span class="sig">Orange</span> = below {spare_pct:g}%, the spare capacity the report points at.</p>'
            f'{form}{table}</section>')


def corrections_body(month: str, res: dict) -> str:
    if not res["corrections"]:
        return '<section><h2>Corrections</h2><p class="empty">No corrections: no past-month number changed since the previous snapshot.</p></section>'
    rows = "".join(f'<tr><td>{e(c["level"])}</td><td>{e(c["detail"])}</td><td>{f"<a href=\"/ui/{month}/projects/{e(c["code"])}\">{e(c["code"])}</a>" if c.get("code") else "–"}</td><td class="dim">{e(c["source"])}</td></tr>'
                   for c in res["corrections"])
    return (f'<section><h2>{res["count"]} correction{"" if res["count"] == 1 else "s"}</h2>'
            f'<p class="lead">Past-month numbers that differ from the previous snapshot: a PM corrected history after the fact.</p>'
            f'<table><thead><tr><th>Level</th><th>Detail</th><th>Project</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table></section>')
