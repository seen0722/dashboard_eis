"""/ui/* 的 route handler。每個 handler：解析參數 → 讀快照 → queries → pages → respond()（PII 出口檢查 + audit）。"""
from __future__ import annotations
import datetime as dt
import time
from collections.abc import Callable
from html import escape as e
from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from ...portfolio.render.pii import find_pii
from ..state import ServerState
from ..store import MONTH_RE, SnapshotBroken, UnknownMonth
from . import pages_overview
from .shell import render_error, render_shell


class WebError(Exception):
    def __init__(self, status: int, title: str, body: str, detail: str = ""):
        super().__init__(title)
        self.status, self.title, self.body, self.detail = status, title, body, detail or title


def ok_months(state: ServerState) -> list[str]:
    return [m["month"] for m in state.store.months() if m["status"] == "ok"]


def load_snap(state: ServerState, month: str) -> dict:
    if not MONTH_RE.match(month):
        raise WebError(404, f"No snapshot for {month}", "<p>Months are written YYYYMM, e.g. 202609.</p>", "unknown_month")
    try:
        return state.store.load_snapshot(month)
    except UnknownMonth:
        raise WebError(404, f"No snapshot for {month}", "<p>That month has not been ingested.</p>", "unknown_month") from None
    except SnapshotBroken:
        raise WebError(503, f"Snapshot for {month} is unreadable",
                       f"<p>Ask an uploader to run <code>ingest_month('{e(month)}')</code> again.</p>", "snapshot_broken") from None


def int_param(request: Request, name: str, default: int, lo: int, hi: int) -> int:
    raw = request.query_params.get(name)
    if raw is None or raw == "":
        return default
    try:
        v = int(raw)
    except ValueError:
        raise WebError(400, f"Bad {name}", f"<p>{e(name)} must be a whole number between {lo} and {hi}.</p>", f"bad_{name}") from None
    if not lo <= v <= hi:
        raise WebError(400, f"Bad {name}", f"<p>{e(name)} must be between {lo} and {hi}.</p>", f"bad_{name}")
    return v


def float_param(request: Request, name: str, lo: float, hi: float) -> float | None:
    raw = request.query_params.get(name)
    if raw is None or raw == "":
        return None
    try:
        v = float(raw)
    except ValueError:
        raise WebError(400, f"Bad {name}", f"<p>{e(name)} must be a number between {lo:g} and {hi:g}.</p>", f"bad_{name}") from None
    if not lo <= v <= hi:
        raise WebError(400, f"Bad {name}", f"<p>{e(name)} must be between {lo:g} and {hi:g}.</p>", f"bad_{name}")
    return v


def date_param(request: Request, name: str = "today") -> str:
    raw = request.query_params.get(name)
    if not raw:
        return dt.date.today().isoformat()
    try:
        return dt.date.fromisoformat(raw).isoformat()
    except ValueError:
        raise WebError(400, f"Bad {name}", f"<p>{e(name)} must be YYYY-MM-DD.</p>", f"bad_{name}") from None


async def respond(state: ServerState, request: Request, build: Callable[[list[str]], str | Response]) -> Response:
    """build(months) 回 HTML 字串（會過 PII 檢查後以 200 送出）或 Response（redirect 等，原樣送出）。"""
    t0 = time.monotonic(); path = request.url.path; args = dict(request.query_params)

    def ms() -> int:
        return int((time.monotonic() - t0) * 1000)

    months = ok_months(state)
    try:
        out = build(months)
    except WebError as ex:
        state.audit.record(None, "web", path, args, "error", ms(), ex.detail)
        return HTMLResponse(render_error(ex.status, ex.title, ex.body, months), status_code=ex.status)
    if isinstance(out, Response):
        state.audit.record(None, "web", path, args, "ok", ms())
        return out
    hits = find_pii(out)
    if hits:
        state.audit.record(None, "web", path, args, "rejected_pii", ms(), "; ".join(hits[:5]))
        body = f"<p>This page was withheld: it contained {len(hits)} PII-shaped fragment(s). Tell the server owner; an uploader should fix the source and re-run ingest_month.</p>"
        return HTMLResponse(render_error(503, "Page withheld", body, months), status_code=503)
    state.audit.record(None, "web", path, args, "ok", ms())
    return HTMLResponse(out)


def register_routes(mcp: MCPServer, state: ServerState) -> None:
    @mcp.custom_route("/ui", methods=["GET"])
    async def ui_root(request: Request) -> Response:
        return await respond(state, request, lambda ok: RedirectResponse("/ui/", status_code=307))

    @mcp.custom_route("/ui/", methods=["GET"])
    async def months(request: Request) -> Response:
        def build(ok):
            return render_shell(title="EIS project status", body=pages_overview.months_body(state.store.months()), months=ok, active="months")
        return await respond(state, request, build)

    @mcp.custom_route("/ui/{month}/report.html", methods=["GET"])
    async def report(request: Request) -> Response:
        month = request.path_params["month"]

        def build(ok):
            load_snap(state, month)          # 404/503 規則與其他頁一致
            return state.store.report_html(month)
        return await respond(state, request, build)

    @mcp.custom_route("/ui/{month}/", methods=["GET"])
    async def overview(request: Request) -> Response:
        month = request.path_params["month"]

        def build(ok):
            if month == "latest":
                latest = state.store.latest_month()
                if latest is None:
                    raise WebError(404, "Nothing ingested yet", "<p>An uploader must upload a month and call ingest_month first.</p>", "no_snapshot")
                return RedirectResponse(f"/ui/{latest}/", status_code=307)
            snap = load_snap(state, month)
            return render_shell(title="Overview", body="<section><p class=\"empty\">Overview arrives in the next task.</p></section>",
                                months=ok, month=month, suffix="", meta=snap["meta"], active="overview")
        return await respond(state, request, build)
