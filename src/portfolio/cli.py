"""python -m src.portfolio.cli --input input-09 --report-month 202610"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from .config import load_config
from .entities import Issue
from .extract.briefing import read_briefing, latest_snap
from .extract.control_list import find_control_lists, read_control_list
from .extract.project_list import read_project_list
from .extract.resource_summary import read_resource_summary, latest_month as _latest_month
from .model.diff import cross_month_corrections
from .model.load import build_dept_loads, capacity_by_month
from .model.normalize import build_projects
from .model.rules import build_exceptions, build_health, days_between
from .model.snapshot import build_snapshot, write_snapshot, read_previous
from .render.page import render_page
from .render.pii import find_pii


def _find_one(d: Path, pattern: str) -> Path | None:
    hits = sorted(p for p in d.glob(pattern) if not p.name.startswith("~$"))
    return hits[-1] if hits else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True); ap.add_argument("--report-month", required=True)
    ap.add_argument("--today", default=dt.date.today().isoformat()); ap.add_argument("--lang", default="en")
    ap.add_argument("--snapshots", default="data/snapshots"); ap.add_argument("--out", default="out")
    a = ap.parse_args(argv)
    d = Path(a.input); cfg = load_config(); th = cfg.thresholds
    master_f = _find_one(d, "Project List-*.xlsx"); brief_f = _find_one(d, "BU10_Project_Briefing_*.xlsx"); summ_f = _find_one(d, "*Resource Summary.xlsx")
    if not (master_f and brief_f and summ_f):
        print(f"missing master/briefing/summary in {d}", file=sys.stderr); return 1
    try:
        master, issues = read_project_list(master_f)
        briefing, i2 = read_briefing(brief_f); issues += i2
    except ValueError as ex:
        print(str(ex), file=sys.stderr); return 1
    summary, i3 = read_resource_summary(summ_f); issues += i3
    cls = []
    for f in find_control_lists(d):
        cl, i4 = read_control_list(f); cls.append(cl); issues += i4
    projects, i5, snap_date = build_projects(master, briefing, summary, cls, cfg); issues += i5
    lm = _latest_month(summary)
    if lm < 1:
        print(f"no month with non-zero Total EIS 人力 in {summ_f.name}; cannot build the report", file=sys.stderr); return 1
    loads, i6 = build_dept_loads(cls); issues += i6
    snap_iso = f"{snap_date[:4]}-{snap_date[4:6]}-{snap_date[6:]}"
    for r in briefing:
        if r.snap == snap_date and r.updated and days_between(snap_iso, r.updated) > th["briefing_stale_days"]:
            issues.append(Issue("track", "briefing_stale", f"{r.name} last updated {r.updated}", "Briefing", r.code))
    prev = read_previous(a.snapshots, a.report_month)
    issues += cross_month_corrections(prev, projects, lm)
    exceptions = build_exceptions(projects, loads, lm, cfg, a.today)
    health = build_health(projects, loads, issues, cfg, a.today, snap_date)
    snap = build_snapshot(a.report_month, lm, snap_date, a.today, projects, loads, capacity_by_month(loads), exceptions, health, issues)
    snap["meta"]["snap_rev"] = len({r.snap for r in briefing})
    html = render_page(snap, a.lang, a.today, th)
    # 負向檢查在任何寫檔之前，HTML 與 snapshot JSON 都要過；命中就兩個檔案都不寫。
    pii = find_pii(html) + find_pii(json.dumps(snap, ensure_ascii=False))
    if pii:
        print(f"PII found, refusing to write HTML or snapshot: {pii[:5]}", file=sys.stderr); return 2
    write_snapshot(snap, a.snapshots)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    f = out / f"portfolio_{a.report_month}_{a.lang}.html"; f.write_text(html, encoding="utf-8")
    print(f"wrote {f} ({len(html)} bytes); {len(projects)} projects; {len(cls)} control lists; latest month {lm}; snapshot {snap_date}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
