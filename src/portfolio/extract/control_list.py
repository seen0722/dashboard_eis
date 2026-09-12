"""每案的 EIS Resource Control List。只讀四類分頁：Plan vs Actual、BU/FU-Task、月分頁。
絕不讀「人力」「實名制」（含姓名工號）。"""
from __future__ import annotations
import re
from pathlib import Path
from ..entities import ControlList, PlanVsActual, Task, DeptLoadRow, Issue, ROLES, empty_months
from .workbook import open_workbook

FILE_RE = re.compile(r"Control List-(.+?)\s*\(")
ROLE_RE = re.compile(r"\((FU RD|BU RD|PM)\)")
SRC = "Control List"


def label_from_filename(path: Path) -> str:
    m = FILE_RE.search(path.name)
    return m.group(1).strip() if m else path.stem


def find_control_lists(input_dir: str | Path) -> list[Path]:
    d = Path(input_dir)
    return sorted(p for p in d.iterdir() if "Control List-" in p.name and not p.name.startswith("~$") and p.suffix.lower() in (".xlsx", ".xlsb"))


def _num(v) -> float:
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return 0.0


def _twelve(r) -> list[float]:
    vals = [_num(x) for x in list(r)[1:13]]
    return (vals + empty_months())[:12]


def _pva_sheet(wb) -> str | None:
    for s in wb.sheetnames:
        if s.strip().lower().replace(" ", "") in ("planvs.acutal", "planvs.actual", "planvsactual"):
            return s
    return None


def _read_pva(rows) -> dict[str, PlanVsActual]:
    out, cur = {}, None
    for r in rows:
        if not r or r[0] is None:
            continue
        head = str(r[0]).strip()
        if len(r) > 1 and r[1] == "Jan":
            m = ROLE_RE.search(head)
            cur = m.group(1) if m else None          # 無括號 = 專案總計區塊，停止
            if cur:
                out[cur] = PlanVsActual(role=cur)
            continue
        if not cur:
            continue
        if "Budget" in head:
            out[cur].plan = _twelve(r)
        elif "EIS 人力" in head:
            out[cur].actual = _twelve(r)
        elif "分攤金額" in head:
            out[cur].ntd = _twelve(r)
    return out


def _read_tasks(rows, side: str) -> tuple[list[Task], set[str]]:
    hdr, tasks, codes = None, [], set()
    for r in rows:
        if hdr is None:
            if r and "Project Code" in [str(c) for c in r]:
                hdr = True
            continue
        if not r or r[0] is None:
            break
        r = tuple(r) + (None,) * (11 - len(r)) if len(r) < 11 else r
        try:
            month = int(r[7])
        except (TypeError, ValueError):
            continue
        if not 1 <= month <= 12:
            continue
        if r[1]:
            codes.add(str(r[1]).strip())
        dept = str(r[4] or "")
        tasks.append(Task(month=month, side=side, function=str(r[5] or "?").strip(),
                          dept=dept.split("-")[-1] if "-" in dept else dept, fte=_num(r[8]),
                          description=str(r[10] or "").strip() if len(r) > 10 else ""))
    return tasks, codes


def _read_month(rows, month: int) -> list[DeptLoadRow]:
    rows = list(rows)
    if not rows or not rows[0] or rows[0][0] != "年月":
        return []
    hdr = [str(c).strip() if c is not None else "" for c in rows[0]]
    need = ("部門代碼", "部門名稱", "BU/FU", "Function", "PROJECTCODE", "主管填入人力", "單位TotalKeyIn人數")
    if any(n not in hdr for n in need):
        return []
    ci = {n: hdr.index(n) for n in need}
    out = []
    for r in rows[1:]:
        if not r or r[0] is None:
            continue
        r = tuple(r) + (None,) * (len(hdr) - len(r))     # xlsb 不補齊短列；補到 header 長度才能安全取欄
        if r[ci["BU/FU"]] != "BU":
            continue
        try:
            keyed = int(r[ci["單位TotalKeyIn人數"]] or 0)
        except (TypeError, ValueError):
            continue
        out.append(DeptLoadRow(dept_code=str(r[ci["部門代碼"]]), dept_name=str(r[ci["部門名稱"]] or ""),
                               function=str(r[ci["Function"]] or "?"), month=month,
                               allocated=_num(r[ci["主管填入人力"]]), keyed_in=keyed,
                               code=str(r[ci["PROJECTCODE"]]).strip() if r[ci["PROJECTCODE"]] else None))
    return out


def read_control_list(path: str | Path) -> tuple[ControlList, list[Issue]]:
    """讀檔與解析都在保護傘下：任何例外都變成 cl_unreadable，永遠回傳 (cl, issues)。"""
    path = Path(path)
    label = label_from_filename(path)
    cl = ControlList(label=label, path=str(path))
    issues: list[Issue] = []
    try:
        _fill(cl, path, label, issues)
    except Exception as exc:  # noqa: BLE001 - 檔案層級的失敗要進健康度而不是中斷
        issues.append(Issue("track", "cl_unreadable", f"{label}: {exc.__class__.__name__}: {exc}", SRC))
    return cl, issues


def _fill(cl: ControlList, path: Path, label: str, issues: list[Issue]) -> None:
    sheetnames, pva_rows, bu_task_rows, fu_task_rows, month_rows = [], [], [], [], {}
    with open_workbook(path) as wb:
        sheetnames = wb.sheetnames
        pva = _pva_sheet(wb)
        if pva:
            pva_rows = list(wb.rows(pva))
        for sheet in ("BU-Task", "FU-Task"):
            if sheet in sheetnames:
                rows = list(wb.rows(sheet))
                if sheet == "BU-Task":
                    bu_task_rows = rows
                else:
                    fu_task_rows = rows
        for m in range(1, 13):
            s = str(m)
            if s in sheetnames:
                month_rows[m] = list(wb.rows(s))
    if pva_rows:
        cl.pva = _read_pva(pva_rows)
        for role in ROLES:
            if role not in cl.pva:
                issues.append(Issue("track", "cl_pva_role_missing", f"{label}: Plan vs Actual has no {role} block", SRC))
    else:
        issues.append(Issue("track", "cl_no_plan_vs_actual", f"{label}: no 'Plan vs. Actual' sheet", SRC))
    codes: set[str] = set()
    any_task_sheet = False
    for rows, side in [(bu_task_rows, "BU"), (fu_task_rows, "FU")]:
        if rows:
            any_task_sheet = True
            tasks, c = _read_tasks(rows, side)
            cl.tasks.extend(tasks); codes |= c
    if not any_task_sheet:
        issues.append(Issue("track", "cl_no_task_sheet", f"{label}: no BU-Task / FU-Task sheet", SRC))
    if not month_rows:
        issues.append(Issue("track", "cl_no_month_sheets", f"{label}: no monthly sheets 1..12", SRC))
    for month, rows in month_rows.items():
        load = _read_month(rows, month)
        cl.load_rows.extend(load)
        codes |= {r.code for r in load if r.code}
    cl.codes = sorted(codes)
