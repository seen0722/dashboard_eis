"""所有 tool 共用：取呼叫者、角色檢查、稽核、PII 出口保險、月份解析。"""
from __future__ import annotations
import json
import time
from collections.abc import Callable
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from ...portfolio.render.pii import find_pii
from ..auth import Principal, principal_from_headers
from ..state import ServerState
from ..store import SnapshotBroken, UnknownMonth


def principal(state: ServerState, ctx: Context) -> Principal:
    p = principal_from_headers(ctx.headers or {}, state.tokens)
    if p is None:
        raise ToolError("unauthorized: this connection carries no valid token; reconnect with 'Authorization: Bearer <token>'")
    return p


def guarded(state: ServerState, ctx: Context, action: str, args: dict, fn: Callable[[Principal], dict], *, requires: str | None = None) -> dict:
    t0 = time.monotonic()
    p = principal(state, ctx)

    def ms() -> int:
        return int((time.monotonic() - t0) * 1000)

    if requires and p.role != requires:
        state.audit.record(p, "tool", action, args, "forbidden", ms())
        raise ToolError(f"forbidden: {action} requires role '{requires}'; token '{p.name}' has role '{p.role}'. Ask an uploader to run it.")
    try:
        out = fn(p)
    except ToolError as ex:
        state.audit.record(p, "tool", action, args, "error", ms(), str(ex)); raise
    except Exception as ex:
        state.audit.record(p, "tool", action, args, "error", ms(), repr(ex)); raise
    hits = find_pii(json.dumps(out, ensure_ascii=False))
    if hits:
        state.audit.record(p, "tool", action, args, "rejected_pii", ms(), "; ".join(hits[:5]))
        raise ToolError(f"rejected_pii: the {action} response contained {len(hits)} PII-shaped fragment(s) and was withheld. "
                        "Tell the server owner; an uploader should fix the source and re-run ingest_month for this month.")
    state.audit.record(p, "tool", action, args, "ok", ms())
    return out


def resolve_month(state: ServerState, month: str | None) -> tuple[str, dict]:
    store = state.store
    if month is None:
        month = store.latest_month()
        if month is None:
            raise ToolError("no_snapshot: nothing has been ingested yet. An uploader must upload a month and call ingest_month first.")
    try:
        return month, store.load_snapshot(month)
    except UnknownMonth:
        avail = [m["month"] for m in store.months() if m["status"] == "ok"]
        raise ToolError(f"unknown_month: {month} has no snapshot. Available: {', '.join(avail) or 'none'}. Call list_months for details.") from None
    except SnapshotBroken:
        raise ToolError(f"snapshot_broken: portfolio.json for {month} is unreadable. Ask an uploader to run ingest_month('{month}') again.") from None


def with_meta(snap: dict, **payload) -> dict:
    return {"meta": snap["meta"], **payload}
