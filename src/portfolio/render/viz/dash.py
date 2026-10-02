"""v2 版型的 HTML 積木（月報與 /ui/ 共用）。所有文字在這裡跳脫。卡片是單一圓角底卡＋上緣色條，不疊兩個圓角矩形。"""
from __future__ import annotations
from collections.abc import Callable
from html import escape as e
from ..strings import t
from .embed import Chart, chart_html

DUE_DAYS = 14


def side_nav(brand_html: str, inner_html: str, menu: str, label: str = "EIS") -> str:
    """左側深色導覽。窄螢幕時 .links 收起，以無 JS 的 checkbox 開關。brand_html 與 inner_html 由呼叫端組好（已跳脫）。"""
    return (f'<nav class="side" aria-label="{e(label)}">{brand_html}'
            f'<input type="checkbox" id="navt" class="navt"><label for="navt" class="navbtn">{e(menu)}</label>'
            f'<div class="links">{inner_html}</div></nav>')


def kpi_cards(items: list[dict], href: dict | None = None, cls: str = "") -> str:
    href = href or {}
    out = []
    for k in items:
        inner = (f'<span class="k-label">{e(k["label"])}</span><b class="k-value">{e(str(k["value"]))}</b>'
                 + (f'<span class="k-sub">{e(k["sub"])}</span>' if k.get("sub") else ""))
        c = f'kpi {k.get("tone", "")}'.strip()
        link = href.get(k["key"])
        out.append(f'<a class="{c}" href="{e(link)}">{inner}</a>' if link else f'<div class="{c}">{inner}</div>')
    return f'<div class="{f"kpis {cls}".strip()}">{"".join(out)}</div>'


def card(title: str, body: str, sub: str = "", cls: str = "") -> str:
    s = f'<span class="card-sub">{e(sub)}</span>' if sub else ""
    return f'<div class="{f"card {cls}".strip()}"><div class="card-h"><h3>{e(title)}</h3>{s}</div>{body}</div>'


def chart_card(ch: Chart, lang: str, sub: str = "", cls: str = "") -> str:
    return card(ch.title, chart_html(ch, lang), sub, cls)


def safe_chart_card(title: str, build: Callable[[], Chart], lang: str, cls: str = "") -> str:
    """舊快照可能缺欄位（例如 capacity）：畫不出來就明說，不讓整頁 500。"""
    try:
        ch = build()
    except (KeyError, TypeError, ValueError, IndexError):
        return card(title, f'<p class="note">{e(t(lang, "v_not_in_snapshot"))}</p>', cls=cls)
    return chart_card(ch, lang, cls=cls)


def milestone_status(days_left: int) -> str:
    return "passed" if days_left < 0 else "due" if days_left <= DUE_DAYS else "ok"


def pill(status: str, lang: str, late: bool = True) -> str:
    """已過的里程碑：階段沒前進（late）才用紅色；已正常往下走的用灰色，與舊版 sig／dim 同一語意。"""
    tone = {"passed": "bad" if late else "mute", "due": "warn", "ok": "ok"}[status]
    return f'<span class="pill {tone}">{e(t(lang, "v_st_" + status))}</span>'


def milestone_table(rows: list[dict], lang: str, link: Callable[[str], str] | None = None) -> str:
    body = []
    for r in rows:
        name = f'<a href="{e(link(r["code"]))}">{e(r["name"])}</a>' if link else f'<b>{e(r["name"])}</b>'
        body.append(f'<tr><td>{e(r["date"][5:].replace("-", "/"))}</td><td>{name}</td><td>{e(r.get("customer") or "")}</td>'
                    f'<td>{e(r["milestone"].upper())}</td><td class="num">{r["days_left"]}</td>'
                    f'<td>{pill(milestone_status(r["days_left"]), lang, r.get("late", False))}</td></tr>')
    return (f'<div class="wide"><table><thead><tr><th>{e(t(lang, "col_date"))}</th><th>{e(t(lang, "col_project"))}</th>'
            f'<th>{e(t(lang, "col_customer"))}</th><th>{e(t(lang, "col_milestone"))}</th><th class="num">{e(t(lang, "v_col_days"))}</th>'
            f'<th>{e(t(lang, "v_col_status"))}</th></tr></thead><tbody>{"".join(body)}</tbody></table></div>')
