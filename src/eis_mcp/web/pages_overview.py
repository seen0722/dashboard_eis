"""月份清單與總覽頁的 body。所有數字來自 snapshot / store.months()。"""
from __future__ import annotations
from html import escape as e
from ...portfolio.render.page import exceptions_html, health_html, stage_strip_html
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


def _milestones(month: str, res: dict) -> str:
    rows = "".join(f'<tr><td>{e(r["date"])}</td><td class="num {"sig" if r["days_left"] < 0 else ""}">{r["days_left"]}</td>'
                   f'<td><a href="/ui/{month}/projects/{e(r["code"])}">{e(r["name"])}</a></td><td>{e(r["stage_cat"])}</td><td>{r["milestone"].upper()}</td></tr>'
                   for r in res["milestones"])
    if not rows:
        return f'<p class="empty">No EVT/DVT/PVT/MP within ±{res["weeks"]} weeks of {e(res["today"])}.</p>'
    return (f'<div class="wide"><table><thead><tr><th>Date</th><th class="num">Days left</th><th>Project</th><th>Stage</th><th>Milestone</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div><p class="dim">Negative days left = already passed. Active projects only (in briefing, not terminated or suspended).</p>')


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
            links = " ".join(_project_link(month, c, names[c]) for c in codes)   # 空白＝斷行點
            items[i] = items[i][:-len("</div>")] + f'<div class="open">Open: {links}</div></div>'
    return "</li>".join(items)


def _linked_health(snap: dict, rows: list[dict]) -> str:
    """health_html 的表格，名稱欄裡「恰好等於某個專案名稱」的項目換成連結；其他（如 KOS (BR…) also booked as …）保持純文字。"""
    month = snap["meta"]["report_month"]
    by_name: dict[str, list[str]] = {}
    for p in snap["projects"]:
        by_name.setdefault(p["name"], []).append(p["code"])
    out = health_html({"health": rows}, "en")
    trs = out.split("</tr>")
    body_start = 1                                    # trs[0] 是表頭列
    if len(trs) != len(rows) + body_start + 1:
        return out
    for i, h in enumerate(rows):
        old = f'class="dim">{e(", ".join(h["names"]))}</td>'
        new_names = ", ".join(_project_link(month, by_name[n][0], n) if len(by_name.get(n, [])) == 1 else e(n) for n in h["names"])
        trs[body_start + i] = trs[body_start + i].replace(old, f'class="dim">{new_names}</td>', 1)
    return "</tr>".join(trs)


def health_section(snap: dict) -> str:
    """decide 級的三項（缺預算、里程碑過期、第二身分）與上方 Decisions 同一件事，收進 <details>；track/ok 級照常顯示。"""
    decide = [h for h in snap["health"] if h["level"] == "decide"]
    rest = [h for h in snap["health"] if h["level"] != "decide"]
    main = f'<div class="wide">{_linked_health(snap, rest)}</div>' if rest else '<p class="empty">No tracking checks.</p>'
    dup = (f'<details class="dup"><summary data-expand="expand" data-collapse="collapse"><span>{len(decide)} decision-level check{"" if len(decide) == 1 else "s"} repeat the Decisions above</span></summary>'
           f'<div class="wide">{_linked_health(snap, decide)}</div></details>') if decide else ""
    return main + dup


def overview_body(snap: dict, th: dict, today: str, weeks: int) -> str:
    month = snap["meta"]["report_month"]; lm = snap["meta"]["latest_month"]
    up = queries.upcoming(snap, today, weeks)
    form = (f'<form method="get" class="filters"><label>Weeks <input type="number" name="weeks" value="{weeks}" min="1" max="52"></label>'
            f'<label>Today <input type="text" name="today" value="{e(today)}" size="10"></label><button>Apply</button></form>')
    return (f'<section><h2>Decisions this month</h2><p class="lead">Exceptions the rules found, ranked; each names the decision asked for.</p>{linked_exceptions(snap, th)}</section>'
            f'<section>{stage_strip_html(snap, "en", lm)}<h2>Milestones within {weeks} weeks</h2>{form}{_milestones(month, up)}</section>'
            f'<section><h2>Data health</h2><p class="lead">What the source files could not answer.</p>{health_section(snap)}</section>')
