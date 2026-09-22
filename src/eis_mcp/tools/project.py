"""單案查詢與篩選。查詢邏輯在 queries.py；這裡只剩 docstring、參數與 guarded()。"""
from __future__ import annotations
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from .. import queries
from ..queries import resolve_project  # noqa: F401  舊 import 路徑保留
from ..state import ServerState
from ._common import guarded, resolve_month, with_meta


def register(mcp: MCPServer, state: ServerState) -> None:
    @mcp.tool()
    def get_project(query: str, ctx: Context, month: str | None = None) -> dict:
        """Look up one project by PROJECTCODE (BR0000xxxxxx), project name or known alias.

        Returns {"meta", "project"} with the full snapshot record: code, name, group, family, customer, product, stage,
        stage_cat, dates {kickoff, evt, dvt, pvt, mp, mp_orig}, in_briefing, in_control_list, has_plan, fte[12], ntd[12],
        pva {role: {plan[12], actual[12], ntd[12]}}, tasks, history. Month indexes are Jan..Dec (index 0 = Jan).
        If several projects match, returns {"candidates": [...]} instead; call again with the exact code.
        month "YYYYMM" is optional and defaults to the latest ingested month.
        """
        def go(p):
            _, snap = resolve_month(state, month)
            try:
                return with_meta(snap, **queries.project(snap, query, state.cfg))
            except queries.NotFound as ex:
                raise ToolError(f"not_found: {ex}. Try search_projects(text=...) or list_months.") from None
        return guarded(state, ctx, "get_project", {"query": query, "month": month}, go)

    @mcp.tool()
    def search_projects(ctx: Context, stage_cat: str | None = None, group: str | None = None, customer: str | None = None,
                        text: str | None = None, month: str | None = None) -> dict:
        """List projects, optionally filtered. stage_cat is one of RFQ / RFI, POC, Execution, MP, Sustain / EOP, Suspended, Other
        (case-insensitive). group and customer match whole values; text matches a substring of name, customer or product.
        Returns {"meta", "count", "projects": [{code, name, stage, stage_cat, customer, group, latest_fte}]} where latest_fte is
        the FTE of meta.latest_month. Use get_project for the full record.
        """
        def go(p):
            _, snap = resolve_month(state, month)
            return with_meta(snap, **queries.search(snap, stage_cat, group, customer, text))
        return guarded(state, ctx, "search_projects", {"stage_cat": stage_cat, "group": group, "customer": customer, "text": text, "month": month}, go)
