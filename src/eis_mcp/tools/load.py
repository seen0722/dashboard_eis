"""部門負載與產能。load% 的分母是「有填報的人數」不是編制——docstring 要講。"""
from __future__ import annotations
from mcp.server.mcpserver import Context, MCPServer
from ...portfolio.entities import MONTHS
from ..state import ServerState
from ._common import guarded, resolve_month, with_meta


def register(mcp: MCPServer, state: ServerState) -> None:
    @mcp.tool()
    def get_dept_loads(ctx: Context, month: str | None = None, min_util: float | None = None) -> dict:
        """Department load rows from the Control Lists: dept_code, dept_name, function, keyed_in[12] (people who reported),
        allocated[12] (FTE managers allocated), util[12] = round(allocated / keyed_in * 100) as an integer percent, or null
        for a month nobody keyed in, plus latest_util for meta.latest_month. The denominator is people who keyed in, not
        headcount. min_util is a percent (e.g. 85 = 85%) and keeps rows with latest_util >= min_util; rows whose
        latest_util is null are always excluded when min_util is given. Sorted by latest_util descending, null rows last,
        then dept_code. Returns {"meta", "latest_month", "count", "loads"}."""
        def go(p):
            _, snap = resolve_month(state, month)
            lm = snap["meta"]["latest_month"]
            rows = [{**r, "latest_util": r["util"][lm - 1]} for r in snap["loads"]]
            if min_util is not None:
                rows = [r for r in rows if r["latest_util"] is not None and r["latest_util"] >= min_util]
            rows.sort(key=lambda r: (r["latest_util"] is None, -r["latest_util"] if r["latest_util"] is not None else 0, r["dept_code"]))
            return with_meta(snap, latest_month=lm, count=len(rows), loads=rows)
        return guarded(state, ctx, "get_dept_loads", {"month": month, "min_util": min_util}, go)

    @mcp.tool()
    def get_capacity(ctx: Context, month: str | None = None) -> dict:
        """Capacity ceiling per calendar month (sum of keyed-in people across departments), Jan..Dec, from the Control Lists.
        Returns {"meta", "months": ["Jan", ...], "capacity": [12 numbers]}. Months after meta.latest_month carry the last
        reported value forward."""
        def go(p):
            _, snap = resolve_month(state, month)
            return with_meta(snap, months=list(MONTHS), capacity=snap["capacity"])
        return guarded(state, ctx, "get_capacity", {"month": month}, go)
