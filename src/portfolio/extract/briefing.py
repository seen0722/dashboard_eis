"""PM 雙週 Briefing。一個檔內有多個 YYYYMMDD 分頁，全部讀，讓 model 層做歷程。"""
from __future__ import annotations
import datetime as dt
import re
from pathlib import Path
from ..entities import BriefingRow, Issue
from .workbook import open_workbook

SNAP_RE = re.compile(r"^\d{8}$")
COLS = {"stage": "Stage", "product": "Product", "customer": "Customer", "name": "Project Name",
        "evt": "EVT Date", "dvt": "DVT Date", "pvt": "PVT Date", "mp_orig": "Original MP Date",
        "mp": "MP Date", "status": "Project status", "kickoff": "Kick-Off Date",
        "updated": "資料更新日", "code": "Project Code",
        # 2026-09 起的新版面：Product 拆成 Category + Panel Size，表頭第一格從 Stage 變 Type
        "category": "Category", "panel": "Panel Size", "biz_type": "Type"}
NA_PANEL = {"", "NA", "N/A", "TBD"}


def parse_date(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    s = str(v).strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _header_index(rows: list[tuple]) -> tuple[int, dict[str, int]] | None:
    """表頭列 = 同時含 Stage 與 Project Name 的那一列（不靠固定欄位位置：舊版第二格是 Stage，新版是 Type）。
    同名欄取第一個（新版 Project Code 在 H 欄與 Y 欄各一份，H 欄是 PM 維護的那份）。"""
    for i, r in enumerate(rows):
        if not r:
            continue
        hdr = [str(c).strip() if c is not None else "" for c in r]
        if "Stage" in hdr and "Project Name" in hdr:
            ci = {k: hdr.index(v) for k, v in COLS.items() if v in hdr}
            return i, ci
    return None


def _product(get, r) -> str:
    """舊版直接有 Product；新版用 Category + Panel Size 組回同樣形狀（`Tablet 10"`），Panel 為 NA 時只留 Category。"""
    if get(r, "product"):
        return str(get(r, "product")).strip()
    cat = str(get(r, "category") or "").strip()
    panel = str(get(r, "panel") or "").strip()
    return f"{cat} {panel}".strip() if panel.upper() not in NA_PANEL else cat


def read_briefing(path: str | Path) -> tuple[list[BriefingRow], list[Issue]]:
    with open_workbook(path) as wb:
        snaps = [s for s in wb.sheetnames if SNAP_RE.match(s)]
        if not snaps:
            raise ValueError(f"briefing has no YYYYMMDD sheet: {path}")
        # Read all snapshot sheets' rows into a dict inside the context manager
        snap_rows = {}
        for s in snaps:
            snap_rows[s] = list(wb.rows(s))

    # Parse after workbook is closed
    out, issues = [], []
    for s in snaps:
        rows = snap_rows[s]
        found = _header_index(rows)
        if not found:
            issues.append(Issue("track", "briefing_sheet_unreadable", f"sheet {s}: header row with 'Stage' and 'Project Name' not found", "Briefing"))
            continue
        hi, ci = found
        get = lambda r, k: r[ci[k]] if k in ci and ci[k] < len(r) else None
        for r in rows[hi + 1:]:
            if not r or not get(r, "name"):
                continue
            out.append(BriefingRow(
                snap=s, name=str(get(r, "name")).strip(),
                code=(str(get(r, "code")).strip() or None) if get(r, "code") else None,
                stage=str(get(r, "stage") or "").strip(), customer=str(get(r, "customer") or "").strip(),
                product=_product(get, r),
                dates={"kickoff": parse_date(get(r, "kickoff")), "evt": parse_date(get(r, "evt")),
                       "dvt": parse_date(get(r, "dvt")), "pvt": parse_date(get(r, "pvt")),
                       "mp": parse_date(get(r, "mp")), "mp_orig": parse_date(get(r, "mp_orig"))},
                updated=parse_date(get(r, "updated")), status_text=str(get(r, "status") or "").strip(),
                biz_type=str(get(r, "biz_type") or "").strip(), category=str(get(r, "category") or "").strip(),
                panel_size=str(get(r, "panel") or "").strip()))
    return out, issues


def latest_snap(rows: list[BriefingRow]) -> str:
    return max(r.snap for r in rows)
