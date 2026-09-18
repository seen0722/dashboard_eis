"""uploader 用的 tools：ingest_month、list_months（list_months 兩種角色都可）。"""
from __future__ import annotations
import datetime as dt
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from ...portfolio.pipeline import INPUT_GLOBS, InputUnreadable, MissingInput, NoManpowerMonth
from ..ingest import IngestBusy, run_ingest
from ..state import ServerState
from ._common import guarded


def register(mcp: MCPServer, state: ServerState) -> None:
    @mcp.tool()
    def ingest_month(report_month: str, ctx: Context, today: str | None = None) -> dict:
        """Build the snapshot for one month from the Excel pack already uploaded to /upload/{report_month}. Uploader role only.

        Args: report_month "YYYYMM"; today "YYYY-MM-DD" (optional) as the reference date for overdue/upcoming milestones,
        pass it when re-running a past month. Returns status "ok" with summary/health/issues_count/warnings, or
        status "rejected_pii" (nothing written) with the offending fragments. Errors name what to do next.
        """
        def go(p):
            try:
                return run_ingest(state, report_month, today or dt.date.today().isoformat(), p.name)
            except ValueError as ex:
                raise ToolError(str(ex)) from None
            except IngestBusy:
                raise ToolError(f"busy: an ingest for {report_month} is already running. Wait, then call list_months to see its result.") from None
            except MissingInput as ex:
                want = ", ".join(f"{k} ({INPUT_GLOBS[k]})" for k in ex.missing)
                raise ToolError(f"missing_input: {want} not found in input/{report_month}. "
                                f"Upload the pack first: scripts/eis-upload.sh {report_month} <dir>") from None
            except InputUnreadable as ex:
                raise ToolError(f"input_unreadable: {ex}. Re-export that file from EIS/PM and upload it again.") from None
            except NoManpowerMonth as ex:
                raise ToolError(f"no_manpower_month: {ex}. Check the Resource Summary has at least one month with non-zero Total EIS 人力.") from None
        return guarded(state, ctx, "ingest_month", {"report_month": report_month, "today": today}, go, requires="uploader")

    @mcp.tool()
    def list_months(ctx: Context) -> dict:
        """List every month the server knows: status (ok | broken | uploaded_only), the uploaded files with uploader and time,
        and the last ingest (by, at, status). Newest first. Use it to pick a month or to see whether an upload was ingested."""
        return guarded(state, ctx, "list_months", {}, lambda p: {"months": state.store.months()})
