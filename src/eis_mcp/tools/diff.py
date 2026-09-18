"""跨月比較：同一專案兩份快照的欄位差異，以及 ingest 時抓到的「歷史月份數字被改」清單。"""
from __future__ import annotations
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from ..state import ServerState
from ._common import guarded, resolve_month, with_meta

TOL = 0.05   # 與 model/diff.cross_month_corrections 的預設容差一致
CORRECTION_CHECK = "cross_month_correction"


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def diff_values(a, b, tol: float = TOL) -> dict | None:
    if isinstance(a, dict) and isinstance(b, dict):
        out = {}
        for k in sorted(set(a) | set(b)):
            d = diff_values(a.get(k), b.get(k), tol)
            if d is not None:
                out[k] = d
        return out or None
    if isinstance(a, list) and isinstance(b, list):
        if a and b and all(_is_num(x) for x in a + b):
            if len(a) != len(b) or any(abs(x - y) > tol for x, y in zip(a, b)):
                return {"a": a, "b": b}
            return None
        if any(isinstance(x, dict) for x in a + b):
            return None if len(a) == len(b) else {"a_count": len(a), "b_count": len(b)}
        return None if a == b else {"a": a, "b": b}
    if _is_num(a) and _is_num(b):
        return None if abs(a - b) <= tol else {"a": a, "b": b}
    return None if a == b else {"a": a, "b": b}


def register(mcp: MCPServer, state: ServerState) -> None:
    @mcp.tool()
    def diff_project(code: str, month_a: str, month_b: str, ctx: Context) -> dict:
        """Compare one project's snapshot record between two ingested months. Returns {"code", "month_a", "month_b",
        "meta_a", "meta_b", "changed": {field: {"a", "b"}}}: only fields that differ appear; nested fields (dates, pva)
        are compared key by key; numeric lists (fte, ntd, plan, actual) use a 0.05 tolerance; task/history lists report
        only a count change as {"a_count", "b_count"}. An empty "changed" means identical."""
        def go(p):
            ma, sa = resolve_month(state, month_a)
            mb, sb = resolve_month(state, month_b)
            pa = next((q for q in sa["projects"] if q["code"].upper() == code.upper()), None)
            pb = next((q for q in sb["projects"] if q["code"].upper() == code.upper()), None)
            if pa is None or pb is None:
                where = " and ".join(m for m, q in ((ma, pa), (mb, pb)) if q is None)
                raise ToolError(f"not_found: {code} is not in the snapshot for {where}. Use get_project to find the right code.")
            return {"code": pa["code"], "month_a": ma, "month_b": mb, "meta_a": sa["meta"], "meta_b": sb["meta"],
                    "changed": diff_values(pa, pb) or {}}
        return guarded(state, ctx, "diff_project", {"code": code, "month_a": month_a, "month_b": month_b}, go)

    @mcp.tool()
    def get_corrections(ctx: Context, month: str | None = None) -> dict:
        """Past-month numbers that changed between the previous snapshot and this one (PM corrected history after the fact).
        Each row: level, check == "cross_month_correction", detail ("<name> <Mon> FTE <old> -> <new>"), source, code.
        Returns {"meta", "count", "corrections"}. Empty for the first ingested month."""
        def go(p):
            _, snap = resolve_month(state, month)
            rows = [i for i in snap["issues"] if i["check"] == CORRECTION_CHECK]
            return with_meta(snap, count=len(rows), corrections=rows)
        return guarded(state, ctx, "get_corrections", {"month": month}, go)
