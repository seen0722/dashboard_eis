"""本月決策頁。例外清單與月報同一份（render/page.py 的 exceptions_html），每條補一行連到單案頁。"""
from __future__ import annotations
from html import escape as e
from ...portfolio.render.page import exceptions_html
from ...portfolio.render.viz.dash import at_risk_html


def _project_link(month: str, code: str, label: str) -> str:
    return f'<a href="/ui/{e(month)}/projects/{e(code)}">{e(label)}</a>'


def linked_exceptions(snap: dict, th: dict) -> str:
    """月報的例外清單（共用 render/page.py，不改它），每條後面補一行連到單案頁的連結，來源是例外自帶的 codes。
    一個 <li> 對一條 snap["exceptions"]；結構對不上就原樣回傳（頁面照常出，只是少了連結），不猜。"""
    out = exceptions_html(snap, "en", th)
    month = snap["meta"]["report_month"]
    names = {p["code"]: p["name"] for p in snap["projects"]}
    items = out.split("</li>")
    if len(items) != len(snap["exceptions"]) + 1:
        return out
    for i, x in enumerate(snap["exceptions"]):
        codes = [c for c in dict.fromkeys(x.get("codes") or []) if c in names]
        if codes and items[i].endswith("</div>"):
            links = " ".join(f'<a class="chip plain" href="/ui/{e(month)}/projects/{e(c)}">{e(names[c])}</a>' for c in codes)   # 空白＝斷行點
            items[i] = items[i][:-len("</div>")] + f'<div class="open">{links}</div></div>'
    return "</li>".join(items)


def decisions_body(snap: dict, th: dict) -> str:
    return (f'<section><p class="lead">Exceptions the rules found, ranked; each names the decision asked for.</p>'
            f'{at_risk_html(snap, "en", th, link=lambda c: f"/ui/{snap["meta"]["report_month"]}/projects/{c}")}'
            f'<div class="card">{linked_exceptions(snap, th)}</div></section>')
