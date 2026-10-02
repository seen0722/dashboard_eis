"""資料健康度頁：健康度表（名稱連到單案頁）＋跨月修正（原 Corrections 頁）。"""
from __future__ import annotations
from html import escape as e
from ...portfolio.render.page import health_html
from .pages_decisions import _project_link
from .pages_load import corrections_body


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
    dup = (f'<details class="dup"><summary data-expand="expand" data-collapse="collapse"><span>{len(decide)} decision-level check{"" if len(decide) == 1 else "s"} repeat items on the Decisions page</span></summary>'
           f'<div class="wide">{_linked_health(snap, decide)}</div></details>') if decide else ""
    return main + dup


def health_body(month: str, snap: dict, corrections: dict) -> str:
    return (f'<section><h2>Data health</h2><p class="lead">What the source files could not answer.</p>'
            f'<div class="card">{health_section(snap)}</div></section>{corrections_body(month, corrections)}')
