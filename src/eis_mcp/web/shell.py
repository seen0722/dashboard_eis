"""頁面外殼：<head>、nav、footer、錯誤頁。CSS = 月報的 CSS + 這裡的 WEB_CSS，全部 inline，無 JS 依賴（月份下拉的 onchange 是唯一例外）。"""
from __future__ import annotations
from html import escape as e
from ...portfolio.render.css import CSS

WEB_CSS = """
nav.top{display:flex;gap:18px;align-items:center;flex-wrap:wrap;padding:12px 0;border-bottom:1px solid var(--ink);font-size:13px}
nav.top a{color:var(--slate);text-decoration:none;padding:2px 0}nav.top a.on{font-weight:600;color:var(--ink);border-bottom:2px solid var(--signal)}
nav.top form{display:inline-flex;gap:8px;align-items:center;margin-left:auto}
input[type=text],input[type=search],input[type=number]{font:inherit;padding:6px 10px;border:1px solid var(--ink);background:#fff;border-radius:0;min-width:0}
button{font:inherit;padding:6px 14px;border:1px solid var(--ink);background:var(--ink);color:#fff;cursor:pointer}
.filters{display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin:0 0 18px}.filters label{display:flex;flex-direction:column;font-size:12px;color:var(--ink-2);gap:4px}
.kv{display:grid;grid-template-columns:160px 1fr;gap:4px 16px;max-width:80ch;margin:0 0 18px}.kv span:first-child{color:var(--ink-2)}
.metaline{color:var(--ink-2);font-size:12px;margin:6px 0 0}
.err{max-width:70ch}.err h1{color:var(--signal)}
.wide{overflow-x:auto}table a{color:var(--slate)}
.tag{display:inline-block;font-size:11px;padding:1px 6px;border:1px solid var(--rule);color:var(--ink-2);margin-left:6px;vertical-align:1px}
.empty{color:var(--ink-3);padding:18px 0}
"""

NAV = (("overview", "Overview", ""), ("projects", "Projects", "projects"), ("loads", "Loads", "loads"),
       ("corrections", "Corrections", "corrections"), ("report", "Report", "report.html"))


def fmt_month(month: str) -> str:
    return f"{month[:4]}-{month[4:]}" if len(month) == 6 else month


def _nav(months: list[str], month: str | None, suffix: str, active: str) -> str:
    links = [f'<a href="/ui/"{" class=\"on\"" if active == "months" else ""}>Months</a>']
    if month:
        links += [f'<a href="/ui/{e(month)}/{path}"{" class=\"on\"" if active == key else ""}>{label}</a>' for key, label, path in NAV]
        opts = "".join(f'<option value="/ui/{e(m)}/{e(suffix)}"{" selected" if m == month else ""}>{fmt_month(m)}</option>' for m in months)
        picker = (f'<label>Month <select onchange="location.href=this.value">{opts}</select></label>'
                  f'<input type="search" name="q" placeholder="code or name" form="navsearch"><button form="navsearch">Find</button>'
                  f'<form id="navsearch" method="get" action="/ui/{e(month)}/projects"></form>')
    else:
        picker = ""
    return f'<nav class="top" aria-label="EIS">{"".join(links)}<form>{picker}</form></nav>' if month else f'<nav class="top" aria-label="EIS">{"".join(links)}</nav>'


def _meta_line(meta: dict | None) -> str:
    if not meta:
        return ""
    return f'<p class="metaline">report_month {e(str(meta.get("report_month", "")))} · latest_month {e(str(meta.get("latest_month", "")))} · snapshot {e(str(meta.get("snap_date", "")))}</p>'


def render_shell(*, title: str, body: str, months: list[str], month: str | None = None, suffix: str = "",
                 meta: dict | None = None, active: str = "") -> str:
    full = f"EIS · {title}" + (f" · {fmt_month(month)}" if month else "")
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(full)}</title><style>{CSS}{WEB_CSS}</style></head><body>'
            f'{_nav(months, month, suffix, active)}'
            f'<header><div><h1>{e(title)}</h1>{_meta_line(meta)}</div></header>'
            f'{body}'
            f'<footer><p>Values come straight from the monthly EIS snapshot; nothing is inferred or filled in.</p>'
            f'<p>Same data as the MCP tools; report_month is the YYYYMM the snapshot was built for, latest_month the last calendar month with reported manpower.</p></footer>'
            f'</body></html>')


def render_error(status: int, title: str, body: str, months: list[str]) -> str:
    links = "".join(f'<li><a href="/ui/{m}/">{fmt_month(m)}</a></li>' for m in months)
    avail = f'<p>Available months:</p><ul>{links}</ul>' if links else '<p>Nothing has been ingested yet.</p>'
    return render_shell(title=f"{status} · {title}", body=f'<section class="err">{body}{avail}</section>', months=months, active="")
