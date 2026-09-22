"""跨月比較：同一專案兩份快照的欄位差異，以及 ingest 時抓到的「歷史月份數字被改」清單。查詢邏輯在 queries.py。"""
from __future__ import annotations
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from .. import queries
from ..queries import CORRECTION_CHECK, TOL, diff_values  # noqa: F401  舊 import 路徑保留（tests 用）
from ..state import ServerState
from ._common import guarded, resolve_month, with_meta


def register(mcp: MCPServer, state: ServerState) -> None:
    @mcp.tool()
    def diff_project(code: str, month_a: str, month_b: str, ctx: Context) -> dict:
        """Compare one project's snapshot record between two ingested months. Returns {"code", "month_a", "month_b",
        "meta_a", "meta_b", "changed": {field: {"a", "b"}}}: only fields that differ appear; nested fields (dates, pva)
        are compared key by key; numeric lists (fte, ntd, plan, actual) use a 0.05 tolerance; task/history lists report
        only a count change as {"a_count", "b_count"}. An empty "changed" means identical."""
        def go(p):
            _, sa = resolve_month(state, month_a)
            _, sb = resolve_month(state, month_b)
            try:
                return queries.diff(sa, sb, code)
            except queries.NotFound as ex:
                raise ToolError(f"not_found: {ex}. Use get_project to find the right code.") from None
        return guarded(state, ctx, "diff_project", {"code": code, "month_a": month_a, "month_b": month_b}, go)

    @mcp.tool()
    def get_corrections(ctx: Context, month: str | None = None) -> dict:
        """Past-month numbers that changed between the previous snapshot and this one (PM corrected history after the fact).
        Each row: level, check == "cross_month_correction", detail ("<name> <Mon> FTE <old> -> <new>"), source, code.
        Returns {"meta", "count", "corrections"}. Empty for the first ingested month."""
        def go(p):
            _, snap = resolve_month(state, month)
            return with_meta(snap, **queries.corrections(snap))
        return guarded(state, ctx, "get_corrections", {"month": month}, go)
