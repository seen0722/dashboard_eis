"""每月一份正規化 JSON。跨月比較與 render 都只吃這個檔。"""
from __future__ import annotations
import json
import os
from dataclasses import asdict
from pathlib import Path

VERSION = "1"


def build_snapshot(report_month: str, latest_month: int, snap_date: str, generated: str, projects, loads, capacity,
                   exceptions, health, issues) -> dict:
    return {
        "meta": {"version": VERSION, "report_month": report_month, "latest_month": latest_month,
                 "snap_date": snap_date, "generated": generated},
        "projects": [asdict(p) for p in projects],
        "loads": [asdict(d) for d in loads],
        "capacity": list(capacity),
        "exceptions": [asdict(e) for e in exceptions],
        "health": [asdict(h) for h in health],
        "issues": [asdict(i) for i in issues],
    }


def write_snapshot(d: dict, snapshots_dir: str | Path) -> Path:
    out = Path(snapshots_dir) / d["meta"]["report_month"] / "portfolio.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, out)
    return out


def read_previous(snapshots_dir: str | Path, report_month: str) -> dict | None:
    root = Path(snapshots_dir)
    if not root.exists():
        return None
    earlier = sorted(p.name for p in root.iterdir() if p.is_dir() and p.name.isdigit() and p.name < report_month)
    if not earlier:
        return None
    f = root / earlier[-1] / "portfolio.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
