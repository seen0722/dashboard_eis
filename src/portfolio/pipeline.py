"""CLI 與 MCP server 共用的一次建置：讀輸入包 → 快照 dict + HTML + PII 命中。不寫任何檔案。"""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from .config import Config
from .entities import Issue
from .extract.briefing import read_briefing
from .extract.control_list import find_control_lists, read_control_list
from .extract.project_list import read_project_list
from .extract.resource_summary import read_resource_summary, latest_month
from .model.diff import cross_month_corrections
from .model.load import build_dept_loads, capacity_by_month
from .model.normalize import build_projects
from .model.rules import build_exceptions, build_health, days_between, second_identity_issues
from .model.snapshot import build_snapshot, read_previous
from .render.page import render_page
from .render.pii import find_pii

INPUT_GLOBS = {"master": "Project List-*.xlsx", "briefing": "BU10_Project_Briefing_*.xlsx", "summary": "*Resource Summary.xlsx"}


class MissingInput(Exception):
    def __init__(self, missing: list[str]):
        super().__init__("missing " + ", ".join(missing))
        self.missing = missing


class InputUnreadable(Exception):
    pass


class NoManpowerMonth(Exception):
    pass


@dataclass
class BuildResult:
    snap: dict
    html: str
    issues: list[Issue]
    pii_hits: list[str]
    summary: dict


def find_one(d: Path, pattern: str) -> Path | None:
    hits = sorted(p for p in d.glob(pattern) if not p.name.startswith("~$"))
    return hits[-1] if hits else None


def build_month(input_dir: str | Path, report_month: str, today: str, snapshots_dir: str | Path, cfg: Config,
                lang: str = "en", pii_check: Callable[[str], list[str]] = find_pii) -> BuildResult:
    d = Path(input_dir); th = cfg.thresholds
    found = {k: find_one(d, g) for k, g in INPUT_GLOBS.items()}
    missing = [k for k, v in found.items() if v is None]
    if missing:
        raise MissingInput(missing)
    try:
        master, issues = read_project_list(found["master"])
        briefing, i2 = read_briefing(found["briefing"]); issues += i2
    except ValueError as ex:
        raise InputUnreadable(str(ex)) from ex
    summary, i3 = read_resource_summary(found["summary"]); issues += i3
    cls = []
    for f in find_control_lists(d):
        cl, i4 = read_control_list(f); cls.append(cl); issues += i4
    projects, i5, snap_date = build_projects(master, briefing, summary, cls, cfg); issues += i5
    lm = latest_month(summary)
    if lm < 1:
        raise NoManpowerMonth(f"no month with non-zero Total EIS 人力 in {found['summary'].name}; cannot build the report")
    loads, i6 = build_dept_loads(cls); issues += i6
    issues += second_identity_issues(projects, lm, cfg)
    snap_iso = f"{snap_date[:4]}-{snap_date[4:6]}-{snap_date[6:]}"
    for r in briefing:
        if r.snap == snap_date and r.updated and days_between(snap_iso, r.updated) > th["briefing_stale_days"]:
            issues.append(Issue("track", "briefing_stale", f"{r.name} last updated {r.updated}", "Briefing", r.code))
    prev = read_previous(snapshots_dir, report_month)
    issues += cross_month_corrections(prev, projects, lm)
    exceptions = build_exceptions(projects, loads, lm, cfg, today)
    health = build_health(projects, loads, issues, cfg, today, snap_date)
    snap = build_snapshot(report_month, lm, snap_date, today, projects, loads, capacity_by_month(loads), exceptions, health, issues)
    snap["meta"]["snap_rev"] = len({r.snap for r in briefing})
    html = render_page(snap, lang, today, th)
    pii = pii_check(html) + pii_check(json.dumps(snap, ensure_ascii=False))
    return BuildResult(snap, html, issues, pii,
                       {"projects": len(projects), "control_lists": len(cls), "latest_month": lm, "snap_date": snap_date})
