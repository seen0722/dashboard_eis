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
from .. import queries
from . import pages_load, pages_overview, pages_project
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

    @mcp.custom_route("/ui/{month}/projects", methods=["GET"])
    async def projects(request: Request) -> Response:
        month = request.path_params["month"]
        qp = request.query_params
        filters = {k: (qp.get(k) or "").strip() for k in ("stage_cat", "group", "customer", "q")}

        def build(ok):
            snap = load_snap(state, month)
            res = queries.search(snap, filters["stage_cat"] or None, filters["group"] or None, filters["customer"] or None, filters["q"] or None)
            if filters["q"] and res["count"] == 1 and not any(filters[k] for k in ("stage_cat", "group", "customer")):
                return RedirectResponse(f"/ui/{month}/projects/{res['projects'][0]['code']}", status_code=307)
            body = pages_project.projects_body(month, res, filters, queries.distinct(snap, "group"), queries.distinct(snap, "customer"))
            suffix = "projects" + (("?" + str(qp)) if str(qp) else "")
            return render_shell(title="Projects", body=body, months=ok, month=month, suffix=suffix, meta=snap["meta"], active="projects")
        return await respond(state, request, build)

    @mcp.custom_route("/ui/{month}/projects/{code}/diff", methods=["GET"])
    async def diff(request: Request) -> Response:
        month, code = request.path_params["month"], request.path_params["code"]
        to = (request.query_params.get("to") or "").strip()

        def build(ok):
            snap = load_snap(state, month)
            if not to:
                raise WebError(400, "Missing 'to'", f'<p>Add <code>?to=YYYYMM</code> to pick the month to compare with.</p>', "missing_to")
            other = load_snap(state, to)
            try:
                res = queries.diff(snap, other, code)
            except queries.NotFound as ex:
                raise WebError(404, "Project not found", f'<p>{e(str(ex), quote=False)}.</p><p><a href="/ui/{month}/projects">Back to the project list</a></p>', "not_found") from None
            return render_shell(title=f"Diff {res['code']}", body=pages_project.diff_body(month, res), months=ok, month=month,
                                suffix=f"projects/{res['code']}/diff?to={to}", meta=snap["meta"], active="projects")
        return await respond(state, request, build)

    @mcp.custom_route("/ui/{month}/projects/{code}", methods=["GET"])
    async def project(request: Request) -> Response:
        month, code = request.path_params["month"], request.path_params["code"]

        def build(ok):
            snap = load_snap(state, month)
            try:
                res = queries.project(snap, code, state.cfg)
            except queries.NotFound as ex:
                raise WebError(404, "Project not found", f'<p>{e(str(ex), quote=False)}.</p><p><a href="/ui/{month}/projects">Back to the project list</a></p>', "not_found") from None
            if "candidates" in res:
                return render_shell(title="Projects", body=pages_project.candidates_body(month, res["candidates"], code), months=ok, month=month,
                                    suffix="projects", meta=snap["meta"], active="projects")
            p = res["project"]; today = date_param(request)
            later = [m for m in ok if m < month]           # ok 是 newest first；前一個 ok 月份 = 小於本月的第一個
            prev = later[0] if later else None
            body = pages_project.project_body(month, p, today, snap["meta"]["latest_month"], prev)
            return render_shell(title=p["name"], body=body, months=ok, month=month, suffix=f"projects/{p['code']}", meta=snap["meta"], active="projects")
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
            weeks = int_param(request, "weeks", int(state.cfg.thresholds.get("upcoming_weeks", 8)), 1, 52)
            today = date_param(request)
            body = pages_overview.overview_body(snap, state.cfg.thresholds, today, weeks)
            return render_shell(title="Overview", body=body, months=ok, month=month, suffix="", meta=snap["meta"], active="overview")
        return await respond(state, request, build)

    @mcp.custom_route("/ui/{month}/loads", methods=["GET"])
    async def loads(request: Request) -> Response:
        month = request.path_params["month"]

        def build(ok):
            snap = load_snap(state, month)
            min_util = float_param(request, "min_util", 0, 1000)
            res = queries.dept_loads(snap, min_util)
            suffix = "loads" + (f"?min_util={min_util:g}" if min_util is not None else "")
            return render_shell(title="Department loads", body=pages_load.loads_body(month, snap, res, min_util, float(state.cfg.thresholds.get("spare_capacity_pct", 85))), months=ok, month=month,
                                suffix=suffix, meta=snap["meta"], active="loads")
        return await respond(state, request, build)

    @mcp.custom_route("/ui/{month}/corrections", methods=["GET"])
    async def corrections(request: Request) -> Response:
        month = request.path_params["month"]

        def build(ok):
            snap = load_snap(state, month)
            return render_shell(title="Corrections", body=pages_load.corrections_body(month, queries.corrections(snap)), months=ok, month=month,
                                suffix="corrections", meta=snap["meta"], active="corrections")
        return await respond(state, request, build)
