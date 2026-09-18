"""MCP resources。eis://months 是靜態 URI，SDK 不允許注入 Context，因此讀它不進稽核（list_months tool 有）。"""
from __future__ import annotations
import json
import time
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError
from ..state import ServerState
from ..store import UnknownMonth
from ._common import principal


def register(mcp: MCPServer, state: ServerState) -> None:
    @mcp.resource("eis://months", mime_type="application/json")
    def months() -> str:
        """Every month the server knows, with status, uploads and last ingest (same as the list_months tool)."""
        return json.dumps({"months": state.store.months()}, ensure_ascii=False)

    @mcp.resource("eis://{month}/report.html", mime_type="text/html")
    def report(month: str, ctx: Context) -> str:
        """The self-contained monthly portfolio review HTML for {month} (YYYYMM), as produced by ingest_month."""
        t0 = time.monotonic(); p = principal(state, ctx); uri = f"eis://{month}/report.html"
        try:
            html = state.store.report_html(month)
        except UnknownMonth:
            state.audit.record(p, "resource", uri, {"month": month}, "error", int((time.monotonic() - t0) * 1000), "unknown_month")
            raise ResourceNotFoundError(f"no report for {month}; read eis://months to see ingested months") from None
        state.audit.record(p, "resource", uri, {"month": month}, "ok", int((time.monotonic() - t0) * 1000))
        return html
