"""頁面外殼：<head>、nav、footer、錯誤頁。CSS = 月報的 CSS + 這裡的 WEB_CSS，全部 inline，無 JavaScript。
月份切換是 GET 表單送到 /ui/go（routes.go 驗證後 redirect），鍵盤選月份不會每按一次方向鍵就跳頁。"""
from __future__ import annotations
from html import escape as e
from ...portfolio.entities import MONTHS
from ...portfolio.render.css import CSS

WEB_CSS = """
nav.top{display:flex;gap:18px;align-items:center;flex-wrap:wrap;padding:12px 0;border-bottom:1px solid var(--ink);font-size:13px}
nav.top a{color:var(--slate);text-decoration:none;padding:2px 0}nav.top a.on{font-weight:600;color:var(--ink);border-bottom:2px solid var(--signal)}
nav.top .tools{display:inline-flex;gap:8px;align-items:center;margin-left:auto}nav.top .tools form{display:inline-flex;gap:8px}
input[type=text],input[type=search],input[type=number]{font:inherit;padding:6px 10px;border:1px solid var(--ink);background:#fff;border-radius:0;min-width:0}
button{font:inherit;padding:6px 14px;border:1px solid var(--ink);background:var(--ink);color:#fff;cursor:pointer}
.filters{display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin:0 0 18px}.filters label{display:flex;flex-direction:column;font-size:12px;color:var(--ink-2);gap:4px}
.kv{display:grid;grid-template-columns:160px 1fr;gap:4px 16px;max-width:80ch;margin:0 0 18px}.kv>span:nth-child(odd){color:var(--ink-2)}
.metaline{color:var(--ink-2);font-size:12px;margin:6px 0 0;max-width:none}nav.top+header{margin-top:20px}
.err{max-width:70ch}.err h1{color:var(--signal)}
.wide{overflow-x:auto}table a,section a{color:var(--slate)}
td.num+td,th.num+th{padding-left:16px}tbody th{border-bottom:1px solid var(--rule);color:var(--ink);text-align:left}
ol.ex li{grid-template-columns:44px minmax(0,1fr)}
.tag{display:inline-block;font-size:11px;padding:1px 6px;border:1px solid var(--rule);color:var(--ink-2);margin-left:6px;vertical-align:1px}
.empty{color:var(--ink-3);padding:18px 0}
ol.ex .open{font-size:12px;margin-top:4px}ol.ex .open a{color:var(--slate);margin-right:10px}
details.dup summary{cursor:pointer;color:var(--ink-2);font-size:13px;margin:12px 0 6px}
nav.top a.brand{font-weight:700;color:var(--ink);margin-right:6px}nav.top a.brand.on{border-bottom:2px solid var(--signal)}
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
@media(max-width:640px){body{padding:20px 16px 60px}.kv{grid-template-columns:96px minmax(0,1fr)}.kv code{overflow-wrap:anywhere}nav.top .tools{margin-left:0;flex-wrap:wrap}nav.top .tools form{flex-wrap:wrap}nav.top input[type=search]{width:150px}ol.ex li{grid-template-columns:32px minmax(0,1fr)}}
"""

NAV = (("overview", "Overview", ""), ("projects", "Projects", "projects"), ("loads", "Loads", "loads"),
       ("corrections", "Corrections", "corrections"), ("report", "Report", "report.html"))


def fmt_month(month: str) -> str:
    return f"{month[:4]}-{month[4:]}" if len(month) == 6 else month


SITE = "BU10 Portfolio Review"
SITE_ZH = "BU10 專案組合檢討"


def _nav(months: list[str], month: str | None, suffix: str, active: str) -> str:
    links = [f'<a href="/ui/" class="brand{" on" if active == "home" else ""}">{SITE}</a>']
    if month:
        links += [f'<a href="/ui/{e(month)}/{path}"{" class=\"on\"" if active == key else ""}>{label}</a>' for key, label, path in NAV]
        opts = "".join(f'<option value="{e(m)}"{" selected" if m == month else ""}>{fmt_month(m)}</option>' for m in months)
        picker = (f'<form method="get" action="/ui/go"><label>Month <select name="month">{opts}</select></label>'
                  f'<input type="hidden" name="page" value="{e(suffix)}"><button>Go</button></form>'
                  f'<form method="get" action="/ui/{e(month)}/projects"><input type="search" name="q" placeholder="code or name" aria-label="Search projects"><button>Find</button></form>')
    else:
        picker = ""
    return f'<nav class="top" aria-label="EIS">{"".join(links)}<div class="tools">{picker}</div></nav>' if month else f'<nav class="top" aria-label="EIS">{"".join(links)}</nav>'


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
                 meta: dict | None = None, active: str = "", title_zh: str = "") -> str:
    full = f"EIS · {title}" + (f" · {fmt_month(month)}" if month else "")
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(full)}</title><style>{CSS}{WEB_CSS}</style></head><body>'
            f'{_nav(months, month, suffix, active)}'
            f'<header><div><h1>{e(title)}{f"<span class=\"zh\" lang=\"zh-Hant\">{e(title_zh)}</span>" if title_zh else ""}</h1>{meta_line(meta)}</div></header>'
            f'{body}'
            f'<footer><p>Values come straight from the monthly EIS snapshot; nothing is inferred or filled in.</p>'
            f'<p>Same data as the MCP tools. Report month is the month the snapshot was built for (report_month in the tools); keyed in through is the last month with reported manpower (latest_month).</p></footer>'
            f'</body></html>')


def render_error(status: int, title: str, body: str, months: list[str]) -> str:
    links = "".join(f'<li><a href="/ui/{e(m)}/">{fmt_month(m)}</a></li>' for m in months)
    avail = f'<p>Available months:</p><ul>{links}</ul>' if links else '<p>Nothing has been ingested yet.</p>'
    return render_shell(title=f"{status} · {title}", body=f'<section class="err">{body}{avail}</section>', months=months, active="")
