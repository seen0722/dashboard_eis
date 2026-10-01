"""把四種來源合併成以 PROJECTCODE 為鍵的 Project。任何對不上的名稱都產生 issue。"""
from __future__ import annotations
from dataclasses import replace
from ..config import Config, normalize_name
from ..entities import Project, Issue, MasterProject, BriefingRow, MonthlyFTE, ControlList, PlanVsActual, ROLES
from .keys import MasterIndex, resolve_code
from .mask import mask_names
from .stages import stage_cat


def _get(projects: dict[str, Project], code: str, name: str, idx: MasterIndex) -> Project:
    if code not in projects:
        m = idx.by_code.get(code)
        projects[code] = Project(code=code, name=m.name if m else name, group=m.group if m else "", family=m.family if m else "")
    return projects[code]


def _add12(a: list[float], b: list[float]) -> list[float]:
    """月對月相加。長度一律補成 12，不動傳入的 list。"""
    at = lambda xs, i: float(xs[i]) if i < len(xs) else 0.0
    return [round(at(a, i) + at(b, i), 4) for i in range(12)]


def _merge_pva(cur: dict[str, PlanVsActual], new: dict[str, PlanVsActual]) -> dict[str, PlanVsActual]:
    """兩份 Control List 落到同一 code 時，plan / actual / ntd 月對月相加。產生新物件，兩邊來源都不被改。"""
    out = dict(cur)
    for role, v in new.items():
        old = out.get(role)
        out[role] = v if old is None else PlanVsActual(role=role, plan=_add12(old.plan, v.plan),
                                                       actual=_add12(old.actual, v.actual), ntd=_add12(old.ntd, v.ntd))
    return out


def _primary_code(cl: ControlList, idx: MasterIndex, aliases: dict) -> tuple[str, bool]:
    if len(cl.codes) == 1:
        return cl.codes[0], True
    by_label, ok = resolve_code(cl.label, None, idx, aliases)
    if ok and by_label in cl.codes:
        return by_label, True
    if cl.codes:
        return cl.codes[0], True
    return resolve_code(cl.label, None, idx, aliases)


def build_projects(master: list[MasterProject], briefing: list[BriefingRow], summary: list[MonthlyFTE],
                   control_lists: list[ControlList], cfg: Config) -> tuple[list[Project], list[Issue], str]:
    idx = MasterIndex(master)
    projects: dict[str, Project] = {}
    issues: list[Issue] = []
    protect = {normalize_name(m.name) for m in master} | {normalize_name(c.label) for c in control_lists}

    def unresolved(src: str, name: str):
        issues.append(Issue("track", "name_unresolved", f"{name} ({src}) has no PROJECTCODE and no master match", src))

    latest = max((r.snap for r in briefing), default="")
    for r in sorted(briefing, key=lambda r: r.snap):
        code, ok = resolve_code(r.name, r.code, idx, cfg.aliases)
        if not ok and r.snap == latest:
            unresolved("Briefing", r.name)
        p = _get(projects, code, r.name, idx)
        p.history.append({"snap": r.snap, "stage": r.stage, "mp": r.dates.get("mp"), "dvt": r.dates.get("dvt")})
        if r.snap == latest:
            p.in_briefing = True
            p.stage, p.stage_cat = r.stage, stage_cat(r.stage, cfg)
            p.customer, p.product, p.dates = r.customer, r.product, dict(r.dates)
            p.biz_type, p.category, p.panel_size = r.biz_type, r.category, r.panel_size
            if p.code.startswith("NAME:"):
                p.name = r.name
    summary_seen: set[str] = set()
    for s in summary:
        code, ok = resolve_code(s.name, None, idx, cfg.aliases)
        if not ok:
            unresolved("Resource Summary", s.name)
        p = _get(projects, code, s.name, idx)
        if code in summary_seen:
            issues.append(Issue("track", "duplicate_source", f"{s.name}: second Resource Summary block for {code}", "Resource Summary", code))
            p.fte, p.ntd = _add12(p.fte, s.fte), _add12(p.ntd, s.ntd)
        else:
            summary_seen.add(code)
            p.fte, p.ntd = list(s.fte), list(s.ntd)
        if not p.group:
            p.group = s.group
    masked_total = 0
    for cl in control_lists:
        code, ok = _primary_code(cl, idx, cfg.aliases)
        if len(cl.codes) > 1:
            issues.append(Issue("track", "cl_multiple_codes", f"{cl.label}: task rows carry codes {cl.codes}; using {code}", "Control List"))
        if not ok:
            unresolved("Control List", cl.label)
        p = _get(projects, code, cl.label, idx)
        dup = p.in_control_list
        if dup:
            issues.append(Issue("track", "duplicate_source", f"{cl.label}: second control list for {code}", "Control List", code))
        p.in_control_list = True
        pva = {role: cl.pva[role] for role in ROLES if role in cl.pva}
        p.pva = _merge_pva(p.pva, pva) if dup else pva
        p.has_plan = any(sum(v.plan) > 0 for v in p.pva.values())
        masked = []
        for t in cl.tasks:
            desc, n = mask_names(t.description, protect); masked_total += n
            masked.append(replace(t, description=desc))
        p.tasks = p.tasks + masked if dup else masked
    issues.append(Issue("ok", "names_masked", str(masked_total), "Control List"))
    return sorted(projects.values(), key=lambda p: p.name), issues, latest
