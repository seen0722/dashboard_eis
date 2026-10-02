"""頁面外殼：<head>、左側導覽、footer、錯誤頁。CSS = 月報的 CSS + 這裡的 WEB_CSS；圖表用 /ui/static/echarts.min.js。
月份切換是 GET 表單送到 /ui/go（routes.go 驗證後 redirect），鍵盤選月份不會每按一次方向鍵就跳頁。"""
from __future__ import annotations
from html import escape as e
from ...portfolio.entities import MONTHS
from ...portfolio.render.css import CSS
from ...portfolio.render.viz.dash import side_nav
from ...portfolio.render.viz.embed import scripts

WEB_CSS = """
input[type=text],input[type=search],input[type=number]{font:inherit;padding:6px 10px;border:1px solid var(--rule);background:#fff;border-radius:6px;min-width:0}
button{font:inherit;padding:6px 14px;border:1px solid var(--accent);background:var(--accent);color:#fff;cursor:pointer;border-radius:6px}
.filters{display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin:0 0 18px}.filters label{display:flex;flex-direction:column;font-size:12px;color:var(--ink-2);gap:4px}
.kv{display:grid;grid-template-columns:160px 1fr;gap:4px 16px;max-width:80ch;margin:0 0 18px}.kv>span:nth-child(odd){color:var(--ink-2)}
.metaline{color:var(--ink-2);font-size:12px;margin:6px 0 0;max-width:none}
.err{max-width:70ch}.err h1{color:var(--signal)}
.wide{overflow-x:auto}table a,section a{color:var(--slate)}
td.num+td,th.num+th{padding-left:16px}tbody th{border-bottom:1px solid var(--rule);color:var(--ink);text-align:left}
ol.ex li{grid-template-columns:44px minmax(0,1fr)}
.tag{display:inline-block;font-size:11px;padding:1px 6px;border:1px solid var(--rule);color:var(--ink-2);margin-left:6px;vertical-align:1px}
.empty{color:var(--ink-3);padding:18px 0}
ol.ex .open{font-size:12px;margin-top:4px}ol.ex .open a{color:var(--slate);margin-right:10px}
details.dup summary{cursor:pointer;color:var(--ink-2);font-size:13px;margin:12px 0 6px}
.zh{display:block;color:var(--ink-2)}.dim .zh,.sig .zh,.empty .zh{color:inherit}.zh-inline{font-weight:400;color:var(--ink-2);font-size:.85em;margin-left:6px}h1 .zh{font-size:.6em;font-weight:500;margin-top:4px}
.intro p{margin:0 0 10px;max-width:80ch}.latest .metaline{margin:0 0 14px}.latest h3{font-size:16px;margin:14px 0 6px}
ol.home-ex{list-style:none;margin:0 0 22px;padding:0}ol.home-ex li{border-top:1px solid var(--rule)}ol.home-ex li:first-child{border-top:0}
ol.home-ex a{display:grid;grid-template-columns:32px minmax(0,1fr);gap:10px;padding:10px 0;color:var(--ink);text-decoration:none}
ol.home-ex a:hover b,ol.home-ex a:focus-visible b{text-decoration:underline}ol.home-ex .n{font-size:22px;font-weight:600;color:var(--signal);line-height:1.1}
.home-search{display:flex;gap:8px;margin:6px 0 10px;max-width:560px}.home-search input{flex:1;font-size:15px;padding:9px 12px}
ul.entries{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:4px 28px}
ul.entries li{padding:10px 0;border-top:1px solid var(--rule)}ul.entries a{font-size:15px;text-decoration:none}ul.entries a:hover b,ul.entries a:focus-visible b{text-decoration:underline}
ul.entries p{margin:4px 0 0;font-size:13px}details.home-more{margin:6px 0 12px}details.home-more{border-top:1px solid var(--rule)}details.home-more:first-child{border-top:0}details.home-more>summary{font-weight:600}
pre.prompt{white-space:pre-wrap;word-break:break-word;background:#fff;border:1px solid var(--rule);padding:10px 12px;margin:6px 0 10px;font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;max-width:100ch}
dl.terms{margin:8px 0 0;max-width:90ch}dl.terms dt{font-weight:600;margin-top:12px}dl.terms dd{margin:2px 0 0}dl.terms p{margin:0}
@media(max-width:640px){.kv{grid-template-columns:96px minmax(0,1fr)}.kv code{overflow-wrap:anywhere}ol.ex li{grid-template-columns:32px minmax(0,1fr)}}
"""

NAV = (("overview", "Overview", ""), ("decisions", "Decisions", "decisions"), ("projects", "Projects", "projects"),
       ("loads", "Loads", "loads"), ("health", "Data health", "health"), ("report", "Report", "report.html"))


def fmt_month(month: str) -> str:
    return f"{month[:4]}-{month[4:]}" if len(month) == 6 else month


SITE = "BU10 Portfolio Review"
SITE_ZH = "BU10 專案組合檢討"


def _nav(months: list[str], month: str | None, suffix: str, active: str, decisions: int | None = None) -> str:
    brand = f'<a href="/ui/" class="brand{" on" if active == "home" else ""}">{SITE}</a>'
    if not month:
        return side_nav(brand, "", "Menu")
    items = []
    for key, label, path in NAV:
        badge = f'<span class="badge">{decisions}</span>' if key == "decisions" and decisions else ""
        items.append(f'<a href="/ui/{e(month)}/{path}"{" class=\"on\"" if active == key else ""}>{label}{badge}</a>')
    opts = "".join(f'<option value="{e(m)}"{" selected" if m == month else ""}>{fmt_month(m)}</option>' for m in months)
    # 月份選了就跳轉（頁尾腳本，不用 inline onchange）；沒有 JS 時才出現 Go。搜尋按 Enter 送出，按鈕只給螢幕閱讀器。
    picker = (f'<form method="get" action="/ui/go"><label>Month <select name="month" data-autosubmit>{opts}</select></label>'
              f'<input type="hidden" name="page" value="{e(suffix)}"><noscript><button>Go</button></noscript></form>'
              f'<form method="get" action="/ui/{e(month)}/projects"><input type="search" name="q" class="search" placeholder="Find project" aria-label="Search projects"><button class="sr">Find</button></form>')
    return side_nav(brand, picker + "".join(items), "Menu")


def meta_line(meta: dict | None) -> str:
    """給人看的資料時點：報告月、人力填報到哪個月、Briefing 快照日。欄位名（report_month 等）留給 MCP，不放頁面。"""
    if not meta:
        return ""
    rm, lm, sd = str(meta.get("report_month", "")), meta.get("latest_month"), str(meta.get("snap_date", ""))
    parts = [f"Report month {fmt_month(rm)}"]
    if isinstance(lm, int) and 1 <= lm <= 12:
        parts.append(f"manpower keyed in through {MONTHS[lm - 1]}")
    if len(sd) == 8:
        parts.append(f"Briefing {sd[:4]}-{sd[4:6]}-{sd[6:]}")
    return f'<p class="metaline">{e(" · ".join(parts))}</p>'


def render_shell(*, title: str, body: str, months: list[str], month: str | None = None, suffix: str = "",
                 meta: dict | None = None, active: str = "", title_zh: str = "", decisions: int | None = None) -> str:
    full = f"EIS · {title}" + (f" · {fmt_month(month)}" if month else "")
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(full)}</title><style>{CSS}{WEB_CSS}</style></head><body><div class="app">'
            f'{_nav(months, month, suffix, active, decisions)}<main class="main">'
            f'<header><div><h1>{e(title)}{f"<span class=\"zh\" lang=\"zh-Hant\">{e(title_zh)}</span>" if title_zh else ""}</h1>{meta_line(meta)}</div></header>'
            f'{body}'
            f'<footer><p>Values come straight from the monthly EIS snapshot; nothing is inferred or filled in.</p>'
            f'<p>Same data as the MCP tools. Report month is the month the snapshot was built for (report_month in the tools); keyed in through is the last month with reported manpower (latest_month).</p></footer>'
            f'</main></div>{scripts("static")}'
            f'<script>document.addEventListener("change",function(e){{var s=e.target;if(s&&s.hasAttribute&&s.hasAttribute("data-autosubmit"))s.form.submit();}});</script>'
            f'</body></html>')


def render_error(status: int, title: str, body: str, months: list[str]) -> str:
    links = "".join(f'<li><a href="/ui/{e(m)}/">{fmt_month(m)}</a></li>' for m in months)
    avail = f'<p>Available months:</p><ul>{links}</ul>' if links else '<p>Nothing has been ingested yet.</p>'
    return render_shell(title=f"{status} · {title}", body=f'<section class="err">{body}{avail}</section>', months=months, active="")
