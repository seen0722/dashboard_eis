"""資料健康度頁：健康度表（名稱連到單案頁）＋跨月修正（原 Corrections 頁）。"""
from __future__ import annotations
from html import escape as e
from ...portfolio.render.page import health_html
from .pages_decisions import _project_link
from .pages_load import corrections_body


KEEP = 6


def _collapse(items: list[str], keep: int = KEEP) -> str:
    """長名單只顯示前 keep 筆，其餘收進 <details>（例如「Briefing 超過 60 天未更新」有 42 筆）。"""
    if len(items) <= keep:
        return ", ".join(items)
    return (", ".join(items[:keep]) + f' <details class="more"><summary>+{len(items) - keep} more</summary>{", ".join(items[keep:])}</details>')


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
        new_names = _collapse([_project_link(month, by_name[n][0], n) if len(by_name.get(n, [])) == 1 else e(n) for n in h["names"]])
        trs[body_start + i] = trs[body_start + i].replace(old, f'class="dim">{new_names}</td>', 1)
    return "</tr>".join(trs)


def health_section(snap: dict) -> str:
    """decide 級的三項（缺預算、里程碑過期、第二身分）與上方 Decisions 同一件事，收進 <details>；track/ok 級照常顯示。"""
    decide = [h for h in snap["health"] if h["level"] == "decide"]
    rest = [h for h in snap["health"] if h["level"] != "decide"]
    found = [h for h in rest if h["count"]]
    empty = [h for h in rest if not h["count"]]                                        # 0 筆的檢查收合，問題不被稀釋
    main = f'<div class="wide">{_linked_health(snap, found)}</div>' if found else '<p class="empty">Every tracking check came back empty.</p>'
    if empty:
        main += (f'<details class="group"><summary data-expand="expand" data-collapse="collapse"><span>{len(empty)} check{"" if len(empty) == 1 else "s"} found nothing</span></summary>'
                 f'<div class="wide">{_linked_health(snap, empty)}</div></details>')
    dup = (f'<details class="dup"><summary data-expand="expand" data-collapse="collapse"><span>{len(decide)} decision-level check{"" if len(decide) == 1 else "s"} repeat items on the Decisions page</span></summary>'
           f'<div class="wide">{_linked_health(snap, decide)}</div></details>') if decide else ""
    return main + dup


def health_body(month: str, snap: dict, corrections: dict) -> str:
    return (f'<section><p class="lead">What the source files could not answer.</p>'
            f'<div class="card">{health_section(snap)}</div></section>{corrections_body(month, corrections)}')
