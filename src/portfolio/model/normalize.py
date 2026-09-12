"""把四種來源合併成以 PROJECTCODE 為鍵的 Project。任何對不上的名稱都產生 issue。"""
from __future__ import annotations
from ..config import Config, normalize_name
from ..entities import Project, Issue, MasterProject, BriefingRow, MonthlyFTE, ControlList, ROLES
from .keys import MasterIndex, resolve_code
from .mask import mask_names
from .stages import stage_cat


def _get(projects: dict[str, Project], code: str, name: str, idx: MasterIndex) -> Project:
    if code not in projects:
        m = idx.by_code.get(code)
        projects[code] = Project(code=code, name=m.name if m else name, group=m.group if m else "", family=m.family if m else "")
    return projects[code]


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
            if p.code.startswith("NAME:"):
                p.name = r.name
    for s in summary:
        code, ok = resolve_code(s.name, None, idx, cfg.aliases)
        if not ok:
            unresolved("Resource Summary", s.name)
        p = _get(projects, code, s.name, idx)
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
        p.in_control_list = True
        p.pva = {role: cl.pva[role] for role in ROLES if role in cl.pva}
        p.has_plan = any(sum(v.plan) > 0 for v in p.pva.values())
        for t in cl.tasks:
            t.description, n = mask_names(t.description, protect); masked_total += n
        p.tasks = list(cl.tasks)
    issues.append(Issue("ok", "names_masked", str(masked_total), "Control List"))
    return sorted(projects.values(), key=lambda p: p.name), issues, latest
