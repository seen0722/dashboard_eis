"""PROJECTCODE 主檔。這是唯一允許 raise 的抽取器：沒有主檔就沒有報告。"""
from __future__ import annotations
from pathlib import Path
from ..entities import MasterProject, Issue
from .workbook import open_workbook

REQUIRED = ("PROJECTCODE", "PROJECTNAME", "PROJECTGROUP", "產品別", "當月生失效")


def read_project_list(path: str | Path) -> tuple[list[MasterProject], list[Issue]]:
    with open_workbook(path) as wb:
        rows = list(wb.rows(wb.sheetnames[0]))

    if not rows:
        raise ValueError(f"project list is empty: {path}")
    hdr = [str(c).strip() if c is not None else "" for c in rows[0]]
    missing = [c for c in REQUIRED if c not in hdr]
    if missing:
        raise ValueError(f"project list missing columns {missing}: {path}")
    ci = {h: i for i, h in enumerate(hdr)}
    out, issues = [], []
    for r in rows[1:]:
        if not r or all(c is None for c in r):
            continue
        code = r[ci["PROJECTCODE"]]
        name = str(r[ci["PROJECTNAME"]] or "").strip()
        if not code:
            issues.append(Issue("track", "master_row_without_code", f"{name} has no PROJECTCODE", "Project List"))
            continue
        out.append(MasterProject(code=str(code).strip(), name=name,
                                 group=str(r[ci["PROJECTGROUP"]] or "").strip(),
                                 family=str(r[ci["產品別"]] or "").strip(),
                                 active=str(r[ci["當月生失效"]] or "").strip().upper() == "Y"))
    return out, issues
