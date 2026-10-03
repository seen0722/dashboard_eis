"""/ui/ 首頁：簡單的起點（需求方 2026-10-03：不要過多文字）。搜尋框、四張本月狀態卡、兩個連結、收合的資料歷程。
側欄帶最新月份的完整導覽，所以這裡不再列「從哪裡開始」。數字全部取自最新快照，與各頁同一個計算。"""
from __future__ import annotations
from html import escape as e
from ...portfolio.entities import MONTHS
from ...portfolio.render.viz.dash import exception_titles, kpi_cards  # noqa: F401  exception_titles：舊 import 路徑保留
from ...portfolio.render.viz.options import at_risk_codes
from .pages_overview import months_body


def _tiles(snap: dict, th: dict) -> str:
    month, lm = snap["meta"]["report_month"], snap["meta"]["latest_month"]
    names = {p["code"]: p["name"] for p in snap["projects"]}
    risk = at_risk_codes(snap, th["mp_slip_days"])
    n_ex = len(snap["exceptions"])
    active = sum(1 for p in snap["projects"] if p["in_briefing"] and p["stage_cat"] in ("RFQ / RFI", "POC", "Execution"))
    items = [{"key": "risk", "label": "At risk", "value": len(risk), "tone": "bad" if risk else "",
              "sub": ", ".join(names.get(c, c) for c in risk) or "none this month"},
             {"key": "decisions", "label": "Decisions", "value": n_ex, "sub": "to make this month" if n_ex else "none this month"},
             {"key": "projects", "label": "Projects", "value": len(snap["projects"]), "sub": f"{active} in RFQ, POC or execution"},
             {"key": "fte", "label": f"FTE, {MONTHS[lm - 1]}", "value": f'{sum(p["fte"][lm - 1] for p in snap["projects"]):.1f}',
              "sub": "reported, all projects"}]
    href = {"risk": f"/ui/{month}/decisions", "decisions": f"/ui/{month}/decisions", "projects": f"/ui/{month}/projects", "fte": f"/ui/{month}/loads"}
    return kpi_cards(items, href=href, cls="home-tiles")


def _search(month: str) -> str:
    return (f'<form method="get" action="/ui/{e(month)}/projects" class="home-search">'
            f'<input type="search" name="q" placeholder="Find a project by code or name" aria-label="Find a project"><button>Find</button></form>')


def _history(months: list[dict]) -> str:
    n = len(months)
    return (f'<details class="home-more"><summary data-expand="expand" data-collapse="collapse"><span>Data history, {n} month{"" if n == 1 else "s"}</span></summary>'
            f'{months_body(months, heading=False)}</details>')


def home_body(months: list[dict], snap: dict | None, th: dict, broken_month: str | None = None) -> str:
    """snap 為最新可讀（ok）月份的快照，沒有則 None。broken_month 是比它更新、卻讀不出來的月份（有就顯示警告）。"""
    parts = []
    if broken_month:
        parts.append(f'<p class="miss-note">The data for {e(broken_month)} could not be read; ask an uploader to run ingest_month again.</p>')
    if snap is not None:
        month = snap["meta"]["report_month"]
        parts.append(f'<section class="home">{_search(month)}{_tiles(snap, th)}'
                     f'<p class="home-links"><a href="/ui/{e(month)}/report.html">Monthly report</a><a href="/ui/mcp">MCP setup for Claude or OpenCode</a></p></section>')
    elif not broken_month:
        parts.append('<p class="empty">Nothing ingested yet. An uploader must upload a month and call ingest_month first.</p>')
    if months:
        parts.append(f'<section class="home-foot">{_history(months)}</section>')
    return "".join(parts)
