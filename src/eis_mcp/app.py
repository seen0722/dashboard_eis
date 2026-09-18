"""組裝 Starlette app：/mcp（Streamable HTTP）+ POST /upload/{month}，共用 Bearer middleware。"""
from __future__ import annotations
import time
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from ..portfolio.config import Config, load_config
from .auth import Audit, BearerAuthMiddleware, Principal
from .state import ServerState
from .store import ALLOWED_DESCRIPTIONS, MONTH_RE, Store, classify_filename

INSTRUCTIONS = (
    "EIS project status for BU10, built from the monthly EIS Excel export. Every tool response carries "
    "meta.report_month and meta.latest_month: quote them when answering. Values come straight from the "
    "snapshot; never infer or fill numbers the tools did not return. Uploaders upload the monthly pack over "
    "HTTP (scripts/eis-upload.sh) and then call ingest_month; everyone else queries with get_project, "
    "search_projects, get_exceptions, get_health, get_upcoming_milestones, get_dept_loads, get_capacity, "
    "diff_project, get_corrections and list_months."
)


def register_upload_route(mcp: MCPServer, state: ServerState) -> None:
    @mcp.custom_route("/upload/{month}", methods=["POST"])
    async def upload(request: Request) -> Response:
        t0 = time.monotonic()
        month = request.path_params["month"]
        p: Principal = request.state.principal
        action = f"upload:{month}"

        def done(status: str, detail: str = "") -> None:
            state.audit.record(p, "upload", action, {"month": month}, status, int((time.monotonic() - t0) * 1000), detail)

        if not MONTH_RE.match(month):
            done("error", "bad_month")
            return JSONResponse({"error": "bad_month", "detail": "month must be YYYYMM, e.g. /upload/202610"}, status_code=400)
        if p.role != "uploader":
            done("forbidden")
            return JSONResponse({"error": "forbidden", "detail": f"token '{p.name}' has role '{p.role}'; uploads need an uploader token"}, status_code=403)
        form = await request.form()
        files = [f for f in form.getlist("file") if isinstance(f, UploadFile)]
        if not files:
            done("error", "no_files")
            return JSONResponse({"error": "no_files", "detail": "send one or more multipart fields named 'file'"}, status_code=400)
        rejected = [f.filename or "" for f in files if classify_filename(f.filename or "") is None]
        if rejected:
            done("error", "bad_filename: " + ", ".join(rejected))
            return JSONResponse({"error": "bad_filename", "rejected": rejected, "allowed": ALLOWED_DESCRIPTIONS,
                                 "detail": "nothing was stored; rename or drop the rejected files and resend the whole pack"}, status_code=400)
        stored = []
        for f in files:
            rec = state.store.register_upload(month, f.filename, await f.read(), p.name)
            rec["category"] = classify_filename(f.filename)
            stored.append(rec)
        done("ok", ", ".join(s["name"] for s in stored))
        return JSONResponse({"month": month, "stored": stored})


def build_app(store: Store, tokens: dict[str, Principal], *, cfg: Config | None = None,
              host: str = "0.0.0.0", allowed_hosts: list[str] | None = None) -> Starlette:
    state = ServerState(store, tokens, Audit(store.audit_db), cfg or load_config())
    mcp = MCPServer("eis", instructions=INSTRUCTIONS)
    register_upload_route(mcp, state)
    if allowed_hosts:
        ts = TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=list(allowed_hosts), allowed_origins=[])
    else:
        ts = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = mcp.streamable_http_app(host=host, transport_security=ts)
    app.add_middleware(BearerAuthMiddleware, tokens=tokens)
    app.state.eis = state
    return app
