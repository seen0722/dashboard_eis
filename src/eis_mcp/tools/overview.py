"""組合總覽：報告第一屏的 exceptions、health 表、以及里程碑視窗。查詢邏輯在 queries.py。"""
from __future__ import annotations
from mcp.server.mcpserver import Context, MCPServer
from .. import queries
from ..queries import MILESTONES, upcoming_milestones  # noqa: F401  舊 import 路徑保留（tests 用）
from ..state import ServerState
from ._common import check_date, guarded, resolve_month, with_meta


def register(mcp: MCPServer, state: ServerState) -> None:
    @mcp.tool()
    def get_exceptions(ctx: Context, month: str | None = None) -> dict:
        """The 'Decisions this month' list of the portfolio report: ranked exceptions with evidence, the decision asked for,
        source and affected project codes. Returns {"meta", "count", "exceptions"} exactly as stored in the snapshot.
        month "YYYYMM" defaults to the latest ingested month."""
        def go(p):
            _, snap = resolve_month(state, month)
            return with_meta(snap, **queries.exceptions(snap))
        return guarded(state, ctx, "get_exceptions", {"month": month}, go)

    @mcp.tool()
    def get_health(ctx: Context, month: str | None = None) -> dict:
        """Data-health table: each row has level (decide | track | ok), check id, label, count, the project names involved and
        the source file. Returns {"meta", "health"} as stored in the snapshot. month "YYYYMM" defaults to the latest month."""
        def go(p):
            _, snap = resolve_month(state, month)
            return with_meta(snap, **queries.health(snap))
        return guarded(state, ctx, "get_health", {"month": month}, go)

    @mcp.tool()
    def get_upcoming_milestones(ctx: Context, weeks: int = 8, month: str | None = None, today: str | None = None) -> dict:
        """EVT/DVT/PVT/MP dates within +/- weeks*7 days of today for active (in briefing, not terminated or suspended) projects.
        days_left < 0 means already passed. Returns {"meta", "today", "weeks", "milestones": [{code, name, stage_cat,
        milestone, date, days_left}]} sorted by days_left. today "YYYY-MM-DD" defaults to the Briefing snapshot date of that month."""
        def go(p):
            _, snap = resolve_month(state, month)
            t = check_date(today) if today else queries.snap_day(snap)
            return with_meta(snap, **queries.upcoming(snap, t, weeks))
        return guarded(state, ctx, "get_upcoming_milestones", {"weeks": weeks, "month": month, "today": today}, go)
