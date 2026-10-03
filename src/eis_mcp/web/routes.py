"""/ui/* 的 route handler。每個 handler：解析參數 → 讀快照 → queries → pages → respond()（PII 出口檢查 + audit）。"""
from __future__ import annotations
import datetime as dt
import logging
import time
from urllib.parse import urlsplit
from collections.abc import Callable
from html import escape as e
from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from ...portfolio.render.pii import find_pii
from ...portfolio.render.viz.embed import echarts_source
from ...portfolio.render.icon import PNG_180
from ...portfolio.render.viz.options import at_risk_rows
from ..state import ServerState
from ..store import MONTH_RE, SnapshotBroken, UnknownMonth
from .. import queries
from ..queries import snap_day
from . import pages_decisions, pages_health, pages_home, pages_load, pages_mcp, pages_overview, pages_project, pages_projects
from .shell import SITE, SITE_ZH, render_error, render_shell

log = logging.getLogger("eis_mcp.web")


class WebError(Exception):
    def __init__(self, status: int, title: str, body: str, detail: str = ""):
        super().__init__(title)
        self.status, self.title, self.body, self.detail = status, title, body, detail or title


def ok_months(state: ServerState) -> list[str]:
    return [m["month"] for m in state.store.months() if m["status"] == "ok"]


def load_snap(state: ServerState, month: str) -> dict:
    if not MONTH_RE.match(month):
        raise WebError(404, f"No data for {month}", "<p>Months are written YYYYMM, e.g. 202609.</p>", "unknown_month")
    try:
        return state.store.load_snapshot(month)
    except UnknownMonth:
        raise WebError(404, f"No data for {month}", "<p>That month has not been ingested.</p>", "unknown_month") from None
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


def date_param(request: Request, default: str, name: str = "today") -> str:
    raw = request.query_params.get(name)
    if not raw:
        return default
    try:
        return dt.date.fromisoformat(raw).isoformat()
    except ValueError:
        raise WebError(400, f"Bad {name}", f"<p>{e(name)} must be YYYY-MM-DD.</p>", f"bad_{name}") from None


class Text:
    """非 HTML 的文字回應（例如給 agent 讀的 markdown）。與 HTML 一樣過 PII 出口檢查，只是 media type 不同。"""
    def __init__(self, body: str, media_type: str):
        self.body, self.media_type = body, media_type


async def respond(state: ServerState, request: Request, build: Callable[[list[str]], "str | Text | Response"]) -> Response:
    """build(months) 回 HTML 字串或 Text（都會過 PII 檢查後以 200 送出），或 Response（redirect 等，原樣送出）。"""
    t0 = time.monotonic(); path = request.url.path; args = dict(request.query_params)

    def ms() -> int:
        return int((time.monotonic() - t0) * 1000)

    months = ok_months(state)
    try:
        out = build(months)
    except WebError as ex:
        state.audit.record(None, "web", path, args, "error", ms(), ex.detail)
        return HTMLResponse(render_error(ex.status, ex.title, ex.body, months), status_code=ex.status)
    except Exception as ex:  # noqa: BLE001 — 任何未預期錯誤都要有 audit 列與乾淨的 500 頁，不漏 traceback
        log.exception("web handler failed: %s", path)
        state.audit.record(None, "web", path, args, "error", ms(), repr(ex)[:200])
        return HTMLResponse(render_error(500, "Server error", "<p>Something went wrong while building this page. The server log has the details.</p>", months), status_code=500)
    if isinstance(out, Response):
        state.audit.record(None, "web", path, args, "ok", ms())
        return out
    text = out.body if isinstance(out, Text) else out
    hits = find_pii(text)
    if hits:
        state.audit.record(None, "web", path, args, "rejected_pii", ms(), "; ".join(hits[:5]))
        body = f"<p>This page was withheld: it contained {len(hits)} PII-shaped fragment(s). Tell the server owner; an uploader should fix the source and re-run ingest_month.</p>"
        return HTMLResponse(render_error(503, "Page withheld", body, months), status_code=503)
    state.audit.record(None, "web", path, args, "ok", ms())
    if isinstance(out, Text):
        return Response(out.body, media_type=out.media_type)
    return HTMLResponse(out)


def nav_count(snap: dict) -> int:
    """側欄 Decisions 的件數 badge：與月報例外清單同一份。"""
    return len(snap.get("exceptions") or [])


def safe_page(page: str) -> str:
    """/ui/go 的 page 參數只能是 /ui/{month}/ 之下的相對路徑（可帶 query）：擋 scheme、host、開頭斜線、..、反斜線、控制字元，
    避免變成 open redirect 或跳出 /ui/。"""
    parts = urlsplit(page)
    if (parts.scheme or parts.netloc or page.startswith("/") or "\\" in page or any(ord(c) < 32 for c in page)
            or ".." in parts.path.split("/")):
        raise WebError(400, "Bad page", "<p>That page is not under this site.</p>", "bad_page")
    return page


def register_routes(mcp: MCPServer, state: ServerState) -> None:
    @mcp.custom_route("/ui/go", methods=["GET"])
    async def go(request: Request) -> Response:
        month = (request.query_params.get("month") or "").strip()
        page = request.query_params.get("page") or ""

        def build(ok):
            load_snap(state, month)                       # 月份格式錯或沒有快照 → 404，與其他頁一致
            return RedirectResponse(f"/ui/{month}/{safe_page(page)}", status_code=307)
        return await respond(state, request, build)

    @mcp.custom_route("/ui", methods=["GET"])
    async def ui_root(request: Request) -> Response:
        return await respond(state, request, lambda ok: RedirectResponse("/ui/", status_code=307))

    @mcp.custom_route("/ui/", methods=["GET"])
    async def months(request: Request) -> Response:
        def build(ok):
            months = state.store.months()                    # newest first
            latest = next((m["month"] for m in months if m["status"] == "ok"), None)
            # 比最新可讀月份還新、卻讀不出來的月份要明講；首頁不因它 503，仍說明用途並顯示最新可讀的那個月
            broken = next((m["month"] for m in months if m["status"] == "broken" and (latest is None or m["month"] > latest)), None)
            snap = state.store.load_snapshot(latest) if latest else None
            body = pages_home.home_body(months, snap, state.cfg.thresholds, broken)
            # 側欄帶最新月份的導覽、頁首帶資料日期；首頁本身只放搜尋、狀態卡與連結
            return render_shell(title=SITE, title_zh=SITE_ZH, body=body, months=ok, active="home", month=latest if snap else None,
                                meta=snap["meta"] if snap else None, decisions=nav_count(snap) if snap else None)
        return await respond(state, request, build)

    async def tool_list() -> list[tuple[str, str]]:
        return sorted((t.name, pages_mcp.first_sentence(t.description)) for t in await mcp.list_tools())

    @mcp.custom_route("/ui/mcp", methods=["GET"])
    async def mcp_page(request: Request) -> Response:
        tools = await tool_list(); host = pages_mcp.host_of(request.headers.get("host"))

        def build(ok):
            return render_shell(title="Use it from an AI agent", title_zh="用 AI agent 查詢", body=pages_mcp.mcp_body(host, tools), months=ok, active="mcp")
        return await respond(state, request, build)

    @mcp.custom_route("/ui/mcp.md", methods=["GET"])
    async def mcp_markdown(request: Request) -> Response:
        tools = await tool_list(); host = pages_mcp.host_of(request.headers.get("host"))

        def build(ok):
            try:
                return Text(pages_mcp.guide_markdown(host, tools), "text/markdown; charset=utf-8")
            except pages_mcp.GuideMissing:
                raise WebError(503, "Setup guide not installed",
                               "<p>docs/eis-mcp-client-setup.md is missing on this server; ask the server owner to re-run deploy/install.sh.</p>", "guide_missing") from None
        return await respond(state, request, build)

    @mcp.custom_route("/ui/{month}/report.html", methods=["GET"])
    async def report(request: Request) -> Response:
        # 網頁不再提供月報（需求方 2026-10-03：月報像網站、打開後回不到網頁）。月報仍由 ingest 產生，
        # 從 CLI out/ 或 MCP 資源 eis://{月}/report.html 取得；舊書籤轉到該月總覽，不給 404。
        month = request.path_params["month"]
        return await respond(state, request, lambda ok: RedirectResponse(f"/ui/{month}/", status_code=301))

    @mcp.custom_route("/ui/{month}/projects", methods=["GET"])
    async def projects(request: Request) -> Response:
        month = request.path_params["month"]
        qp = request.query_params
        filters = {k: (qp.get(k) or "").strip() for k in ("stage_cat", "group", "customer", "biz_type", "category", "q", "sort", "dir")}

        def build(ok):
            snap = load_snap(state, month)
            hit = queries.exact_code(snap, filters["q"]) if filters["q"] and not any(filters[k] for k in ("stage_cat", "group", "customer", "biz_type", "category")) else None
            if hit:                                          # 完全相同的 code 或名稱直接進單案頁，不被子字串比對拖成列表
                return RedirectResponse(f"/ui/{month}/projects/{hit}", status_code=307)
            res = queries.search(snap, filters["stage_cat"] or None, filters["group"] or None, filters["customer"] or None, filters["q"] or None,
                                 filters["biz_type"] or None, filters["category"] or None)
            if filters["q"] and res["count"] == 1 and not any(filters[k] for k in ("stage_cat", "group", "customer", "biz_type", "category")):
                return RedirectResponse(f"/ui/{month}/projects/{res['projects'][0]['code']}", status_code=307)
            body = pages_projects.projects_body(month, snap, [x["code"] for x in res["projects"]], filters, state.cfg.thresholds,
                                                date_param(request, snap_day(snap)), queries.distinct(snap, "group"),
                                                queries.distinct(snap, "customer"), queries.distinct(snap, "category"))
            suffix = "projects" + (("?" + str(qp)) if str(qp) else "")
            return render_shell(title="Projects", body=body, months=ok, month=month, suffix=suffix, meta=snap["meta"], decisions=nav_count(snap), active="projects")
        return await respond(state, request, build)

    @mcp.custom_route("/ui/{month}/projects/{code}/diff", methods=["GET"])
    async def diff(request: Request) -> Response:
        month, code = request.path_params["month"], request.path_params["code"]
        to = (request.query_params.get("to") or "").strip()

        def build(ok):
            snap = load_snap(state, month)
            if not to:
                raise WebError(400, "Missing 'to'", f'<p>Add <code>?to=YYYYMM</code> to pick the month to compare with.</p>', "missing_to")
            if to == month:
                raise WebError(400, "Same month on both sides", f'<p>Pick a month other than {e(month)} for <code>to</code>.</p>', "same_month")
            other = load_snap(state, to)
            try:
                res = queries.diff(snap, other, code)
            except queries.NotFound as ex:
                raise WebError(404, "Project not found", f'<p>{e(str(ex), quote=False)}.</p><p><a href="/ui/{month}/projects">Back to the project list</a></p>', "not_found") from None
            return render_shell(title=f"Diff {res['code']}", body=pages_project.diff_body(month, res), months=ok, month=month,
                                suffix=f"projects/{res['code']}", meta=snap["meta"], decisions=nav_count(snap), active="projects")   # 換月份回單案頁，避免同月互比
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
                                    suffix="projects", meta=snap["meta"], decisions=nav_count(snap), active="projects")
            p = res["project"]; today = date_param(request, snap_day(snap))
            earlier = [m for m in ok if m < month]           # ok 是 newest first；前一個 ok 月份 = 小於本月的第一個
            prev = earlier[0] if earlier else None
            risk = next((r for r in at_risk_rows(snap, state.cfg.thresholds["mp_slip_days"]) if r["code"] == p["code"]), None)
            body = pages_project.project_body(month, p, today, snap["meta"]["latest_month"], prev, risk)
            return render_shell(title=p["name"], body=body, months=ok, month=month, suffix=f"projects/{p['code']}", meta=snap["meta"], decisions=nav_count(snap), active="projects")
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
            today = date_param(request, snap_day(snap))
            body = pages_overview.overview_body(snap, state.cfg.thresholds, today, weeks)
            return render_shell(title="Overview", body=body, months=ok, month=month, suffix="", meta=snap["meta"], decisions=nav_count(snap), active="overview")
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
                                suffix=suffix, meta=snap["meta"], decisions=nav_count(snap), active="loads")
        return await respond(state, request, build)

    @mcp.custom_route("/ui/static/icon-180.png", methods=["GET"])
    async def icon_png(request: Request) -> Response:
        # 網站圖示的 PNG 版（Safari 起始頁、舊版 Safari 分頁）；與 echarts 同樣不寫 audit
        if not PNG_180:                                       # 檔案缺漏時只少這個圖示，不影響其他頁面
            return Response(status_code=404)
        return Response(PNG_180, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})

    @mcp.custom_route("/ui/static/echarts.min.js", methods=["GET"])
    async def echarts_js(request: Request) -> Response:
        # vendor 靜態檔、不含資料：不過 PII 檢查也不寫 audit（每頁都會載一次，只是噪音）
        return Response(echarts_source(), media_type="application/javascript; charset=utf-8",
                        headers={"Cache-Control": "public, max-age=86400"})

    @mcp.custom_route("/ui/{month}/decisions", methods=["GET"])
    async def decisions(request: Request) -> Response:
        month = request.path_params["month"]

        def build(ok):
            snap = load_snap(state, month)
            return render_shell(title="Decisions this month", body=pages_decisions.decisions_body(snap, state.cfg.thresholds), months=ok, month=month,
                                suffix="decisions", meta=snap["meta"], decisions=nav_count(snap), active="decisions")
        return await respond(state, request, build)

    @mcp.custom_route("/ui/{month}/health", methods=["GET"])
    async def health(request: Request) -> Response:
        month = request.path_params["month"]

        def build(ok):
            snap = load_snap(state, month)
            return render_shell(title="Data health", body=pages_health.health_body(month, snap, queries.corrections(snap)), months=ok,
                                month=month, suffix="health", meta=snap["meta"], decisions=nav_count(snap), active="health")
        return await respond(state, request, build)

    @mcp.custom_route("/ui/{month}/corrections", methods=["GET"])
    async def corrections(request: Request) -> Response:
        month = request.path_params["month"]

        def build(ok):
            load_snap(state, month)                       # 月份不存在照樣 404
            return RedirectResponse(f"/ui/{month}/health", status_code=301)   # 2026-10-02 併入 Data health
        return await respond(state, request, build)
