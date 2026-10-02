"""v2 版型的 HTML 積木（月報與 /ui/ 共用）。所有文字在這裡跳脫。卡片是單一圓角底卡＋上緣色條，不疊兩個圓角矩形。"""
from __future__ import annotations
from collections.abc import Callable
from html import escape as e
from ..strings import t
from .embed import Chart, chart_div, chart_html
from .options import at_risk_codes

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
    return card(ch.title, chart_html(ch, lang), sub or ch.headline, cls)


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
    tone = {"passed": "bad" if late else "mute", "due": "warn", "ok": "mute"}[status]   # 「ok」只代表超過 14 天，不代表進度正常
    return f'<span class="pill {tone}">{e(t(lang, "v_st_" + status))}</span>'


def milestone_table(rows: list[dict], lang: str, link: Callable[[str], str] | None = None, compact: bool = False) -> str:
    """compact：三分之一寬的卡片只放 Date／Project／Milestone／Status（Customer 與 Days left 放不下）。"""
    body = []
    for r in rows:
        name = f'<a href="{e(link(r["code"]))}">{e(r["name"])}</a>' if link else f'<b>{e(r["name"])}</b>'
        status = pill(milestone_status(r["days_left"]), lang, r.get("late", False))
        if compact:
            body.append(f'<tr><td>{e(r["date"][5:].replace("-", "/"))}</td><td>{name}</td><td>{e(r["milestone"].upper())}</td><td>{status}</td></tr>')
        else:
            body.append(f'<tr><td>{e(r["date"][5:].replace("-", "/"))}</td><td>{name}</td><td>{e(r.get("customer") or "")}</td>'
                        f'<td>{e(r["milestone"].upper())}</td><td class="num">{r["days_left"]}</td><td>{status}</td></tr>')
    if compact:
        head = (f'<th>{e(t(lang, "col_date"))}</th><th>{e(t(lang, "col_project"))}</th><th>{e(t(lang, "col_milestone"))}</th>'
                f'<th>{e(t(lang, "v_col_status"))}</th>')
    else:
        head = (f'<th>{e(t(lang, "col_date"))}</th><th>{e(t(lang, "col_project"))}</th><th>{e(t(lang, "col_customer"))}</th>'
                f'<th>{e(t(lang, "col_milestone"))}</th><th class="num">{e(t(lang, "v_col_days"))}</th><th>{e(t(lang, "v_col_status"))}</th>')
    return f'<div class="wide"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def at_risk_html(snap: dict, lang: str, th: dict, link: Callable[[str], str] | None = None) -> str:
    """At Risk KPI 的落地處：列出 KPI 數到的每一案，含只在健康度追蹤（PM 已確認）的 MP 延後。"""
    codes = at_risk_codes(snap, th["mp_slip_days"])
    if not codes:
        return ""
    names = {p["code"]: p["name"] for p in snap["projects"]}
    items = " ".join(f'<a class="chip" href="{e(link(c))}">{e(names.get(c, c))}</a>' if link else f'<span class="chip">{e(names.get(c, c))}</span>' for c in codes)
    return (f'<p class="lead"><b class="sig">{e(t(lang, "v_risk_head", n=len(codes)))}</b> {items}'
            f'<br><span class="note">{e(t(lang, "v_risk_note", days=th["mp_slip_days"]))}</span></p>')



def exception_titles(snap: dict, th: dict, lang: str) -> list[str]:
    """與 render/page.py::_exceptions 相同的標題組法（同一組 kw、同一個 legacy 退路），只取標題。
    tests 以「每個標題都出現在 exceptions_html 輸出裡」守住兩邊不漂移。"""
    out = []
    for x in snap["exceptions"]:
        k = x["title"]
        kw = {"n": x["count"], "days": th["mp_slip_days"], "pct": th["spare_capacity_pct"], "full": x.get("ask_data", "")}
        kw.update(x.get("extra", {}))
        if k == "suspended_charging" and "suspended" not in kw:
            k = "suspended_charging_legacy"
        out.append(t(lang, f"ex_{k}_title", **kw))
    return out


def status_html(snap: dict, lang: str, th: dict, link: Callable[[str], str] | None = None, decisions_href: str = "#decisions") -> str:
    """Overview 第一屏：At risk（列出每一案）與本月決策（列出標題），兩張重點卡並排。"""
    codes = at_risk_codes(snap, th["mp_slip_days"])
    names = {p["code"]: p["name"] for p in snap["projects"]}
    chips = "".join(f'<a class="chip" href="{e(link(c))}">{e(names.get(c, c))}</a>' if link else f'<span class="chip">{e(names.get(c, c))}</span>'
                    for c in codes)
    risk = (f'<div class="status-card risk"><div class="s-head"><span class="s-label">{e(t(lang, "v_kpi_risk"))}</span>'
            f'<b class="s-num">{len(codes)}</b></div><div class="chips">{chips}</div>'
            f'<p class="note">{e(t(lang, "v_kpi_risk_sub", days=th["mp_slip_days"]))}</p></div>')
    titles = exception_titles(snap, th, lang)
    items = "".join(f"<li>{e(x)}</li>" for x in titles)
    dec = (f'<a class="status-card dec" href="{e(decisions_href)}"><div class="s-head"><span class="s-label">{e(t(lang, "s_decisions"))}</span>'
           f'<b class="s-num">{len(titles)}</b></div><ol class="s-list">{items}</ol></a>')
    return f'<div class="status">{risk}{dec}</div>'



def donut_card(ch: Chart, lang: str, sub: str = "") -> str:
    """小甜甜圈＋HTML 圖例表格（色塊、名稱、數量、百分比）。表格就是這張圖的資料表，沒有 JS 也讀得到。"""
    colors = [d["itemStyle"]["color"] for d in ch.option["series"][0]["data"]]
    rows = "".join(f'<tr><td title="{e(str(r[0]))}"><i style="background:{e(c)}"></i>{e(str(r[0]))}</td><td class="num"><b>{r[1]}</b> <span class="dim">({e(str(r[2]))})</span></td></tr>'
                   for r, c in zip(ch.rows, colors))
    note = f'<p class="note">{e(ch.note)}</p>' if ch.note else ""
    return card(ch.title, f'<div class="dl">{chart_div(ch, lang)}<table class="legend-t">{rows}</table></div>{note}', sub)


def bar_list_card(ch: Chart, lang: str, sub: str = "") -> str:
    """純 HTML 長條清單（名稱｜長條｜數字），與 mock 同一列樣式；沒有 JS 也完整。"""
    mx = max((r[1] for r in ch.rows), default=0) or 1
    rows = "".join(f'<tr><td>{e(str(r[0]))}</td><td class="bar"><span style="width:{r[1] / mx * 100:.0f}%"></span></td><td class="num"><b>{r[1]}</b></td></tr>'
                   for r in ch.rows)
    return card(ch.title, f'<table class="bars-t">{rows}</table>', sub)
