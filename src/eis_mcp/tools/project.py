"""單案查詢。解析順序：代碼精確 → alias → 正規化全名 → 正規化子字串。"""
from __future__ import annotations
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from ...portfolio.config import Config, normalize_name
from ..state import ServerState
from ._common import guarded, resolve_month, with_meta


def resolve_project(snap: dict, query: str, cfg: Config) -> dict | list[dict]:
    projects = snap["projects"]; q = query.strip()
    exact = [p for p in projects if p["code"].upper() == q.upper()]
    if exact:
        return exact[0]
    nq = normalize_name(q); nq = cfg.aliases.get(nq, nq)
    same = [p for p in projects if normalize_name(p["name"]) == nq]
    if len(same) == 1:
        return same[0]
    if same:
        return same
    partial = [p for p in projects if nq and nq in normalize_name(p["name"])]
    return partial[0] if len(partial) == 1 else partial


def register(mcp: MCPServer, state: ServerState) -> None:
    @mcp.tool()
    def get_project(query: str, ctx: Context, month: str | None = None) -> dict:
        """Look up one project by PROJECTCODE (BR0000xxxxxx), project name or known alias.

        Returns {"meta", "project"} with the full snapshot record: code, name, group, family, customer, product, stage,
        stage_cat, biz_type (JDM|ODM|EMS), category, panel_size, dates {kickoff, evt, dvt, pvt, mp, mp_orig}, in_briefing, in_control_list, has_plan, fte[12], ntd[12],
        pva {role: {plan[12], actual[12], ntd[12]}}, tasks, history. Month indexes are Jan..Dec (index 0 = Jan).
        If several projects match, returns {"candidates": [...]} instead; call again with the exact code.
        month "YYYYMM" is optional and defaults to the latest ingested month.
        """
        def go(p):
            m, snap = resolve_month(state, month)
            hit = resolve_project(snap, query, state.cfg)
            if isinstance(hit, dict):
                return with_meta(snap, project=hit)
            if not hit:
                raise ToolError(f"not_found: no project in {m} matches '{query}'. Try search_projects(text=...) or list_months.")
            return with_meta(snap, candidates=[{"code": c["code"], "name": c["name"], "stage": c["stage"]} for c in hit],
                             hint="several projects match; call get_project again with the exact code")
        return guarded(state, ctx, "get_project", {"query": query, "month": month}, go)

    @mcp.tool()
    def search_projects(ctx: Context, stage_cat: str | None = None, group: str | None = None, customer: str | None = None,
                        biz_type: str | None = None, category: str | None = None, text: str | None = None,
                        month: str | None = None) -> dict:
        """List projects, optionally filtered. stage_cat is one of RFQ / RFI, POC, Execution, MP, Sustain / EOP, Suspended, Other
        (case-insensitive). group, customer, biz_type (JDM | ODM | EMS) and category (Tablet, NB, AI PC, Box PC, ...) match whole
        values case-insensitively; text matches a substring of name, customer or product. biz_type / category / panel_size come
        from the PM Briefing's Type / Category / Panel Size columns (added 2026-09) and are empty strings for older briefings.
        Returns {"meta", "count", "projects": [{code, name, stage, stage_cat, customer, group, biz_type, category, panel_size,
        latest_fte}]} where latest_fte is the FTE of meta.latest_month. Use get_project for the full record.
        """
        def go(p):
            _, snap = resolve_month(state, month)
            lm = snap["meta"]["latest_month"]
            nt = normalize_name(text) if text else ""
            ng, nc = (normalize_name(group) if group else ""), (normalize_name(customer) if customer else "")
            nb, nk = (normalize_name(biz_type) if biz_type else ""), (normalize_name(category) if category else "")
            rows = [q for q in snap["projects"]
                    if (not stage_cat or q["stage_cat"].lower() == stage_cat.lower())
                    and (not ng or normalize_name(q["group"]) == ng)
                    and (not nc or normalize_name(q["customer"]) == nc)
                    and (not nb or normalize_name(q.get("biz_type", "")) == nb)
                    and (not nk or normalize_name(q.get("category", "")) == nk)
                    and (not nt or any(nt in normalize_name(q[k]) for k in ("name", "customer", "product")))]
            return with_meta(snap, count=len(rows), projects=[
                {"code": q["code"], "name": q["name"], "stage": q["stage"], "stage_cat": q["stage_cat"], "customer": q["customer"],
                 "group": q["group"], "biz_type": q.get("biz_type", ""), "category": q.get("category", ""),
                 "panel_size": q.get("panel_size", ""), "latest_fte": q["fte"][lm - 1]} for q in rows])
        return guarded(state, ctx, "search_projects", {"stage_cat": stage_cat, "group": group, "customer": customer, "biz_type": biz_type,
                                                       "category": category, "text": text, "month": month}, go)
