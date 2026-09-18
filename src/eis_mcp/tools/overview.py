"""組合總覽：報告第一屏的 exceptions、health 表、以及里程碑視窗。"""
from __future__ import annotations
import datetime as dt
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from ...portfolio.model.rules import days_between
from ..state import ServerState
from ._common import guarded, resolve_month, with_meta

MILESTONES = ("evt", "dvt", "pvt", "mp")


def upcoming_milestones(snap: dict, today: str, weeks: int) -> list[dict]:
    """與 rules._active() 同條件：只看 in_briefing 且非 Suspended 的專案；視窗前後各 weeks 週；已過期者 days_left 為負。"""
    span = weeks * 7
    out = []
    for p in snap["projects"]:
        if not p.get("in_briefing") or p.get("stage_cat") == "Suspended":
            continue
        for ms in MILESTONES:
            d = p["dates"].get(ms)
            if not d:
                continue
            left = days_between(d, today)
            if -span <= left <= span:
                out.append({"code": p["code"], "name": p["name"], "stage_cat": p["stage_cat"], "milestone": ms, "date": d, "days_left": left})
    return sorted(out, key=lambda r: (r["days_left"], r["code"]))


def _check_date(s: str) -> str:
    try:
        dt.date.fromisoformat(s)
    except ValueError:
        raise ToolError(f"bad_date: '{s}' must be YYYY-MM-DD") from None
    return s


def register(mcp: MCPServer, state: ServerState) -> None:
    @mcp.tool()
    def get_exceptions(ctx: Context, month: str | None = None) -> dict:
        """The 'Decisions this month' list of the portfolio report: ranked exceptions with evidence, the decision asked for,
        source and affected project codes. Returns {"meta", "count", "exceptions"} exactly as stored in the snapshot.
        month "YYYYMM" defaults to the latest ingested month."""
        def go(p):
            _, snap = resolve_month(state, month)
            return with_meta(snap, count=len(snap["exceptions"]), exceptions=snap["exceptions"])
        return guarded(state, ctx, "get_exceptions", {"month": month}, go)

    @mcp.tool()
    def get_health(ctx: Context, month: str | None = None) -> dict:
        """Data-health table: each row has level (decide | track | ok), check id, label, count, the project names involved and
        the source file. Returns {"meta", "health"} as stored in the snapshot. month "YYYYMM" defaults to the latest month."""
        def go(p):
            _, snap = resolve_month(state, month)
            return with_meta(snap, health=snap["health"])
        return guarded(state, ctx, "get_health", {"month": month}, go)

    @mcp.tool()
    def get_upcoming_milestones(ctx: Context, weeks: int = 8, month: str | None = None, today: str | None = None) -> dict:
        """EVT/DVT/PVT/MP dates within +/- weeks*7 days of today for active (in briefing, not suspended) projects.
        days_left < 0 means already passed. Returns {"meta", "today", "weeks", "milestones": [{code, name, stage_cat,
        milestone, date, days_left}]} sorted by days_left. today "YYYY-MM-DD" defaults to the server date."""
        def go(p):
            _, snap = resolve_month(state, month)
            t = _check_date(today) if today else dt.date.today().isoformat()
            return with_meta(snap, today=t, weeks=weeks, milestones=upcoming_milestones(snap, t, weeks))
        return guarded(state, ctx, "get_upcoming_milestones", {"weeks": weeks, "month": month, "today": today}, go)
