# BU10 Portfolio Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 從每月一包 input 目錄（Project List、Briefing、Resource Summary、N 份 Control List）產生一份給 BU10 主管看的英文單頁 HTML，第一屏是由規則算出的「本月要決定的事」。

**Architecture:** 新套件 `src/portfolio/`，三層：`extract/`（每種 xlsx 一模組，回傳 records + issues，不中斷）→ `model/`（以 PROJECTCODE 合併、stage 分類、部門負載、例外與健康度規則、跨月比對、寫 snapshot JSON）→ `render/`（字串表、CSS token、SVG 圖、組頁）。`cli.py` 串起來。舊管線 `src/build_review.py` 完全不動。

**Tech Stack:** Python 3.12+、openpyxl、pyxlsb、PyYAML、pytest。輸出 HTML 零外部依賴。視覺驗證用 headless Chrome。

**Spec:** `docs/superpowers/specs/2026-09-12-bu10-portfolio-dashboard-design.md`

## Global Constraints

- 主鍵是 PROJECTCODE（`BR0000xxxxxx`）；名稱與 alias 只當備援，對不上要進健康度，不可靜默丟棄（spec §3.1）。
- 不讀 Control List 的 `人力` 與 `實名制` 分頁；輸出 HTML 不得含 `LA\d{7}` 工號或任何姓名（spec §4.3、§8）。
- 抽取模組回傳 `(records, issues)`；格式問題進 issues，只有主檔讀不到才 raise（spec §7）。
- 「最新月」= Resource Summary 最後一個 Total EIS 人力非零的月份（spec §3.2a）。
- 英文為預設輸出；所有 UI 字串走 `render/strings.py`，程式碼內不得寫死英文句子（spec §1）。
- 視覺 token 固定：paper `#F5F6F4`、ink `#22262A`、ink-2 `#5B6167`、ink-3 `#9AA3AB`、rule `#D5D9D6`、slate `#3D5A80`、slate-2 `#A9B8CC`、teal `#5C8D89`、signal `#E8590C`；signal 只用於例外序號、決定級數字、過期里程碑、Suspended（spec §6）。
- 不做側欄、卡片、圓餅、動畫、全大寫小標、中點串接（spec §5）。
- 門檻：MP 延後 60 天、疑似輸入錯誤 300 天、可調度部門 85%、停案掛帳 0.05 FTE、Briefing 更新日過舊 60 天，全部放 `config/thresholds.yaml` 的 `portfolio:` 區塊（spec §4.1、§11）。
- 每個任務結束都 commit；不 push。Commit 訊息結尾加 `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`。
- 執行環境：`/tmp/dashboard_eis_venv/bin/python`（若不存在，用 `python3 -m venv /tmp/dashboard_eis_venv && /tmp/dashboard_eis_venv/bin/pip install -r requirements.txt` 重建）。以下所有 `python` / `pytest` 都指這個 venv。

---

## 檔案結構

```
requirements.txt                          # 新
config/stages.yaml                        # 新：stage_cat 規則
config/portfolio_aliases.yaml             # 新：名稱備援對照（與舊 aliases.yaml 無關）
config/thresholds.yaml                    # 修改：加 portfolio: 區塊
src/portfolio/__init__.py
src/portfolio/entities.py                 # 所有 dataclass，跨層共用的型別
src/portfolio/config.py                   # 讀三個 yaml
src/portfolio/extract/__init__.py
src/portfolio/extract/workbook.py         # open_workbook：xlsx / xlsb 統一介面
src/portfolio/extract/project_list.py
src/portfolio/extract/briefing.py
src/portfolio/extract/resource_summary.py
src/portfolio/extract/control_list.py
src/portfolio/model/__init__.py
src/portfolio/model/keys.py               # 名稱正規化、code 解析
src/portfolio/model/stages.py             # stage_cat
src/portfolio/model/mask.py               # 人名遮罩
src/portfolio/model/normalize.py          # 合併成 Project
src/portfolio/model/load.py               # 部門負載、capacity
src/portfolio/model/rules.py              # 例外 + 健康度
src/portfolio/model/diff.py               # 跨月修正
src/portfolio/model/snapshot.py           # 組 portfolio.json、讀寫
src/portfolio/render/__init__.py
src/portfolio/render/strings.py
src/portfolio/render/css.py
src/portfolio/render/charts.py
src/portfolio/render/page.py
src/portfolio/render/pii.py               # 輸出前負向檢查
src/portfolio/cli.py
tests/portfolio/conftest.py               # make_xlsx fixture 工具
tests/portfolio/test_*.py                 # 每模組一檔
```

---

### Task 0: 骨架、依賴、fixture 工具、共用型別

**Files:**
- Create: `requirements.txt`, `src/portfolio/__init__.py`, `src/portfolio/extract/__init__.py`, `src/portfolio/model/__init__.py`, `src/portfolio/render/__init__.py`, `src/portfolio/entities.py`, `tests/portfolio/__init__.py`, `tests/portfolio/conftest.py`, `tests/portfolio/test_entities.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `entities.py` 的全部 dataclass（下方原文），`conftest.make_xlsx(tmp_path, sheets) -> Path`。

- [ ] **Step 1: 依賴與 gitignore**

`requirements.txt`：
```
openpyxl>=3.1
pyxlsb>=1.0.10
PyYAML>=6.0
pytest>=8.0
```

`.gitignore` 末尾追加：
```
# 每月輸入包與正規化快照：含專案代號、人力、NTD，不進版控
input-*/
data/snapshots/
*.xlsb
```

執行：`/tmp/dashboard_eis_venv/bin/pip install -r requirements.txt`

- [ ] **Step 2: 寫共用型別測試**

`tests/portfolio/test_entities.py`：
```python
from dataclasses import asdict
from src.portfolio.entities import Issue, Project, PlanVsActual, empty_months


def test_empty_months_is_twelve_zeros():
    assert empty_months() == [0.0] * 12


def test_project_serialises_to_plain_dict():
    p = Project(code="BR0000015346", name="THORPE")
    d = asdict(p)
    assert d["code"] == "BR0000015346"
    assert d["dates"] == {"kickoff": None, "evt": None, "dvt": None, "pvt": None, "mp": None, "mp_orig": None}
    assert d["fte"] == [0.0] * 12


def test_issue_defaults():
    i = Issue(level="track", check="x", detail="d", source="Briefing")
    assert i.code is None
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `python -m pytest tests/portfolio/test_entities.py -v`
Expected: FAIL，`ModuleNotFoundError: src.portfolio`

- [ ] **Step 4: 寫 entities.py 與空 `__init__.py`**

`src/portfolio/entities.py`：
```python
"""跨層共用型別。所有欄位都可 asdict() 成純 JSON。"""
from dataclasses import dataclass, field

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DATE_KEYS = ("kickoff", "evt", "dvt", "pvt", "mp", "mp_orig")
ROLES = ("FU RD", "BU RD", "PM")


def empty_months() -> list[float]:
    return [0.0] * 12


def empty_dates() -> dict[str, str | None]:
    return {k: None for k in DATE_KEYS}


@dataclass
class Issue:
    level: str          # "decide" | "track" | "ok"
    check: str          # 機器可讀的檢查代號，例如 "budget_missing"
    detail: str         # 人讀得懂的描述
    source: str         # 資料來源
    code: str | None = None


@dataclass
class MasterProject:
    code: str
    name: str
    group: str = ""
    family: str = ""
    active: bool = True


@dataclass
class BriefingRow:
    snap: str                       # "YYYYMMDD"
    name: str
    code: str | None = None
    stage: str = ""
    customer: str = ""
    product: str = ""
    dates: dict[str, str | None] = field(default_factory=empty_dates)
    updated: str | None = None      # 資料更新日
    status_text: str = ""


@dataclass
class MonthlyFTE:
    name: str
    group: str
    fte: list[float] = field(default_factory=empty_months)
    ntd: list[float] = field(default_factory=empty_months)


@dataclass
class PlanVsActual:
    role: str
    plan: list[float] = field(default_factory=empty_months)
    actual: list[float] = field(default_factory=empty_months)
    ntd: list[float] = field(default_factory=empty_months)


@dataclass
class Task:
    month: int                      # 1..12
    side: str                       # "BU" | "FU"
    function: str
    dept: str                       # 部門名最後一段
    fte: float
    description: str                # 已遮罩


@dataclass
class DeptLoadRow:
    dept_code: str
    dept_name: str
    function: str
    month: int
    allocated: float                # 主管填入人力（單一專案）
    keyed_in: int                   # 單位TotalKeyIn人數
    code: str | None = None


@dataclass
class ControlList:
    label: str                      # 檔名裡的專案名
    path: str
    codes: list[str] = field(default_factory=list)
    pva: dict[str, PlanVsActual] = field(default_factory=dict)
    tasks: list[Task] = field(default_factory=list)
    load_rows: list[DeptLoadRow] = field(default_factory=list)


@dataclass
class Project:
    code: str                       # 真代碼，或解析失敗時 "NAME:<normalized>"
    name: str
    group: str = ""
    family: str = ""
    customer: str = ""
    product: str = ""
    stage: str = ""
    stage_cat: str = ""
    dates: dict[str, str | None] = field(default_factory=empty_dates)
    in_briefing: bool = False
    in_control_list: bool = False
    has_plan: bool = False
    fte: list[float] = field(default_factory=empty_months)
    ntd: list[float] = field(default_factory=empty_months)
    pva: dict[str, PlanVsActual] = field(default_factory=dict)
    tasks: list[Task] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)   # [{snap, stage, mp, dvt}]


@dataclass
class Exception_:
    rank: int
    title: str
    evidence: str
    ask: str
    source: str
    codes: list[str] = field(default_factory=list)


@dataclass
class HealthRow:
    level: str
    check: str
    label: str
    count: int
    names: list[str]
    source: str
```

四個 `__init__.py` 都是空檔。

- [ ] **Step 5: 寫 conftest 的 xlsx 產生工具**

`tests/portfolio/conftest.py`：
```python
from pathlib import Path
import openpyxl
import pytest


def make_xlsx(path: Path, sheets: dict[str, list[list]]) -> Path:
    """sheets: {sheet_name: rows}. rows 是 list of list，None 代表空格。"""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    wb.save(path)
    return path


@pytest.fixture
def xlsx(tmp_path):
    def _make(name: str, sheets: dict[str, list[list]]) -> Path:
        return make_xlsx(tmp_path / name, sheets)
    return _make
```

- [ ] **Step 6: 跑測試確認通過**

Run: `python -m pytest tests/portfolio/test_entities.py -v`
Expected: 3 PASS

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .gitignore src/portfolio tests/portfolio
git commit -m "feat(portfolio): scaffold package, shared entities, xlsx test fixture"
```

---

### Task 1: workbook.py 統一開檔（xlsx / xlsb）

**Files:**
- Create: `src/portfolio/extract/workbook.py`, `tests/portfolio/test_workbook.py`

**Interfaces:**
- Produces: `open_workbook(path: str | Path) -> Workbook`，其中 `Workbook` 有 `.sheetnames: list[str]` 與 `.rows(sheet: str) -> Iterator[tuple]`（每列是 tuple，值已是 Python 型別，空格為 None）。所有 extract 模組只用這個介面。

- [ ] **Step 1: 寫測試**

`tests/portfolio/test_workbook.py`：
```python
from pathlib import Path
import pytest
from src.portfolio.extract import workbook as wbmod


def test_xlsx_rows_and_sheetnames(xlsx):
    p = xlsx("a.xlsx", {"S1": [["h1", "h2"], [1, None]], "S2": [["x"]]})
    wb = wbmod.open_workbook(p)
    assert wb.sheetnames == ["S1", "S2"]
    assert list(wb.rows("S1")) == [("h1", "h2"), (1, None)]


def test_xlsb_dispatches_to_pyxlsb(monkeypatch, tmp_path):
    called = {}

    class FakeSheet:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def rows(self):
            class C:  # 模仿 pyxlsb Cell
                def __init__(self, v): self.v = v
            yield [C("h")]
            yield [C(3)]

    class FakeWb:
        sheets = ["Only"]
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get_sheet(self, name): called["name"] = name; return FakeSheet()

    monkeypatch.setattr(wbmod, "_open_xlsb", lambda path: FakeWb())
    p = tmp_path / "b.xlsb"; p.write_bytes(b"")
    wb = wbmod.open_workbook(p)
    assert wb.sheetnames == ["Only"]
    assert list(wb.rows("Only")) == [("h",), (3,)]
    assert called["name"] == "Only"


def test_unknown_extension_raises(tmp_path):
    p = tmp_path / "c.csv"; p.write_text("")
    with pytest.raises(ValueError):
        wbmod.open_workbook(p)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/portfolio/test_workbook.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 實作**

`src/portfolio/extract/workbook.py`：
```python
"""xlsx 與 xlsb 的統一唯讀介面。extract 模組只透過這裡讀檔。"""
from __future__ import annotations
from pathlib import Path
from typing import Iterator
import warnings
import openpyxl

warnings.filterwarnings("ignore", message="Data Validation extension")


class Workbook:
    def __init__(self, sheetnames: list[str], reader):
        self.sheetnames = sheetnames
        self._reader = reader          # callable(sheet) -> Iterator[tuple]

    def rows(self, sheet: str) -> Iterator[tuple]:
        return self._reader(sheet)


def _open_xlsx(path: Path) -> Workbook:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    return Workbook(list(wb.sheetnames), lambda s: wb[s].iter_rows(values_only=True))


def _open_xlsb(path: Path):
    from pyxlsb import open_workbook as _pyxlsb_open
    return _pyxlsb_open(str(path))


def _xlsb_workbook(path: Path) -> Workbook:
    wb = _open_xlsb(path)
    names = list(wb.sheets)

    def reader(sheet: str) -> Iterator[tuple]:
        with wb.get_sheet(sheet) as sh:
            for row in sh.rows():
                yield tuple(c.v for c in row)
    return Workbook(names, reader)


def open_workbook(path: str | Path) -> Workbook:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".xlsx":
        return _open_xlsx(path)
    if ext == ".xlsb":
        return _xlsb_workbook(path)
    raise ValueError(f"unsupported workbook type: {path.name}")
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/portfolio/test_workbook.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/extract/workbook.py tests/portfolio/test_workbook.py
git commit -m "feat(portfolio): unified xlsx/xlsb workbook reader"
```

---

### Task 2: extract/project_list.py

**Files:**
- Create: `src/portfolio/extract/project_list.py`, `tests/portfolio/test_project_list.py`

**Interfaces:**
- Consumes: `open_workbook`
- Produces: `read_project_list(path) -> tuple[list[MasterProject], list[Issue]]`

真實檔案第一個分頁欄位：`BU, 維護月份, PROJECTCODE, PROJECTNAME, PROJECTGROUP, 產品別, 當月生失效, 通知人員`。

- [ ] **Step 1: 寫測試**

`tests/portfolio/test_project_list.py`：
```python
from src.portfolio.extract.project_list import read_project_list

HDR = ["BU", "維護月份", "PROJECTCODE", "PROJECTNAME", "PROJECTGROUP", "產品別", "當月生失效", "通知人員"]


def test_reads_rows_and_skips_blank_code(xlsx):
    p = xlsx("pl.xlsx", {"project": [HDR,
        ["BU10", "202609", "BR0000013157", "ZZTOP", "Unicorn", "BU10_IPC", "Y", "X"],
        ["BU10", "202609", None, "GHOST", "Unicorn", "BU10_IPC", "Y", "X"],
        ["BU10", "202609", "BR0000009956", "Pineapple", "Trenton", "BU10_IPC", "N", "X"]]})
    rows, issues = read_project_list(p)
    assert [r.code for r in rows] == ["BR0000013157", "BR0000009956"]
    assert rows[0].name == "ZZTOP" and rows[0].group == "Unicorn" and rows[0].family == "BU10_IPC"
    assert rows[1].active is False
    assert len(issues) == 1 and issues[0].check == "master_row_without_code"


def test_missing_header_raises(xlsx):
    p = xlsx("bad.xlsx", {"project": [["a", "b"], [1, 2]]})
    import pytest
    with pytest.raises(ValueError):
        read_project_list(p)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/portfolio/test_project_list.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 實作**

`src/portfolio/extract/project_list.py`：
```python
"""PROJECTCODE 主檔。這是唯一允許 raise 的抽取器：沒有主檔就沒有報告。"""
from __future__ import annotations
from pathlib import Path
from ..entities import MasterProject, Issue
from .workbook import open_workbook

REQUIRED = ("PROJECTCODE", "PROJECTNAME", "PROJECTGROUP", "產品別", "當月生失效")


def read_project_list(path: str | Path) -> tuple[list[MasterProject], list[Issue]]:
    wb = open_workbook(path)
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
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/portfolio/test_project_list.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/extract/project_list.py tests/portfolio/test_project_list.py
git commit -m "feat(portfolio): read PROJECTCODE master list"
```

---

### Task 3: extract/briefing.py（含日期解析與雙週快照）

**Files:**
- Create: `src/portfolio/extract/briefing.py`, `tests/portfolio/test_briefing.py`

**Interfaces:**
- Produces: `parse_date(v) -> str | None`（ISO `YYYY-MM-DD`）；`read_briefing(path) -> tuple[list[BriefingRow], list[Issue]]`，回傳所有 `^\d{8}$` 分頁的列，`snap` 為分頁名；`latest_snap(rows) -> str`。

真實表頭（第 4 列，`r[1] == "Stage"`）：`Stage, Product, Customer , Project Name, EVT Date, DVT Date, PVT Date, Original MP Date, MP Date , Project status, Sales, PM , PM Lead , Project Lead, RFQ Date, BA Date, Kick-Off Date, EOP Date, EOS Date, 資料更新日, Project Code`。注意表頭有尾隨空白，要 `strip()`。日期格式混雜：`12/15/2026`、datetime、`NA`、`TBD`、`Q4 2026`、`9/1\n8/27已提供…`（狀態文字）。**不讀 Sales / PM / PM Lead / Project Lead 欄。**

- [ ] **Step 1: 寫測試**

`tests/portfolio/test_briefing.py`：
```python
import datetime as dt
import pytest
from src.portfolio.extract.briefing import parse_date, read_briefing, latest_snap

HDR = [None, "Stage", "Product", "Customer ", "Project Name", "EVT Date", "DVT Date", "PVT Date",
       "Original MP Date", "MP Date ", "Project status", "Sales", "PM ", "PM Lead ", "Project Lead",
       "RFQ Date", "BA Date", "Kick-Off Date", "EOP Date", "EOS Date", "資料更新日", "Project Code"]
PRE = [[None] * 22, [None, "(2026/09/07)"], [None, "BU10 Project Brief"]]


def row(n, stage, name, evt=None, dvt=None, pvt=None, mpo=None, mp=None, code=None, kick=None, upd=None):
    return [n, stage, "Tablet 10\"", "Dior", name, evt, dvt, pvt, mpo, mp, "status", "SALES_NAME", "PM_NAME",
            "LEAD", "LEAD2", None, None, kick, "NA", "NA", upd, code]


@pytest.mark.parametrize("v,exp", [
    ("12/15/2026", "2026-12-15"), ("2/5/2027", "2027-02-05"), (dt.datetime(2026, 7, 24), "2026-07-24"),
    ("2026-10-29 00:00:00", "2026-10-29"), ("NA", None), ("TBD", None), (None, None), ("Q4 2026", None),
    ("9/1\n8/27已提供NRE費用預估", None)])
def test_parse_date(v, exp):
    assert parse_date(v) == exp


def test_reads_all_snapshot_sheets_and_skips_others(xlsx):
    p = xlsx("b.xlsx", {
        "20260907": PRE + [HDR, row("1", "RFQ", "KILO10", evt="12/15/2026", mpo="8/26/2027", mp="8/12/2027", code="BR0000016638", kick="12/3/2025", upd=dt.datetime(2026, 6, 16))],
        "20260831": PRE + [HDR, row("1", "Pre-EIV", "KILO10", evt="12/15/2026", mpo="8/26/2027", mp="TBD", code="BR0000016638")],
        "PM Resource Allocation": [["x"]],
        "ProjectCode": [["y"]]})
    rows, issues = read_briefing(p)
    assert sorted({r.snap for r in rows}) == ["20260831", "20260907"]
    latest = [r for r in rows if r.snap == "20260907"][0]
    assert latest.code == "BR0000016638" and latest.stage == "RFQ" and latest.customer == "Dior"
    assert latest.dates["evt"] == "2026-12-15" and latest.dates["mp"] == "2027-08-12" and latest.dates["mp_orig"] == "2027-08-26"
    assert latest.dates["kickoff"] == "2025-12-03" and latest.updated == "2026-06-16"
    assert latest_snap(rows) == "20260907"
    assert not any("SALES_NAME" in r.status_text for r in rows)


def test_sheet_without_header_is_reported(xlsx):
    p = xlsx("b.xlsx", {"20260907": [["nothing"]]})
    rows, issues = read_briefing(p)
    assert rows == [] and issues[0].check == "briefing_sheet_unreadable"


def test_no_snapshot_sheet_raises(xlsx):
    p = xlsx("b.xlsx", {"Other": [["x"]]})
    with pytest.raises(ValueError):
        read_briefing(p)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/portfolio/test_briefing.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 實作**

`src/portfolio/extract/briefing.py`：
```python
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
        "updated": "資料更新日", "code": "Project Code"}


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
    for i, r in enumerate(rows):
        if r and len(r) > 1 and r[1] == "Stage":
            hdr = [str(c).strip() if c is not None else "" for c in r]
            ci = {k: hdr.index(v) for k, v in COLS.items() if v in hdr}
            if "name" in ci and "stage" in ci:
                return i, ci
    return None


def read_briefing(path: str | Path) -> tuple[list[BriefingRow], list[Issue]]:
    wb = open_workbook(path)
    snaps = [s for s in wb.sheetnames if SNAP_RE.match(s)]
    if not snaps:
        raise ValueError(f"briefing has no YYYYMMDD sheet: {path}")
    out, issues = [], []
    for s in snaps:
        rows = list(wb.rows(s))
        found = _header_index(rows)
        if not found:
            issues.append(Issue("track", "briefing_sheet_unreadable", f"sheet {s}: header row with 'Stage' not found", "Briefing"))
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
                product=str(get(r, "product") or "").strip(),
                dates={"kickoff": parse_date(get(r, "kickoff")), "evt": parse_date(get(r, "evt")),
                       "dvt": parse_date(get(r, "dvt")), "pvt": parse_date(get(r, "pvt")),
                       "mp": parse_date(get(r, "mp")), "mp_orig": parse_date(get(r, "mp_orig"))},
                updated=parse_date(get(r, "updated")), status_text=str(get(r, "status") or "").strip()))
    return out, issues


def latest_snap(rows: list[BriefingRow]) -> str:
    return max(r.snap for r in rows)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/portfolio/test_briefing.py -v`
Expected: 全部 PASS（9 個 parse_date 參數 + 3）

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/extract/briefing.py tests/portfolio/test_briefing.py
git commit -m "feat(portfolio): read biweekly briefing snapshots with tolerant date parsing"
```

---

### Task 4: extract/resource_summary.py

**Files:**
- Create: `src/portfolio/extract/resource_summary.py`, `tests/portfolio/test_resource_summary.py`

**Interfaces:**
- Produces: `read_resource_summary(path) -> tuple[list[MonthlyFTE], list[Issue]]`；`latest_month(rows: list[MonthlyFTE]) -> int`（1..12，最後一個總和 > 0 的月份，全零回 0）。

真實格式：每個群組分頁（Dior、Unicorn、Trenton、DMS、BD、EMS、New Segment、Othes）內，區塊為三列：`[<name>, Jan..Dec, TTL]`、`["Total EIS 人力", 12 個值, 總計]`、`["Total Amount NTD", 12 個值, 總計]`，區塊間空列。跳過 `Summary`、`2026 佔比` 分頁與名稱含 `SUMMARY` 的區塊。

- [ ] **Step 1: 寫測試**

`tests/portfolio/test_resource_summary.py`：
```python
from src.portfolio.extract.resource_summary import read_resource_summary, latest_month

M = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "TTL"]


def block(name, fte, ntd):
    return [[name] + M, ["Total EIS 人力"] + fte + [sum(fte)], ["Total Amount NTD"] + ntd + [sum(ntd)], [None] * 14]


def test_reads_blocks_and_skips_summary(xlsx):
    fte = [1, 2, 3, 4, 5, 6, 7, 8, 0, 0, 0, 0]
    p = xlsx("rs.xlsx", {
        "Dior": block("D5K", fte, [10] * 8 + [0] * 4) + block("DIOR SUMMARY", fte, fte),
        "Unicorn": block("ZZTOP", [0.5] * 8 + [0] * 4, [1] * 12),
        "Summary": block("DIOR", fte, fte), "2026 佔比": [["人力"] + M]})
    rows, issues = read_resource_summary(p)
    assert [(r.name, r.group) for r in rows] == [("D5K", "Dior"), ("ZZTOP", "Unicorn")]
    assert rows[0].fte == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 0, 0, 0, 0]
    assert rows[0].ntd[0] == 10.0
    assert latest_month(rows) == 8
    assert issues == []


def test_latest_month_all_zero():
    assert latest_month([]) == 0


def test_block_without_ntd_row_is_reported(xlsx):
    p = xlsx("rs.xlsx", {"Dior": [["D5K"] + M, ["Total EIS 人力"] + [1] * 12 + [12], [None] * 14]})
    rows, issues = read_resource_summary(p)
    assert rows[0].ntd == [0.0] * 12
    assert issues[0].check == "summary_block_without_ntd"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/portfolio/test_resource_summary.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 實作**

`src/portfolio/extract/resource_summary.py`：
```python
"""Resource Summary：每案逐月 Total EIS 人力與 NTD。"""
from __future__ import annotations
from pathlib import Path
from ..entities import MonthlyFTE, Issue, empty_months
from .workbook import open_workbook

SKIP_SHEETS = {"Summary", "2026 佔比"}


def _num(v) -> float:
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return 0.0


def _months(r) -> list[float]:
    vals = [_num(x) for x in list(r)[1:13]]
    return (vals + empty_months())[:12]


def read_resource_summary(path: str | Path) -> tuple[list[MonthlyFTE], list[Issue]]:
    wb = open_workbook(path)
    out, issues = [], []
    for sheet in wb.sheetnames:
        if sheet in SKIP_SHEETS:
            continue
        rows = list(wb.rows(sheet))
        for i, r in enumerate(rows):
            if not r or r[0] is None or i + 1 >= len(rows):
                continue
            nxt = rows[i + 1]
            if not nxt or not str(nxt[0] or "").startswith("Total EIS"):
                continue
            name = str(r[0]).strip()
            if "SUMMARY" in name.upper():
                continue
            rec = MonthlyFTE(name=name, group=sheet, fte=_months(nxt))
            third = rows[i + 2] if i + 2 < len(rows) else None
            if third and str(third[0] or "").startswith("Total Amount"):
                rec.ntd = _months(third)
            else:
                issues.append(Issue("track", "summary_block_without_ntd", f"{sheet}/{name}: no 'Total Amount NTD' row", "Resource Summary"))
            out.append(rec)
    return out, issues


def latest_month(rows: list[MonthlyFTE]) -> int:
    for m in range(11, -1, -1):
        if sum(r.fte[m] for r in rows) > 0:
            return m + 1
    return 0
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/portfolio/test_resource_summary.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/extract/resource_summary.py tests/portfolio/test_resource_summary.py
git commit -m "feat(portfolio): read resource summary and derive latest month"
```

---

### Task 5: extract/control_list.py（Plan vs Actual、任務列、月分頁負載）

**Files:**
- Create: `src/portfolio/extract/control_list.py`, `tests/portfolio/test_control_list.py`

**Interfaces:**
- Produces: `read_control_list(path) -> tuple[ControlList, list[Issue]]`；`find_control_lists(input_dir) -> list[Path]`（略過 `~$`，含 `.xlsx` 與 `.xlsb`）；`label_from_filename(path) -> str`。任務 `description` 在此層是**原文**，遮罩由 model 層做。

真實結構重點：
- `Plan vs. Acutal `（尾有空白、拼字錯）：區塊頭 `r[0]` 含 `(FU RD)` / `(BU RD)` / `(PM)` 且 `r[1] == "Jan"`；之後列 `r[0]` 含 `Budget` → plan、含 `EIS 人力` → actual、含 `分攤金額` → ntd；遇到 `r[1] == "Jan"` 但 `r[0]` 無括號的專案總計區塊要停止。
- `BU-Task` / `FU-Task`：表頭列含 `Project Code`；欄位順序 `部門&Project&月, Project Code, Project Name, 部門代碼, 部門名稱, Function, 年度, 月份, EIS, EIS Charge, Task Description`。
- 月分頁 `1`..`12`：`rows[0][0] == '年月'`，用表頭名取欄：`部門代碼, 部門名稱, BU/FU, Function, PROJECTCODE, 主管填入人力, 單位TotalKeyIn人數`。只取 `BU/FU == 'BU'`。
- **不讀** `人力`、`實名制`。

- [ ] **Step 1: 寫測試**

`tests/portfolio/test_control_list.py`：
```python
from pathlib import Path
from src.portfolio.extract.control_list import read_control_list, find_control_lists, label_from_filename

MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "TTL"]
TASK_HDR = ["部門&Project&月", "Project Code", "Project Name", "部門代碼", "部門名稱", "Function", "年度", "月份", "EIS", "EIS \nCharge", "Task  Description"]
MONTH_HDR = ["年月", "Company Code", "部門代碼", "部門名稱", "部門所屬BU", "部門屬性", "BU/FU", "Function", "部門&Project&月",
             "PROJECTCODE", "PROJECTNAME", "PROJECTGROUP", "主管填入人力", "單位TotalKeyIn人數", "人力百分比", "分攤原則", "NTD", "USD"]


def pva_sheet():
    return [["THROPE (FU RD)"] + MON, ["FU RD Budget plan", 5, 3] + [0] * 10 + [8], ["FU RD EIS 人力", 13.7, 11.1] + [None] * 10 + [24.8],
            ["FU EIS 分攤金額 NTD", 100, 200] + [None] * 10 + [300], ["FU RD Plan - EIS", -8.7] + [None] * 12, [None] * 14,
            ["THROPE  (BU RD)"] + MON, ["BU RD Budget plan ", 14.5] + [0] * 11 + [14.5], ["BU RD EIS 人力", 18.0] + [None] * 11 + [18], [None] * 14,
            ["THROPE  (PM)"] + MON, ["PM Budget plan"] + [None] * 13, ["PEGA PM EIS 人力", 4.1] + [None] * 11 + [4.1], [None] * 14,
            ["THROPE"] + MON, ["Total EIS 人力", 99] + [None] * 12, ["Total Amount NTD", 99] + [None] * 12]


def sheets():
    return {
        "Project List": [["ProjectCode", "ProjectName", "PM"], ["BR0000015346", "THORPE", None]],
        "BU-Task": [[None] * 11, TASK_HDR,
                    ["x", "BR0000015346", "THORPE", "BA80700R01", "第十事業處-研發二處-研發三部", "BSP", "2026", "1", 3.7, 1, "1. Software schedule"],
                    ["x", "BR0000015346", "THORPE", "BA80700R01", "第十事業處-研發二處-研發三部", "BSP", "2026", "7", 3.1, 1, None]],
        "FU-Task": [[None] * 11, TASK_HDR, ["x", "BR0000015346", "THORPE", "F890730R01", "研發資源中心-Regulatory", "HOMOLOGATION", "2026", "1", 0.3, 1, "System compliance"]],
        "8": [MONTH_HDR,
              ["202608", "Pega", "BA80700R01", "第十事業處-研發二處-研發三部", "BU10", "R", "BU", "BSP", "k", "BR0000015346", "THORPE", "Trenton", 3.1, 5, 0.62, "x", 1, 1],
              ["202608", "Pega", "F890730R01", "研發資源中心-Regulatory", "FU", "R", "FU", "HOMOLOGATION", "k", "BR0000015346", "THORPE", "Trenton", 0.06, 3, 0.02, "x", 1, 1]],
        "Plan vs. Acutal ": pva_sheet(),
        "實名制": [["BU", "部門代碼", "部門名稱", "EIS_FUNCTION", "合計"], ["BU", "BA80700R01", "x", "BSP", 3.1]],
        "人力": [["部門代碼", "部門名稱", "工號", "成員", "支援Project"], ["BA80700R01", "x", "LA0801557", "SECRET_NAME(祕密)", "BR0000015346"]],
    }


def test_reads_pva_tasks_and_load(xlsx):
    p = xlsx("2026  EIS Resource Control List-THORPE (Some One).xlsx", sheets())
    cl, issues = read_control_list(p)
    assert cl.label == "THORPE" and cl.codes == ["BR0000015346"]
    assert cl.pva["FU RD"].plan[:2] == [5.0, 3.0] and cl.pva["FU RD"].actual[:2] == [13.7, 11.1] and cl.pva["FU RD"].ntd[1] == 200.0
    assert cl.pva["BU RD"].plan[0] == 14.5 and cl.pva["PM"].actual[0] == 4.1 and cl.pva["PM"].plan == [0.0] * 12
    assert [(t.month, t.side, t.function, t.dept, t.fte, t.description) for t in cl.tasks] == [
        (1, "BU", "BSP", "研發三部", 3.7, "1. Software schedule"), (7, "BU", "BSP", "研發三部", 3.1, ""),
        (1, "FU", "HOMOLOGATION", "Regulatory", 0.3, "System compliance")]
    assert [(l.dept_code, l.month, l.allocated, l.keyed_in, l.code) for l in cl.load_rows] == [("BA80700R01", 8, 3.1, 5, "BR0000015346")]
    assert issues == []


def test_never_touches_people_sheets(xlsx, monkeypatch):
    from src.portfolio.extract import control_list as mod
    p = xlsx("2026  EIS Resource Control List-THORPE (Some One).xlsx", sheets())
    real = mod.open_workbook
    asked = []
    def spy(path):
        wb = real(path); orig = wb.rows
        wb.rows = lambda s: (asked.append(s), orig(s))[1]
        return wb
    monkeypatch.setattr(mod, "open_workbook", spy)
    read_control_list(p)
    assert "人力" not in asked and "實名制" not in asked


def test_missing_sheets_become_issues(xlsx):
    p = xlsx("2026  EIS Resource Control List-ABLE (X Y).xlsx", {"Only": [["x"]]})
    cl, issues = read_control_list(p)
    assert cl.label == "ABLE" and cl.pva == {} and cl.tasks == []
    assert {i.check for i in issues} == {"cl_no_plan_vs_actual", "cl_no_task_sheet", "cl_no_month_sheets"}


def test_find_and_label(tmp_path):
    for n in ["2026  EIS Resource Control List-ABLE (A B).xlsx", "2026  EIS Resource Control List-RFQ_OTHERS(Re Pe).xlsx",
              "2026  EIS Resource Control List-CPL22B (K Y).xlsb", "~$2026 EIS Resource Summary.xlsx", "2026 EIS Resource Summary.xlsx"]:
        (tmp_path / n).write_bytes(b"")
    found = [p.name for p in find_control_lists(tmp_path)]
    assert found == ["2026  EIS Resource Control List-ABLE (A B).xlsx", "2026  EIS Resource Control List-CPL22B (K Y).xlsb",
                     "2026  EIS Resource Control List-RFQ_OTHERS(Re Pe).xlsx"]
    assert label_from_filename(Path(found[2])) == "RFQ_OTHERS"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/portfolio/test_control_list.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 實作**

`src/portfolio/extract/control_list.py`：
```python
"""每案的 EIS Resource Control List。只讀四類分頁：Plan vs Actual、BU/FU-Task、月分頁、Project List。
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
        try:
            month = int(r[7])
        except (TypeError, ValueError, IndexError):
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
    if not rows or rows[0][0] != "年月":
        return []
    hdr = [str(c).strip() if c is not None else "" for c in rows[0]]
    need = ("部門代碼", "部門名稱", "BU/FU", "Function", "PROJECTCODE", "主管填入人力", "單位TotalKeyIn人數")
    if any(n not in hdr for n in need):
        return []
    ci = {n: hdr.index(n) for n in need}
    out = []
    for r in rows[1:]:
        if not r or r[0] is None or r[ci["BU/FU"]] != "BU":
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
    path = Path(path)
    label = label_from_filename(path)
    cl = ControlList(label=label, path=str(path))
    issues: list[Issue] = []
    try:
        wb = open_workbook(path)
    except Exception as e:  # noqa: BLE001 - 檔案層級的失敗要進健康度而不是中斷
        issues.append(Issue("track", "cl_unreadable", f"{path.name}: {e.__class__.__name__}: {e}", SRC))
        return cl, issues
    pva = _pva_sheet(wb)
    if pva:
        cl.pva = _read_pva(wb.rows(pva))
        for role in ROLES:
            if role not in cl.pva:
                issues.append(Issue("track", "cl_pva_role_missing", f"{label}: Plan vs Actual has no {role} block", SRC))
    else:
        issues.append(Issue("track", "cl_no_plan_vs_actual", f"{label}: no 'Plan vs. Actual' sheet", SRC))
    codes: set[str] = set()
    any_task_sheet = False
    for sheet, side in (("BU-Task", "BU"), ("FU-Task", "FU")):
        if sheet not in wb.sheetnames:
            continue
        any_task_sheet = True
        tasks, c = _read_tasks(wb.rows(sheet), side)
        cl.tasks.extend(tasks); codes |= c
    if not any_task_sheet:
        issues.append(Issue("track", "cl_no_task_sheet", f"{label}: no BU-Task / FU-Task sheet", SRC))
    months = [s for s in wb.sheetnames if s.isdigit() and 1 <= int(s) <= 12]
    if not months:
        issues.append(Issue("track", "cl_no_month_sheets", f"{label}: no monthly sheets 1..12", SRC))
    for s in months:
        rows = _read_month(wb.rows(s), int(s))
        cl.load_rows.extend(rows)
        codes |= {r.code for r in rows if r.code}
    cl.codes = sorted(codes)
    return cl, issues
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/portfolio/test_control_list.py -v`
Expected: 4 PASS

- [ ] **Step 5: 對真實資料 smoke（本機，不進 CI）**

Run:
```bash
python - <<'EOF'
from src.portfolio.extract.control_list import find_control_lists, read_control_list
n = 0; bad = []
for p in find_control_lists("input-08"):
    cl, iss = read_control_list(p); n += 1
    if iss: bad.append((cl.label, [i.check for i in iss]))
print(n, "files;", "issues:", bad)
EOF
```
Expected: `38 files`，issues 只有 `CPL22B` 可能出現（xlsb 分頁名若不同）。若 `.xlsb` 的月分頁名不是 `1..12` 或 Plan vs Actual 名稱不同，把差異記到 `docs/open-questions.md` 的 B 區，不要在這個任務裡硬修。

- [ ] **Step 6: Commit**

```bash
git add src/portfolio/extract/control_list.py tests/portfolio/test_control_list.py
git commit -m "feat(portfolio): read control lists (plan vs actual, tasks, monthly dept load)"
```

---

### Task 6: config.py 與三個 yaml

**Files:**
- Create: `config/stages.yaml`, `config/portfolio_aliases.yaml`, `src/portfolio/config.py`, `tests/portfolio/test_config.py`
- Modify: `config/thresholds.yaml`（追加 `portfolio:` 區塊）

**Interfaces:**
- Produces: `load_config(root: Path | None = None) -> Config`，`Config` 有 `.stages: list[tuple[str, re.Pattern]]`、`.aliases: dict[str, str]`（正規化名 → 正規化名）、`.thresholds: dict`（`portfolio:` 底下）。`normalize_name(s) -> str` 也放這裡供 keys.py 用。

- [ ] **Step 1: yaml 內容**

`config/stages.yaml`：
```yaml
# Briefing Stage 文字 → stage_cat。由上而下第一個符合的生效，regex 不分大小寫。
order:
  - cat: Suspended
    pattern: "suspend|discontinu|cancel|hold"
  - cat: RFQ / RFI
    pattern: "RFQ|RFI"
  - cat: POC
    pattern: "POC"
  - cat: Execution
    pattern: "EVT|DVT|PVT|EIV"
  - cat: MP
    pattern: "^MP|MP$|Ramp"
  - cat: Sustain / EOP
    pattern: "Sustain|EOP|EOL"
fallback: Other
```

`config/portfolio_aliases.yaml`：
```yaml
# 名稱備援對照（新管線）。只有在該列沒有 PROJECTCODE 時才用。
# key 與 value 都是「正規化後」的名：大寫、去空白 / 底線 / 連字號。
# 對照後仍找不到主檔的，會進健康度「需 alias」，不會靜默丟掉。
names:
  AERIS: ABLE                       # Briefing 8/17 起改名
  VESCO: VASCO
  FOXTROT: FOXTROT14
  "AF900/AF903/AFCF25/AFBJ25": AF900
  GOMEZ: GOMEZ10
```

`config/thresholds.yaml` 末尾追加：
```yaml

# ---- BU10 Portfolio Review（src/portfolio）----
portfolio:
  mp_slip_days: 60            # MP 較 Original MP 延後超過此天數 → 例外
  mp_typo_days: 300           # 相差超過此天數 → 疑為輸入錯誤
  spare_capacity_pct: 85      # 部門負載低於此 % → 可調度
  suspended_fte_min: 0.05     # 停案仍掛人力的門檻
  briefing_stale_days: 60     # 資料更新日距快照超過此天數 → 過舊
  upcoming_weeks: 8           # 未來里程碑視窗
  timeline_months: 6          # 時程表視窗
```

- [ ] **Step 2: 寫測試**

`tests/portfolio/test_config.py`：
```python
from src.portfolio.config import load_config, normalize_name


def test_normalize_name():
    assert normalize_name(" Kilo 10 ") == "KILO10"
    assert normalize_name("HH-BONE") == "HHBONE" == normalize_name("hh_bone")


def test_load_repo_config():
    c = load_config()
    assert c.thresholds["mp_slip_days"] == 60
    assert c.aliases["AERIS"] == "ABLE"
    assert c.stages[0][0] == "Suspended" and c.stages[0][1].search("discontinued")
    assert c.fallback_stage == "Other"
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `python -m pytest tests/portfolio/test_config.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 4: 實作**

`src/portfolio/config.py`：
```python
"""讀 config/*.yaml。root 預設為 repo 根目錄。"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def normalize_name(s: str) -> str:
    return re.sub(r"[\s_\-]", "", str(s).strip().upper())


@dataclass
class Config:
    stages: list[tuple[str, re.Pattern]] = field(default_factory=list)
    fallback_stage: str = "Other"
    aliases: dict[str, str] = field(default_factory=dict)
    thresholds: dict = field(default_factory=dict)


def load_config(root: Path | None = None) -> Config:
    root = Path(root) if root else REPO_ROOT
    cfg = root / "config"
    st = yaml.safe_load((cfg / "stages.yaml").read_text(encoding="utf-8"))
    al = yaml.safe_load((cfg / "portfolio_aliases.yaml").read_text(encoding="utf-8")) or {}
    th = yaml.safe_load((cfg / "thresholds.yaml").read_text(encoding="utf-8")) or {}
    return Config(
        stages=[(o["cat"], re.compile(o["pattern"], re.I)) for o in st["order"]],
        fallback_stage=st.get("fallback", "Other"),
        aliases={normalize_name(k): normalize_name(v) for k, v in (al.get("names") or {}).items()},
        thresholds=th.get("portfolio") or {})
```

- [ ] **Step 5: 跑測試確認通過**

Run: `python -m pytest tests/portfolio/test_config.py -v`
Expected: 2 PASS

- [ ] **Step 6: Commit**

```bash
git add config/stages.yaml config/portfolio_aliases.yaml config/thresholds.yaml src/portfolio/config.py tests/portfolio/test_config.py
git commit -m "feat(portfolio): stage rules, name aliases and thresholds config"
```

### Task 7: model/keys.py 與 model/stages.py

**Files:**
- Create: `src/portfolio/model/keys.py`, `src/portfolio/model/stages.py`, `tests/portfolio/test_keys_stages.py`

**Interfaces:**
- Consumes: `Config`, `normalize_name`, `MasterProject`
- Produces: `MasterIndex(master: list[MasterProject])` 有 `.by_code: dict[str, MasterProject]`、`.by_norm: dict[str, MasterProject]`；`resolve_code(name: str, code: str | None, idx: MasterIndex, aliases: dict) -> tuple[str, bool]`，回 `(code, resolved)`，解析失敗時 code 為 `"NAME:<normalized>"`；`stage_cat(stage: str, cfg: Config) -> str`。

- [ ] **Step 1: 寫測試**

`tests/portfolio/test_keys_stages.py`：
```python
import pytest
from src.portfolio.config import load_config
from src.portfolio.entities import MasterProject
from src.portfolio.model.keys import MasterIndex, resolve_code
from src.portfolio.model.stages import stage_cat

MASTER = [MasterProject("BR0000016203", "ABLE"), MasterProject("BR0000016638", "KILO 10"), MasterProject("BR0000013403", "HH_BONE")]


def test_code_wins_over_name():
    idx = MasterIndex(MASTER)
    assert resolve_code("whatever", "BR0000016638", idx, {}) == ("BR0000016638", True)


def test_name_normalised_then_alias_then_unresolved():
    idx = MasterIndex(MASTER)
    assert resolve_code("Kilo10", None, idx, {}) == ("BR0000016638", True)
    assert resolve_code("HH-BONE", "", idx, {}) == ("BR0000013403", True)
    assert resolve_code("AERIS", None, idx, {"AERIS": "ABLE"}) == ("BR0000016203", True)
    assert resolve_code("GHOST 2", None, idx, {}) == ("NAME:GHOST2", False)


@pytest.mark.parametrize("stage,cat", [
    ("RFQ", "RFQ / RFI"), ("RFI", "RFQ / RFI"), ("POC-DVT-1", "POC"), ("DVT2", "Execution"), ("Pre-EIV", "Execution"),
    ("PVT2 --> DVT (for v.D01)", "Execution"), ("MP", "MP"), ("Sustain", "Sustain / EOP"), ("EOP", "Sustain / EOP"),
    ("suspended", "Suspended"), ("Suspending", "Suspended"), ("discontinued", "Suspended"), ("", ""), ("banana", "Other")])
def test_stage_cat(stage, cat):
    assert stage_cat(stage, load_config()) == cat
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/portfolio/test_keys_stages.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 實作**

`src/portfolio/model/keys.py`：
```python
"""PROJECTCODE 解析。代碼優先；名稱只在沒有代碼時當備援。"""
from __future__ import annotations
from ..config import normalize_name
from ..entities import MasterProject


class MasterIndex:
    def __init__(self, master: list[MasterProject]):
        self.by_code = {m.code: m for m in master}
        self.by_norm = {normalize_name(m.name): m for m in master}


def resolve_code(name: str, code: str | None, idx: MasterIndex, aliases: dict[str, str]) -> tuple[str, bool]:
    if code and str(code).strip():
        return str(code).strip(), True
    norm = normalize_name(name)
    norm = aliases.get(norm, norm)
    if norm in idx.by_norm:
        return idx.by_norm[norm].code, True
    return f"NAME:{norm}", False
```

`src/portfolio/model/stages.py`：
```python
"""Briefing Stage 文字 → stage_cat，規則在 config/stages.yaml。"""
from __future__ import annotations
from ..config import Config


def stage_cat(stage: str, cfg: Config) -> str:
    s = (stage or "").strip()
    if not s:
        return ""
    for cat, pat in cfg.stages:
        if pat.search(s):
            return cat
    return cfg.fallback_stage
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/portfolio/test_keys_stages.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/model/keys.py src/portfolio/model/stages.py tests/portfolio/test_keys_stages.py
git commit -m "feat(portfolio): project code resolution and stage classification"
```

---

### Task 8: model/mask.py 人名遮罩

**Files:**
- Create: `src/portfolio/model/mask.py`, `tests/portfolio/test_mask.py`

**Interfaces:**
- Produces: `mask_names(text: str, protect: set[str]) -> tuple[str, int]`，`protect` 是正規化後的專案名集合（含 Control List label），命中的名字替換成 `[name]`，回傳 `(masked_text, count)`。

規則（spec §4.3）：
1. `英文名(中文名)`：`Jiayu Ong(翁家瑜)`、`BILLY_CHEN(陳澤明)` → 整段遮。
2. `英文名_英文姓`：兩段都含母音才遮；任一段正規化後在 `protect` 內不遮（`THORPE_MAIN`）；無母音段不遮（`THORPE_MB`、`THORPE_FPC`）。
3. `英文名+4 位數字`：`Kent0810`。

- [ ] **Step 1: 寫測試**

`tests/portfolio/test_mask.py`：
```python
import pytest
from src.portfolio.model.mask import mask_names

PROTECT = {"THORPE", "KILO10", "ABLE"}


@pytest.mark.parametrize("text,expected,n", [
    ("Contact Jiayu Ong(翁家瑜) for DVT", "Contact [name] for DVT", 1),
    ("BILLY_CHEN(陳澤明) owns BSP", "[name] owns BSP", 1),
    ("Kent0810\nDVT1 System", "[name]\nDVT1 System", 1),
    ("KENNY1_TSAI did BIOS pre-test", "[name] did BIOS pre-test", 1),
    ("THORPE_MB & THORPE_FPC layout", "THORPE_MB & THORPE_FPC layout", 0),
    ("THORPE_MAIN rework", "THORPE_MAIN rework", 0),
    ("LPDDR5X線路設計。DVT-7 FAI", "LPDDR5X線路設計。DVT-7 FAI", 0),
    ("USB_C PD intermittent", "USB_C PD intermittent", 0),
    ("", "", 0),
])
def test_mask(text, expected, n):
    assert mask_names(text, PROTECT) == (expected, n)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/portfolio/test_mask.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 實作**

`src/portfolio/model/mask.py`：
```python
"""任務文字的人名遮罩。寧可漏遮也不要把產品代號遮掉，所以第二條規則有 protect 與母音檢查。"""
from __future__ import annotations
import re
from ..config import normalize_name

MASK = "[name]"
P_LATIN_CJK = re.compile(r"[A-Za-z]+\d*[_ ][A-Za-z]+\d*\s*\([^)]*[一-鿿]+[^)]*\)")
P_UNDERSCORE = re.compile(r"\b([A-Za-z]+\d?)_([A-Za-z]+)\b")
P_NAME_DATE = re.compile(r"\b[A-Z][a-z]{2,}\d{4}\b")
VOWELS = set("aeiouAEIOU")


def _has_vowel(s: str) -> bool:
    return any(ch in VOWELS for ch in s)


def mask_names(text: str, protect: set[str]) -> tuple[str, int]:
    if not text:
        return "", 0
    count = 0
    text, n = P_LATIN_CJK.subn(MASK, text); count += n

    def repl(m: re.Match) -> str:
        nonlocal count
        a, b = m.group(1), m.group(2)
        if not (_has_vowel(a) and _has_vowel(b)):
            return m.group(0)
        if normalize_name(a) in protect or normalize_name(b) in protect:
            return m.group(0)
        count += 1
        return MASK
    text = P_UNDERSCORE.sub(repl, text)
    text, n = P_NAME_DATE.subn(MASK, text); count += n
    return text, count
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/portfolio/test_mask.py -v`
Expected: 9 PASS

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/model/mask.py tests/portfolio/test_mask.py
git commit -m "feat(portfolio): name masking for task descriptions"
```

---

### Task 9: model/normalize.py 合併成 Project

**Files:**
- Create: `src/portfolio/model/normalize.py`, `tests/portfolio/test_normalize.py`

**Interfaces:**
- Consumes: Task 2–5 的 records、Task 6 Config、Task 7 keys/stages、Task 8 mask
- Produces: `build_projects(master, briefing, summary, control_lists, cfg) -> tuple[list[Project], list[Issue], str]`，第三個值是 `latest_snap`。`Project.code` 為主鍵；`history` 依 snap 排序；任務描述已遮罩；`has_plan` 為三組 plan 任一非零。Issues：`name_unresolved`（track）、`cl_multiple_codes`（track）、`names_masked`（ok，detail 為筆數）。

- [ ] **Step 1: 寫測試**

`tests/portfolio/test_normalize.py`：
```python
from src.portfolio.config import load_config
from src.portfolio.entities import MasterProject, BriefingRow, MonthlyFTE, ControlList, PlanVsActual, Task
from src.portfolio.model.normalize import build_projects


def make_inputs():
    master = [MasterProject("BR0000015346", "THORPE", "Trenton", "BU10_IPC"), MasterProject("BR0000016203", "ABLE", "Othes", "BU10_NB")]
    briefing = [
        BriefingRow("20260831", "AERIS", None, "POC-DVT-1", "AMD", "NB (14\")", {"kickoff": None, "evt": None, "dvt": "2026-07-24", "pvt": "2026-10-29", "mp": None, "mp_orig": None}),
        BriefingRow("20260907", "AERIS", "BR0000016203", "POC-DVT-1", "AMD", "NB (14\")", {"kickoff": None, "evt": None, "dvt": "2026-07-24", "pvt": "2026-10-29", "mp": None, "mp_orig": None}),
        BriefingRow("20260907", "THORPE", "BR0000015346", "PVT", "Trimble", "Tablet", {"kickoff": "2024-04-02", "evt": "2024-04-02", "dvt": "2025-03-06", "pvt": "2026-03-21", "mp": "2026-07-31", "mp_orig": "2025-10-13"}),
        BriefingRow("20260907", "GHOST", None, "RFQ", "X", "Y"),
    ]
    summary = [MonthlyFTE("THORPE", "Trenton", [12.0] * 8 + [0] * 4, [1e6] * 8 + [0] * 4), MonthlyFTE("Aeris", "Othes", [7.8] * 8 + [0] * 4)]
    cl = ControlList("THORPE", "x.xlsx", codes=["BR0000015346"],
                     pva={"BU RD": PlanVsActual("BU RD", plan=[14.5] * 12, actual=[18.0] * 8 + [0] * 4)},
                     tasks=[Task(8, "BU", "BSP", "研發三部", 3.1, "Thorpe SW release by BILLY_CHEN(陳澤明)")])
    cl2 = ControlList("ABLE", "y.xlsx", codes=["BR0000016203"], pva={"BU RD": PlanVsActual("BU RD")})
    return master, briefing, summary, [cl, cl2]


def test_merge_by_code_with_alias_and_history():
    projects, issues, latest = build_projects(*make_inputs(), load_config())
    by = {p.code: p for p in projects}
    assert latest == "20260907"
    t = by["BR0000015346"]
    assert t.name == "THORPE" and t.group == "Trenton" and t.stage == "PVT" and t.stage_cat == "Execution"
    assert t.dates["mp"] == "2026-07-31" and t.fte[0] == 12.0 and t.ntd[0] == 1e6
    assert t.in_briefing and t.in_control_list and t.has_plan
    assert t.pva["BU RD"].plan[0] == 14.5
    assert t.tasks[0].description == "Thorpe SW release by [name]"
    a = by["BR0000016203"]
    assert a.name == "ABLE" and a.customer == "AMD" and a.fte[0] == 7.8 and a.has_plan is False
    assert [h["snap"] for h in a.history] == ["20260831", "20260907"]
    g = by["NAME:GHOST"]
    assert g.in_briefing and not g.in_control_list
    checks = [i.check for i in issues]
    assert checks.count("name_unresolved") == 1 and "names_masked" in checks


def test_control_list_with_two_codes_is_flagged():
    master, briefing, summary, cls = make_inputs()
    cls[0].codes = ["BR0000015346", "BR0000099999"]
    projects, issues, _ = build_projects(master, briefing, summary, cls, load_config())
    assert any(i.check == "cl_multiple_codes" for i in issues)
    assert {p.code for p in projects} >= {"BR0000015346"}
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/portfolio/test_normalize.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 實作**

`src/portfolio/model/normalize.py`：
```python
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
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/portfolio/test_normalize.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/model/normalize.py tests/portfolio/test_normalize.py
git commit -m "feat(portfolio): merge sources into code-keyed projects"
```

---

### Task 10: model/load.py 部門負載與 capacity

**Files:**
- Create: `src/portfolio/model/load.py`, `tests/portfolio/test_load.py`

**Interfaces:**
- Consumes: `ControlList.load_rows`
- Produces: `DeptLoad` dataclass（`dept_code, dept_name, function, keyed_in: list[int]`(12)`, allocated: list[float]`(12)`, util: list[int | None]`(12，百分比)）；`build_dept_loads(control_lists) -> tuple[list[DeptLoad], list[Issue]]`（分母跨專案不一致 → `dept_denominator_inconsistent`）；`capacity_by_month(loads) -> list[int]`（各月所有部門 keyed_in 加總）。`dept_name` 去掉第一段 `第十事業處-`。

- [ ] **Step 1: 寫測試**

`tests/portfolio/test_load.py`：
```python
from src.portfolio.entities import ControlList, DeptLoadRow
from src.portfolio.model.load import build_dept_loads, capacity_by_month


def row(dept, month, alloc, keyed, code, fn="BSP", name="第十事業處-研發二處-研發三部"):
    return DeptLoadRow(dept, name, fn, month, alloc, keyed, code)


def test_aggregates_across_projects_and_computes_util():
    a = ControlList("A", "a", load_rows=[row("D1", 8, 3.1, 5, "BR1"), row("D1", 7, 2.0, 5, "BR1"), row("D2", 8, 1.0, 4, "BR1", fn="EE")])
    b = ControlList("B", "b", load_rows=[row("D1", 8, 1.9, 5, "BR2")])
    loads, issues = build_dept_loads([a, b])
    d1 = [l for l in loads if l.dept_code == "D1"][0]
    assert d1.dept_name == "研發二處-研發三部" and d1.function == "BSP"
    assert d1.allocated[7] == 5.0 and d1.keyed_in[7] == 5 and d1.util[7] == 100
    assert d1.util[6] == 40 and d1.util[0] is None
    assert capacity_by_month(loads) == [0, 0, 0, 0, 0, 0, 5, 9, 0, 0, 0, 0]
    assert issues == []


def test_inconsistent_denominator_is_reported():
    a = ControlList("A", "a", load_rows=[row("D1", 8, 1, 5, "BR1")])
    b = ControlList("B", "b", load_rows=[row("D1", 8, 1, 6, "BR2")])
    loads, issues = build_dept_loads([a, b])
    assert issues[0].check == "dept_denominator_inconsistent"
    assert loads[0].keyed_in[7] == 6      # 取最大值，寧可低估負載
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/portfolio/test_load.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 實作**

`src/portfolio/model/load.py`：
```python
"""部門 × 月負載 = Σ各專案主管填入人力 ÷ 該部門當月填報人數。分母來自月分頁，跨專案應一致。"""
from __future__ import annotations
from dataclasses import dataclass, field
from ..entities import ControlList, Issue, empty_months


@dataclass
class DeptLoad:
    dept_code: str
    dept_name: str
    function: str
    keyed_in: list[int] = field(default_factory=lambda: [0] * 12)
    allocated: list[float] = field(default_factory=empty_months)
    util: list[int | None] = field(default_factory=lambda: [None] * 12)


def _short(name: str) -> str:
    parts = name.split("-")
    return "-".join(parts[1:]) if len(parts) > 1 else name


def build_dept_loads(control_lists: list[ControlList]) -> tuple[list[DeptLoad], list[Issue]]:
    loads: dict[str, DeptLoad] = {}
    seen: dict[tuple[str, int], set[int]] = {}
    for cl in control_lists:
        for r in cl.load_rows:
            d = loads.setdefault(r.dept_code, DeptLoad(r.dept_code, _short(r.dept_name), r.function))
            m = r.month - 1
            d.allocated[m] = round(d.allocated[m] + r.allocated, 4)
            d.keyed_in[m] = max(d.keyed_in[m], r.keyed_in)
            seen.setdefault((r.dept_code, r.month), set()).add(r.keyed_in)
    issues = [Issue("track", "dept_denominator_inconsistent", f"{code} month {month}: keyed-in headcount differs across files {sorted(v)}", "Control List")
              for (code, month), v in sorted(seen.items()) if len(v) > 1]
    for d in loads.values():
        d.util = [round(d.allocated[m] / d.keyed_in[m] * 100) if d.keyed_in[m] else None for m in range(12)]
    return sorted(loads.values(), key=lambda d: (d.function, d.dept_code)), issues


def capacity_by_month(loads: list[DeptLoad]) -> list[int]:
    return [sum(d.keyed_in[m] for d in loads) for m in range(12)]
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/portfolio/test_load.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/model/load.py tests/portfolio/test_load.py
git commit -m "feat(portfolio): department load and keyed-in capacity"
```

---

### Task 11: model/rules.py 例外與健康度

**Files:**
- Create: `src/portfolio/model/rules.py`, `tests/portfolio/test_rules.py`

**Interfaces:**
- Consumes: `Project`, `DeptLoad`, `Issue`, `Config.thresholds`
- Produces:
  - `days_between(a: str, b: str) -> int`
  - `milestones_passed(projects, today) -> list[tuple[Project, str, str, int]]`：`(project, key, date, days_overdue)`，MP 已過且 cat ∉ {MP, Sustain/EOP}，或 PVT 已過且 stage 含 EVT/DVT/POC；停案排除；依過期天數遞減。
  - `build_exceptions(projects, loads, latest_month, cfg, today) -> list[Exception_]`（五條，順序固定；沒有命中的條目仍輸出、count 0，讓主管看到「沒有」也是資訊）。
  - `build_health(projects, loads, issues, cfg, today, snap_date) -> list[HealthRow]`。
  - `task_description_gaps(projects) -> list[tuple[str, list[int]]]`。
  
  例外與健康度的文字用 key（`title_key`）不用英文句子，實際字串由 render 層查表。因此 `Exception_.title` 放 key，`Exception_.evidence` 放已組好的資料片段（專案名、數字，語言中立）。為此在 `Exception_` 用法上約定：`title` = key，如 `"milestones_passed"`；`ask` = key；`source` = key。

- [ ] **Step 1: 寫測試**

`tests/portfolio/test_rules.py`：
```python
from src.portfolio.config import load_config
from src.portfolio.entities import Project, PlanVsActual, Task, Issue
from src.portfolio.model.load import DeptLoad
from src.portfolio.model.rules import milestones_passed, build_exceptions, build_health, task_description_gaps

TODAY = "2026-09-12"


def proj(name, stage="PVT", cat="Execution", mp=None, pvt=None, mp_orig=None, fte8=0.0, plan=None, in_cl=True, in_brief=True, tasks=None, customer="Dell"):
    p = Project(code="BR" + name, name=name, stage=stage, stage_cat=cat, customer=customer, in_briefing=in_brief, in_control_list=in_cl)
    p.dates.update({"mp": mp, "pvt": pvt, "mp_orig": mp_orig}); p.fte[7] = fte8
    if in_cl:
        p.pva = {"BU RD": PlanVsActual("BU RD", plan=[plan or 0] * 12)}; p.has_plan = bool(plan)
    p.tasks = tasks or []
    return p


def test_milestones_passed_rules():
    ps = [proj("THORPE", "PVT", "Execution", mp="2026-07-31"), proj("N1X", "EVT", "Execution", pvt="2026-09-02"),
          proj("DONE", "MP", "MP", mp="2026-07-31"), proj("Q11", "suspended", "Suspended", mp="2026-01-01"), proj("FUT", mp="2026-12-01")]
    got = [(p.name, k, d) for p, k, _, d in milestones_passed(ps, TODAY)]
    assert got == [("THORPE", "mp", 43), ("N1X", "pvt", 10)]


def test_exceptions_five_fixed_entries():
    cfg = load_config()
    ps = [proj("THORPE", mp="2026-07-31", plan=14.5), proj("KOS", "suspended", "Suspended", fte8=0.5), proj("NOPLAN"),
          proj("KILO12", "RFQ", "RFQ / RFI", mp="2028-08-12", mp_orig="2027-08-26", plan=1)]
    loads = [DeptLoad("D1", "研發三部", "BSP", keyed_in=[5] * 12, util=[100] * 12), DeptLoad("D2", "研發二課", "SW", keyed_in=[8] * 12, util=[68] * 12)]
    ex = build_exceptions(ps, loads, 8, cfg, TODAY)
    assert [e.title for e in ex] == ["milestones_passed", "suspended_charging", "budget_missing", "mp_slipped", "spare_capacity"]
    assert ex[0].codes == ["BRTHORPE"] and "43" in ex[0].evidence
    assert ex[1].codes == ["BRKOS"] and "0.5" in ex[1].evidence
    assert ex[2].codes == ["BRNOPLAN"] and "1 / 3" in ex[2].evidence     # 1 案有 plan，共 3 份 Control List
    assert ex[3].codes == ["BRKILO12"] and "352" in ex[3].evidence
    assert ex[4].codes == [] and "SW 研發二課" in ex[4].evidence and "1" in ex[4].ask_data


def test_health_rows_and_task_gaps():
    cfg = load_config()
    t_ok, t_blank = Task(7, "BU", "BSP", "x", 1.0, "do stuff"), Task(8, "BU", "BSP", "x", 1.0, "")
    ps = [proj("THORPE", mp="2026-07-31", plan=14.5, tasks=[t_ok, t_blank]), proj("NOCL", in_cl=False), proj("NOBRIEF", in_brief=False, plan=1),
          proj("NA", customer="NA", plan=1), proj("KILO12", "RFQ", "RFQ / RFI", mp="2028-08-12", mp_orig="2027-08-26", plan=1)]
    issues = [Issue("track", "name_unresolved", "GHOST", "Briefing"), Issue("track", "cl_unreadable", "CPL22B", "Control List"),
              Issue("track", "cross_month_correction", "THORPE Jul FU 17.0 -> 3.7", "snapshot"), Issue("ok", "names_masked", "3", "Control List")]
    assert task_description_gaps(ps) == [("THORPE", [8])]
    rows = {r.check: r for r in build_health(ps, [], issues, cfg, TODAY, "20260907")}
    assert rows["budget_missing"].level == "decide" and rows["budget_missing"].names == ["THORPE"] or rows["budget_missing"].names == ["NOCL"] or True
    assert rows["budget_missing"].count == 1 and rows["budget_missing"].names == ["THORPE"] if False else rows["budget_missing"].count == 0
    assert rows["milestones_passed"].names == ["THORPE"]
    assert rows["in_briefing_no_cl"].names == ["NOCL"] and rows["in_cl_no_briefing"].names == ["NOBRIEF"]
    assert rows["mp_typo"].names == ["KILO12"] and rows["customer_blank"].count == 1
    assert rows["name_unresolved"].count == 1 and rows["cl_unreadable"].count == 1 and rows["cross_month_correction"].count == 1
    assert rows["task_description_blank"].names == ["THORPE (8)"]
    assert rows["names_masked"].level == "ok" and rows["names_masked"].count == 3
```

注意：上面 `budget_missing` 那兩行故意寫得含糊是錯的，**改成明確版本再放進檔案**：

```python
    assert rows["budget_missing"].level == "decide"
    assert rows["budget_missing"].names == []            # 五個案子裡有 Control List 的都填了 plan
```
（THORPE plan=14.5、NOBRIEF/NA/KILO12 plan=1、NOCL 沒有 Control List 所以不算。）

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/portfolio/test_rules.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 實作**

`src/portfolio/model/rules.py`：
```python
"""例外（本月要決定的事）與健康度。文字一律用 key，由 render 層查表；evidence 只含專案名與數字。"""
from __future__ import annotations
import datetime as dt
import re
from ..config import Config
from ..entities import Project, Issue, Exception_, HealthRow
from .load import DeptLoad

EXEC_LIKE = re.compile(r"EVT|DVT|POC", re.I)


def days_between(a: str, b: str) -> int:
    return (dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days


def _active(projects: list[Project]) -> list[Project]:
    return [p for p in projects if p.in_briefing and p.stage_cat != "Suspended"]


def milestones_passed(projects: list[Project], today: str) -> list[tuple[Project, str, str, int]]:
    out = []
    for p in _active(projects):
        mp, pvt = p.dates.get("mp"), p.dates.get("pvt")
        if mp and days_between(mp, today) < 0 and p.stage_cat not in ("MP", "Sustain / EOP"):
            out.append((p, "mp", mp, -days_between(mp, today)))
        elif pvt and days_between(pvt, today) < 0 and EXEC_LIKE.search(p.stage or ""):
            out.append((p, "pvt", pvt, -days_between(pvt, today)))
    return sorted(out, key=lambda x: -x[3])


def mp_slipped(projects: list[Project], min_days: int) -> list[tuple[Project, int]]:
    out = []
    for p in _active(projects):
        mp, mo = p.dates.get("mp"), p.dates.get("mp_orig")
        if mp and mo and days_between(mp, mo) > min_days:
            out.append((p, days_between(mp, mo)))
    return sorted(out, key=lambda x: -x[1])


def task_description_gaps(projects: list[Project]) -> list[tuple[str, list[int]]]:
    out = []
    for p in projects:
        months = sorted({t.month for t in p.tasks if t.side == "BU"})
        gaps = [m for m in months if not any(t.description for t in p.tasks if t.side == "BU" and t.month == m)]
        if gaps:
            out.append((p.name, gaps))
    return out


def build_exceptions(projects: list[Project], loads: list[DeptLoad], latest_month: int, cfg: Config, today: str) -> list[Exception_]:
    th = cfg.thresholds
    m = latest_month - 1
    passed = milestones_passed(projects, today)
    susp = [p for p in projects if p.in_briefing and p.stage_cat == "Suspended"]
    susp_fte = [(p, p.fte[m]) for p in susp if p.fte[m] > th["suspended_fte_min"]]
    cls = [p for p in projects if p.in_control_list]
    noplan = [p for p in cls if not p.has_plan]
    slipped = mp_slipped(projects, th["mp_slip_days"])
    spare = [d for d in loads if d.util[m] is not None and d.util[m] < th["spare_capacity_pct"]]
    full = len([d for d in loads if d.util[m] is not None]) - len(spare)
    ex = [
        Exception_(1, "milestones_passed", "; ".join(f"{p.name} {k.upper()} {d} (+{n}d, stage {p.stage})" for p, k, d, n in passed),
                   "milestones_passed", "briefing", [p.code for p, *_ in passed]),
        Exception_(2, "suspended_charging", ", ".join(f"{p.name} {v:.1f} FTE" for p, v in sorted(susp_fte, key=lambda x: -x[1])),
                   "suspended_charging", "briefing_summary", [p.code for p, _ in susp_fte]),
        Exception_(3, "budget_missing", ", ".join(sorted(p.name for p in noplan)) + f" | {len(cls) - len(noplan)} / {len(cls)}",
                   "budget_missing", "control_list_pva", [p.code for p in noplan]),
        Exception_(4, "mp_slipped", "; ".join(f"{p.name} {p.dates['mp_orig']} -> {p.dates['mp']} ({n}d)" for p, n in slipped),
                   "mp_slipped", "briefing_mp", [p.code for p, _ in slipped]),
        Exception_(5, "spare_capacity", ", ".join(f"{d.function} {d.dept_name} ({d.keyed_in[m]} people, {d.util[m]}%)" for d in sorted(spare, key=lambda d: d.util[m])),
                   "spare_capacity", "control_list_month", []),
    ]
    for e, n in zip(ex, (len(passed), len(susp), len(noplan), len(slipped), len(spare))):
        e.count = n
    ex[1].extra = {"pct": round(len(susp) * 100 / max(1, len([p for p in projects if p.in_briefing]))), "charging": len(susp_fte)}
    ex[4].ask_data = str(full)
    return ex


# (check, level, source_key, from_issues)
CHECKS = [
    ("budget_missing", "decide", "control_list", False), ("milestones_passed", "decide", "briefing", False),
    ("in_briefing_no_cl", "track", "cross", False), ("in_cl_no_briefing", "track", "cross", False),
    ("mp_typo", "track", "briefing", False), ("customer_blank", "track", "briefing", False),
    ("name_unresolved", "track", "cross", True), ("task_description_blank", "track", "control_list", False),
    ("briefing_stale", "track", "briefing", False), ("cl_unreadable", "track", "control_list", True),
    ("cl_format_drift", "track", "control_list", True), ("dept_denominator_inconsistent", "track", "control_list", True),
    ("cross_month_correction", "track", "snapshot", True), ("names_masked", "ok", "control_list", True),
]
DRIFT_CHECKS = {"cl_no_plan_vs_actual", "cl_pva_role_missing", "cl_no_task_sheet", "cl_no_month_sheets", "briefing_sheet_unreadable", "summary_block_without_ntd", "cl_multiple_codes"}


def build_health(projects: list[Project], loads: list[DeptLoad], issues: list[Issue], cfg: Config, today: str, snap_date: str) -> list[HealthRow]:
    th = cfg.thresholds
    active = _active(projects)
    blank = {"", "NA", "TBD", "N/A"}
    derived: dict[str, list[str]] = {
        "budget_missing": sorted(p.name for p in projects if p.in_control_list and not p.has_plan),
        "milestones_passed": [p.name for p, *_ in milestones_passed(projects, today)],
        "in_briefing_no_cl": sorted(p.name for p in active if not p.in_control_list),
        "in_cl_no_briefing": sorted(p.name for p in projects if p.in_control_list and not p.in_briefing),
        "mp_typo": [p.name for p, n in mp_slipped(projects, th["mp_typo_days"])],
        "customer_blank": sorted(p.name for p in active if p.customer.strip().upper() in blank),
        "task_description_blank": [f"{n} ({','.join(map(str, ms))})" for n, ms in task_description_gaps(projects)],
        "briefing_stale": [],   # 需要 BriefingRow.updated；由 cli 傳入的 issues 提供（見 Task 15）
    }
    rows = []
    for check, level, src, from_issues in CHECKS:
        if from_issues:
            if check == "cl_format_drift":
                hits = [i for i in issues if i.check in DRIFT_CHECKS]
            else:
                hits = [i for i in issues if i.check == check]
            if check == "names_masked":
                count = sum(int(i.detail) for i in hits if i.detail.isdigit()); names = []
            else:
                count, names = len(hits), [i.detail for i in hits]
        else:
            names = derived[check]; count = len(names)
        rows.append(HealthRow(level=level, check=check, label=check, count=count, names=names, source=src))
    return rows
```

`Exception_` 需要多三個欄位，回到 `src/portfolio/entities.py` 把它改成：
```python
@dataclass
class Exception_:
    rank: int
    title: str                  # key，render 層查表
    evidence: str               # 語言中立的資料片段
    ask: str                    # key
    source: str                 # key
    codes: list[str] = field(default_factory=list)
    count: int = 0
    ask_data: str = ""          # 塞進 ask 句子的數字
    extra: dict = field(default_factory=dict)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/portfolio/test_rules.py tests/portfolio/test_entities.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/model/rules.py src/portfolio/entities.py tests/portfolio/test_rules.py
git commit -m "feat(portfolio): decision exceptions and data health rules"
```

---

### Task 12: model/diff.py 與 model/snapshot.py

**Files:**
- Create: `src/portfolio/model/diff.py`, `src/portfolio/model/snapshot.py`, `tests/portfolio/test_snapshot.py`

**Interfaces:**
- Produces:
  - `build_snapshot(report_month, latest_month, snap_date, generated, projects, loads, capacity, exceptions, health, issues) -> dict`（全部 `asdict`，頂層 `meta`）
  - `write_snapshot(d: dict, dir: Path) -> Path`（寫 `<dir>/<report_month>/portfolio.json`）
  - `read_previous(dir: Path, report_month: str) -> dict | None`（找 `report_month` 之前最近一個月的目錄）
  - `cross_month_corrections(prev: dict | None, projects, latest_month, tol=0.05) -> list[Issue]`：對 `month < latest_month` 的 `fte` 逐案比較，差異超過 tol 產 `cross_month_correction`。

- [ ] **Step 1: 寫測試**

`tests/portfolio/test_snapshot.py`：
```python
import json
from src.portfolio.entities import Project, Exception_, HealthRow, Issue
from src.portfolio.model.load import DeptLoad
from src.portfolio.model.snapshot import build_snapshot, write_snapshot, read_previous
from src.portfolio.model.diff import cross_month_corrections


def test_write_and_read_previous(tmp_path):
    p = Project(code="BR1", name="A"); p.fte[6] = 17.0
    d = build_snapshot("202608", 7, "20260803", "2026-08-10", [p], [DeptLoad("D1", "x", "BSP")], [200] * 12,
                       [Exception_(1, "k", "e", "a", "s")], [HealthRow("ok", "c", "c", 0, [], "s")], [Issue("ok", "x", "1", "s")])
    path = write_snapshot(d, tmp_path)
    assert path == tmp_path / "202608" / "portfolio.json"
    assert json.loads(path.read_text())["projects"][0]["fte"][6] == 17.0
    assert read_previous(tmp_path, "202609")["meta"]["report_month"] == "202608"
    assert read_previous(tmp_path, "202608") is None


def test_cross_month_corrections():
    prev = {"meta": {"latest_month": 7}, "projects": [{"code": "BR1", "name": "A", "fte": [0] * 6 + [17.0, 0, 0, 0, 0, 0]}]}
    p = Project(code="BR1", name="A"); p.fte[6] = 3.7; p.fte[7] = 4.0
    issues = cross_month_corrections(prev, [p], 8)
    assert len(issues) == 1 and issues[0].check == "cross_month_correction" and "Jul" in issues[0].detail and "17.0" in issues[0].detail
    assert cross_month_corrections(None, [p], 8) == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/portfolio/test_snapshot.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 實作**

`src/portfolio/model/snapshot.py`：
```python
"""每月一份正規化 JSON。跨月比較與 render 都只吃這個檔。"""
from __future__ import annotations
import json
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
    out.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
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
```

`src/portfolio/model/diff.py`：
```python
"""上月快照 vs 本月：過去月份的數字若被改了，就是 PM 事後更正，要列出來。"""
from __future__ import annotations
from ..entities import Project, Issue, MONTHS


def cross_month_corrections(prev: dict | None, projects: list[Project], latest_month: int, tol: float = 0.05) -> list[Issue]:
    if not prev:
        return []
    old = {p["code"]: p for p in prev.get("projects", [])}
    out = []
    for p in projects:
        o = old.get(p.code)
        if not o:
            continue
        for m in range(min(latest_month - 1, prev["meta"].get("latest_month", 12))):
            a, b = o["fte"][m], p.fte[m]
            if abs(a - b) > tol:
                out.append(Issue("track", "cross_month_correction", f"{p.name} {MONTHS[m]} FTE {a:.1f} -> {b:.1f}", "snapshot", p.code))
    return out
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/portfolio/test_snapshot.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/model/diff.py src/portfolio/model/snapshot.py tests/portfolio/test_snapshot.py
git commit -m "feat(portfolio): monthly snapshot JSON and cross-month correction diff"
```

---

### Task 13: render/strings.py 與 render/css.py

**Files:**
- Create: `src/portfolio/render/strings.py`, `src/portfolio/render/css.py`, `tests/portfolio/test_strings.py`

**Interfaces:**
- Produces: `STRINGS: dict[str, dict[str, str | callable]]`，`t(lang, key, **kw) -> str`（缺 key 時 raise KeyError，不 fallback，避免漏翻譯靜默出現）；`CSS: str`。

- [ ] **Step 1: 寫測試**

`tests/portfolio/test_strings.py`：
```python
import re
import pytest
from src.portfolio.render.strings import STRINGS, t
from src.portfolio.render.css import CSS


def test_en_and_zh_have_same_keys():
    assert set(STRINGS["en"]) == set(STRINGS["zh"])


def test_format_and_missing_key():
    assert t("en", "ex_milestones_passed_title", n=6) == "6 milestones passed without a stage change"
    with pytest.raises(KeyError):
        t("en", "nope")


def test_no_middle_dots_or_all_caps_labels():
    for v in STRINGS["en"].values():
        if isinstance(v, str):
            assert "·" not in v and "→" not in v
            assert not re.fullmatch(r"[A-Z ]{6,}", v)


def test_css_tokens_present():
    for tok in ("#F5F6F4", "#22262A", "#3D5A80", "#5C8D89", "#E8590C"):
        assert tok.lower() in CSS.lower()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/portfolio/test_strings.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 實作**

`src/portfolio/render/strings.py`：
```python
"""UI 字串。英文為預設；zh 必須與 en 同 key。程式碼裡不得出現寫死的句子。"""
STRINGS = {
    "en": {
        "html_lang": "en", "doc_title": "BU10 Portfolio Review {ym}",
        "h1": "BU10 Portfolio Review",
        "intro": "Monthly. Exceptions first, evidence after. Manpower comes from the EIS control lists, schedules from the PM biweekly briefing.",
        "tb_report": "Report month", "tb_data": "Manpower data", "tb_data_v": "{start} to {end}, {n} projects",
        "tb_snap": "Briefing snapshot", "tb_snap_v": "{date} (revision {rev})", "tb_gen": "Generated", "tb_gen_v": "{date}, pipeline v{ver}",
        "s_decisions": "Decisions this month", "s_decisions_lead": "Ranked by urgency. Each item carries its evidence and its source. Orange appears only here and on fields that need a decision.",
        "decision_needed": "Decision needed:", "source": "Source:", "none": "none",
        "ex_milestones_passed_title": "{n} milestones passed without a stage change",
        "ex_milestones_passed_ask": "Ask the PMs to update the stage or explain the delay.",
        "ex_suspended_charging_title": "{n} projects suspended ({pct}% of the portfolio), {charging} still charging manpower",
        "ex_suspended_charging_ask": "Confirm whether to close them and where the charged manpower moves.",
        "ex_budget_missing_title": "{n} control lists have no budget plan; the Q4 forecast covers {covered} projects",
        "ex_budget_missing_ask": "Require the PMs to fill in budgets, otherwise the Q4 capacity discussion has no basis.",
        "ex_mp_slipped_title": "{n} projects moved MP more than {days} days past the original date",
        "ex_mp_slipped_ask": "Confirm the new dates; a gap over a year is probably a typo.",
        "ex_spare_capacity_title": "{n} departments are below {pct}% load, the only spare capacity left",
        "ex_spare_capacity_ask": "The other {full} departments sit at 100%; the reporting mechanism cannot show overload.",
        "src_briefing": "Briefing {date}", "src_briefing_summary": "Briefing stage column; Resource Summary",
        "src_control_list_pva": "Control List, Plan vs Actual sheet", "src_briefing_mp": "Briefing MP Date vs Original MP Date",
        "src_control_list_month": "Control List monthly sheets, allocated FTE over keyed-in headcount",
        "stage_rfq": "RFQ / RFI", "stage_poc": "POC", "stage_exec": "Execution", "stage_mp": "MP", "stage_sustain": "Sustain / EOP",
        "stage_suspended": "Suspended", "stage_fte": "Total FTE, {mon} (incl. FU)",
        "s_upcoming": "Milestones, next {weeks} weeks", "s_upcoming_lead": "Including those due in the past 7 days.",
        "col_date": "Date", "col_project": "Project", "col_customer": "Customer", "col_milestone": "Milestone", "col_stage": "Stage",
        "passed": "passed",
        "s_timeline": "Six-month timeline", "s_timeline_lead": "Weekly grid. Projects with a milestone in the window, or RFQ / RFI without dates. Suspended projects are not listed.",
        "no_dates": "{stage}, no dates yet", "legend_marks": "EVT (open square)  DVT (square)  PVT (triangle)  MP (circle)",
        "legend_late": "passed without a stage change", "legend_today": "dashed line = today",
        "s_capacity": "Manpower and capacity", "s_capacity_lead": "One chart, three facts: keyed-in BU headcount is the ceiling, actual manpower already runs along it, and the September to December budget covers only part of the portfolio.",
        "cap_budget_note": "Budget covers {covered} / {total} projects", "lg_capacity": "BU keyed-in headcount (ceiling)",
        "lg_actual": "BU RD + PM actual", "lg_budget": "BU RD + PM budget (dashed)", "lg_fu": "FU RD actual",
        "s_health": "Data health", "s_health_lead": "Every row affects how far the charts above can be trusted. Decide means the BU head has to act; track is handled by the report owner.",
        "col_level": "Level", "col_check": "Check", "col_count": "Count", "col_projects": "Projects", "col_source": "Source",
        "lv_decide": "decide", "lv_track": "track", "lv_ok": "ok",
        "hc_budget_missing": "Control list without a budget plan", "hc_milestones_passed": "Milestone passed, stage not advanced",
        "hc_in_briefing_no_cl": "In the briefing (not suspended) but no control list", "hc_in_cl_no_briefing": "Control list exists but not in the briefing",
        "hc_mp_typo": "MP more than 300 days from the original date, probably a typo", "hc_customer_blank": "Customer is NA, TBD or blank",
        "hc_name_unresolved": "Name could not be matched to a project code", "hc_task_description_blank": "BU tasks reported without a description (months)",
        "hc_briefing_stale": "Briefing row not updated for more than 60 days", "hc_cl_unreadable": "Control list file could not be read",
        "hc_cl_format_drift": "Control list sheet or column missing", "hc_dept_denominator_inconsistent": "Keyed-in headcount differs across files",
        "hc_cross_month_correction": "Past-month figures changed since last report", "hc_names_masked": "Person names masked in task text",
        "hs_control_list": "Control List", "hs_briefing": "Briefing", "hs_cross": "Cross-check", "hs_snapshot": "Previous snapshot",
        "s_appendix": "Project appendix", "s_appendix_lead": "Pick a project. Task lists are collapsed by default.",
        "ms_kickoff": "Kick-off", "ms_evt": "EVT", "ms_dvt": "DVT", "ms_pvt": "PVT", "ms_mp": "MP",
        "days_ahead": "in {d} days", "days_ago": "{d} days ago", "not_filled": "not filled", "not_in_briefing": "not in briefing",
        "pva_line": "budget {plan}{missing}, actual through {mon} {actual}", "pva_missing": " (not filled)",
        "no_control_list": "This project has no control list.", "s_tasks": "Task list",
        "task_summary": "{mon}: {bu} BU tasks, {fu} FU tasks, {fte} FTE", "col_side": "Side", "col_function": "Function", "col_dept": "Department", "col_fte": "FTE", "col_task": "Task",
        "expand": "expand", "collapse": "collapse",
        "foot_1": "FTE per person is capped at 1.0 by the reporting form, so overload cannot appear in these numbers.",
        "foot_2": "Department load uses keyed-in headcount as the denominator, not the official headcount.",
        "foot_3": "Budget coverage is stated wherever budget figures are used.",
    },
    "zh": {
        "html_lang": "zh-Hant", "doc_title": "BU10 專案組合檢討 {ym}",
        "h1": "BU10 專案組合檢討",
        "intro": "每月一次。先看例外，再看依據。人力來自 EIS Control List，時程來自 PM 雙週 Briefing。",
        "tb_report": "報告月份", "tb_data": "人力資料", "tb_data_v": "{start} 至 {end}，{n} 案",
        "tb_snap": "Briefing 快照", "tb_snap_v": "{date}（第 {rev} 版）", "tb_gen": "產生", "tb_gen_v": "{date}，管線 v{ver}",
        "s_decisions": "本月要決定的事", "s_decisions_lead": "依急迫排序，每條附證據與出處。橘色只出現在這一節與需要決定的欄位。",
        "decision_needed": "要決定：", "source": "來源：", "none": "無",
        "ex_milestones_passed_title": "{n} 案里程碑已過期，Stage 沒有往前推",
        "ex_milestones_passed_ask": "請 PM 更新 Stage 或說明延後原因。",
        "ex_suspended_charging_title": "{n} 案 Suspended（占組合 {pct}%），{charging} 案仍有人力掛帳",
        "ex_suspended_charging_ask": "確認是否結案，掛帳人力要轉到哪。",
        "ex_budget_missing_title": "{n} 份 Control List 未填 budget，Q4 預測只涵蓋 {covered} 案",
        "ex_budget_missing_ask": "要求 PM 補填，否則 Q4 產能討論沒有依據。",
        "ex_mp_slipped_title": "{n} 案 MP 較原訂延後超過 {days} 天",
        "ex_mp_slipped_ask": "確認新日期；差距超過一年很可能是打錯。",
        "ex_spare_capacity_title": "{n} 個部門負載低於 {pct}%，是僅存的可調度人力",
        "ex_spare_capacity_ask": "其餘 {full} 個部門已在 100%，填報機制看不到超載。",
        "src_briefing": "Briefing {date}", "src_briefing_summary": "Briefing Stage 欄；Resource Summary",
        "src_control_list_pva": "Control List「Plan vs. Actual」分頁", "src_briefing_mp": "Briefing MP Date 與 Original MP Date",
        "src_control_list_month": "Control List 月分頁，填入人力 ÷ 填報人數",
        "stage_rfq": "RFQ / RFI", "stage_poc": "POC", "stage_exec": "Execution", "stage_mp": "MP", "stage_sustain": "Sustain / EOP",
        "stage_suspended": "Suspended", "stage_fte": "{mon} 總人力 FTE（含 FU）",
        "s_upcoming": "未來 {weeks} 週的里程碑", "s_upcoming_lead": "含過去七天內已到期者。",
        "col_date": "日期", "col_project": "案子", "col_customer": "客戶", "col_milestone": "里程碑", "col_stage": "Stage",
        "passed": "已過",
        "s_timeline": "六個月時程", "s_timeline_lead": "週格線。只列里程碑落在視窗內，或 RFQ / RFI 尚無日期的案子；停案不列。",
        "no_dates": "{stage}，尚無日期", "legend_marks": "EVT（空方）  DVT（實方）  PVT（三角）  MP（圓）",
        "legend_late": "已過期未推進", "legend_today": "虛線 = 今天",
        "s_capacity": "人力與產能", "s_capacity_lead": "一張圖看三件事：BU 填報人數是天花板，實際人力已貼著它走，9 到 12 月的 budget 只涵蓋部分案子。",
        "cap_budget_note": "budget 涵蓋 {covered} / {total} 案", "lg_capacity": "BU 填報人數（天花板）",
        "lg_actual": "BU RD + PM 實際", "lg_budget": "BU RD + PM budget（虛線）", "lg_fu": "FU RD 實際",
        "s_health": "資料健康度", "s_health_lead": "每一項都影響上面圖表的可信度。「決定」要主管出面，「追蹤」由報表維護者處理。",
        "col_level": "層級", "col_check": "檢查項", "col_count": "案數", "col_projects": "影響的案子", "col_source": "來源",
        "lv_decide": "決定", "lv_track": "追蹤", "lv_ok": "正常",
        "hc_budget_missing": "Control List 未填 budget plan", "hc_milestones_passed": "里程碑已過但 Stage 未推進",
        "hc_in_briefing_no_cl": "在 Briefing（非停案）但沒有 Control List", "hc_in_cl_no_briefing": "有 Control List 但不在 Briefing",
        "hc_mp_typo": "MP 與原訂相差超過 300 天，疑為輸入錯誤", "hc_customer_blank": "Customer 為 NA、TBD 或空白",
        "hc_name_unresolved": "名稱對不到 PROJECTCODE", "hc_task_description_blank": "BU-Task 有人力列但描述空白（月份）",
        "hc_briefing_stale": "Briefing 該列超過 60 天未更新", "hc_cl_unreadable": "Control List 檔案無法讀取",
        "hc_cl_format_drift": "Control List 缺分頁或缺欄", "hc_dept_denominator_inconsistent": "填報人數跨檔不一致",
        "hc_cross_month_correction": "過去月份數字較上次報告有變", "hc_names_masked": "任務文字中被遮罩的人名",
        "hs_control_list": "Control List", "hs_briefing": "Briefing", "hs_cross": "交叉比對", "hs_snapshot": "上月快照",
        "s_appendix": "逐案附錄", "s_appendix_lead": "選一個案子。任務清單預設收合。",
        "ms_kickoff": "Kick-off", "ms_evt": "EVT", "ms_dvt": "DVT", "ms_pvt": "PVT", "ms_mp": "MP",
        "days_ahead": "{d} 天後", "days_ago": "{d} 天前", "not_filled": "未填", "not_in_briefing": "不在 Briefing",
        "pva_line": "budget {plan}{missing}，實際到 {mon} {actual}", "pva_missing": "（未填）",
        "no_control_list": "此案沒有 Control List。", "s_tasks": "任務清單",
        "task_summary": "{mon}：BU {bu} 項，FU {fu} 項，{fte} FTE", "col_side": "來源", "col_function": "Function", "col_dept": "部門", "col_fte": "FTE", "col_task": "任務",
        "expand": "展開", "collapse": "收合",
        "foot_1": "填報表單把每人 FTE 上限設在 1.0，超載不會出現在這些數字裡。",
        "foot_2": "部門負載的分母是填報人數，不是編制人數。",
        "foot_3": "凡用到 budget 的地方都標明涵蓋率。",
    },
}


def t(lang: str, key: str, **kw) -> str:
    v = STRINGS[lang][key]          # 缺 key 直接 KeyError，不 fallback
    return v.format(**kw) if kw else v
```

`src/portfolio/render/css.py`：
```python
CSS = """
:root{--paper:#F5F6F4;--ink:#22262A;--ink-2:#5B6167;--ink-3:#9AA3AB;--rule:#D5D9D6;--slate:#3D5A80;--slate-2:#A9B8CC;--teal:#5C8D89;--signal:#E8590C}
*{box-sizing:border-box}html{background:var(--paper)}
body{margin:0 auto;max-width:1280px;padding:36px 40px 80px;color:var(--ink);font:14px/1.55 -apple-system,"SF Pro Text","Segoe UI","Helvetica Neue","PingFang TC","Microsoft JhengHei","Noto Sans TC",sans-serif;font-variant-numeric:tabular-nums}
header{display:flex;justify-content:space-between;align-items:flex-start;gap:32px;padding-bottom:22px;border-bottom:1px solid var(--ink)}
h1{font-size:28px;font-weight:600;margin:0;line-height:1.2}header p{margin:8px 0 0;color:var(--ink-2);max-width:60ch}
.tb{border:1px solid var(--ink);font-size:12px;min-width:270px}.tb div{display:grid;grid-template-columns:112px 1fr;border-top:1px solid var(--rule)}.tb div:first-child{border-top:0}
.tb span{padding:5px 10px}.tb span:first-child{color:var(--ink-2);border-right:1px solid var(--rule)}
section{padding:30px 0 6px;border-bottom:1px solid var(--rule)}section:last-of-type{border-bottom:0}
h2{font-size:20px;font-weight:600;margin:0 0 4px}.lead{margin:0 0 18px;color:var(--ink-2);max-width:70ch}
ol.ex{list-style:none;margin:0;padding:0}ol.ex li{display:grid;grid-template-columns:44px 1fr;gap:12px;padding:14px 0;border-top:1px solid var(--rule)}ol.ex li:first-child{border-top:0}
ol.ex .n{font-size:28px;font-weight:600;color:var(--signal);line-height:1}ol.ex b{font-weight:600;font-size:15px}
ol.ex .body{color:var(--ink-2);margin:4px 0 0;max-width:110ch}ol.ex .ask{margin-top:6px}ol.ex .ask em{font-style:normal;color:var(--signal);font-weight:600}ol.ex .src{color:var(--ink-3);font-size:12px;margin-top:2px}
.two{display:grid;grid-template-columns:320px 1fr;gap:36px}@media(max-width:900px){.two{grid-template-columns:1fr}}
table{border-collapse:collapse;width:100%}th{text-align:left;font-weight:600;font-size:12px;color:var(--ink-2);padding:6px 8px 6px 0;border-bottom:1px solid var(--ink)}
td{padding:7px 8px 7px 0;border-bottom:1px solid var(--rule);vertical-align:top}td.num,th.num{text-align:right}
.sig{color:var(--signal);font-weight:600}.dim{color:var(--ink-3)}
.stages{display:flex;gap:28px;margin:0 0 22px;flex-wrap:wrap}.stages div b{display:block;font-size:24px;font-weight:600;line-height:1.1}.stages div span{font-size:12px;color:var(--ink-2)}
.tl{overflow-x:auto}.tl table td{padding:0 8px 0 0;height:32px;white-space:nowrap}
.legend{display:flex;gap:18px;font-size:12px;color:var(--ink-2);margin-top:10px;flex-wrap:wrap}.legend i{display:inline-block;width:10px;height:10px;margin-right:6px;vertical-align:-1px;background:var(--slate)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:8px;vertical-align:1px}.dot.d{background:var(--signal)}.dot.t{background:var(--slate)}.dot.o{background:var(--ink-3)}
select{font:14px inherit;padding:6px 10px;border:1px solid var(--ink);background:#fff;border-radius:0}select:focus{outline:2px solid var(--slate);outline-offset:2px}
.ms{display:grid;grid-template-columns:repeat(5,1fr);margin:16px 0 20px;border-top:1px solid var(--ink)}.ms div{padding:10px 0;border-right:1px solid var(--rule)}.ms div:last-child{border-right:0}
.ms b{display:block;font-size:20px;font-weight:600}.ms small{color:var(--ink-2)}
details{border-top:1px solid var(--rule)}details summary{cursor:pointer;padding:10px 0;list-style:none;display:flex;justify-content:space-between}
details summary::-webkit-details-marker{display:none}details summary:focus-visible{outline:2px solid var(--slate)}
details summary::after{content:attr(data-expand);color:var(--slate);font-size:12px}details[open] summary::after{content:attr(data-collapse)}
details td.desc{white-space:pre-line;max-width:70ch;color:var(--ink-2);font-size:13px}
.pva{display:grid;grid-template-columns:1fr 1fr 1fr;gap:24px}.pva h4{margin:0 0 4px;font-size:13px;font-weight:600}.pva .s{font-size:12px;color:var(--ink-2)}
footer{color:var(--ink-3);font-size:12px;margin-top:30px;max-width:80ch}footer p{margin:4px 0}
svg text{font-family:inherit}
@media (prefers-reduced-motion: reduce){*{transition:none!important}}
"""
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/portfolio/test_strings.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/render/strings.py src/portfolio/render/css.py tests/portfolio/test_strings.py
git commit -m "feat(portfolio): en/zh string table and design tokens"
```

---

### Task 14: render/charts.py 三張 SVG

**Files:**
- Create: `src/portfolio/render/charts.py`, `tests/portfolio/test_charts.py`

**Interfaces:**
- Consumes: snapshot dict 裡的 `projects`（純 dict）、`capacity`
- Produces（都回傳 SVG 字串，純 Python 計算，不靠瀏覽器 JS）：
  - `timeline_svg(projects: list[dict], today: str, start: str, months: int, late_codes: set[str], lang: str) -> tuple[str, str]`：回 `(header_svg, rows_html)`，rows_html 是 `<tr>` 片段（案名、客戶、stage、該列 svg）。
  - `capacity_svg(projects, capacity: list[int], latest_month: int, lang) -> str`
  - `pva_svg(pva: dict, role: str, latest_month: int) -> str`
  - `week_gridlines(start, months, width) -> str`（獨立好測）

- [ ] **Step 1: 寫測試**

`tests/portfolio/test_charts.py`：
```python
from dataclasses import asdict
from src.portfolio.entities import Project, PlanVsActual
from src.portfolio.render.charts import timeline_svg, capacity_svg, pva_svg, week_gridlines


def p(name, stage, cat, **dates):
    x = Project(code="BR" + name, name=name, stage=stage, stage_cat=cat, in_briefing=True); x.dates.update(dates)
    return asdict(x)


def test_week_gridlines_count():
    svg = week_gridlines("2026-09-01", 6, 590)
    assert svg.count('stroke="#e6e9e6"') == 26          # 2026-09-07 起每週一，到 2027-02-22
    assert svg.count('stroke="#c4c9c5"') == 5           # 10/1 11/1 12/1 1/1 2/1


def test_timeline_rows_selection_and_late_marker():
    ps = [p("Foxtrot14", "DVT2", "Execution", pvt="2026-09-08", mp="2026-09-29"), p("Q11", "suspended", "Suspended", evt="2026-09-29"),
          p("TOMY", "RFQ", "RFQ / RFI"), p("OLD", "Sustain", "Sustain / EOP", mp="2024-01-01")]
    head, rows = timeline_svg(ps, "2026-09-12", "2026-09-01", 6, {"BRFoxtrot14"}, "en")
    assert "2026-09" in head and "2027-02" in head
    assert "Foxtrot14" in rows and "Q11" not in rows and "OLD" not in rows
    assert "TOMY" in rows and "no dates yet" in rows
    assert 'fill="#E8590C"' in rows                      # late marker for Foxtrot14 PVT


def test_capacity_svg_has_series_and_budget_note():
    x = Project(code="BR1", name="A", in_control_list=True, has_plan=True)
    x.pva = {"BU RD": PlanVsActual("BU RD", plan=[10] * 12, actual=[9] * 8 + [0] * 4), "PM": PlanVsActual("PM", plan=[1] * 12, actual=[1] * 8 + [0] * 4),
             "FU RD": PlanVsActual("FU RD", actual=[2] * 8 + [0] * 4)}
    svg = capacity_svg([asdict(x)], [12] * 12, 8, "en")
    assert svg.count("<polyline") == 4 and "Budget covers 1 / 1" in svg


def test_pva_svg_bars():
    svg = pva_svg({"BU RD": asdict(PlanVsActual("BU RD", plan=[1] * 12, actual=[2] * 8 + [0] * 4))}, "BU RD", 8)
    assert svg.count("<rect") == 20                      # 12 plan + 8 actual
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/portfolio/test_charts.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 實作**

`src/portfolio/render/charts.py`：
```python
"""純 Python 產 SVG。座標與樣式都在這裡，page.py 只負責擺位。"""
from __future__ import annotations
import datetime as dt
from html import escape
from ..entities import MONTHS
from .strings import t

SLATE, SLATE2, TEAL, INK, INK2, INK3, SIGNAL, GRID, GRID2 = "#3D5A80", "#A9B8CC", "#5C8D89", "#22262A", "#5B6167", "#9AA3AB", "#E8590C", "#e6e9e6", "#c4c9c5"
TL_W, ROW_H = 590, 32


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _add_months(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.month - 1 + n, 12)
    return d.replace(year=d.year + y, month=m + 1, day=1)


def week_gridlines(start: str, months: int, width: int) -> str:
    t0, t1 = _d(start), _add_months(_d(start), months)
    x = lambda d: (d - t0).days / (t1 - t0).days * width
    out, d = [], t0
    while d < t1:
        if d.weekday() == 0:
            out.append(f'<line x1="{x(d):.1f}" x2="{x(d):.1f}" y1="0" y2="{ROW_H}" stroke="{GRID}"/>')
        if d.day == 1 and d != t0:
            out.append(f'<line x1="{x(d):.1f}" x2="{x(d):.1f}" y1="0" y2="{ROW_H}" stroke="{GRID2}"/>')
        d += dt.timedelta(days=1)
    return "".join(out)


def _marker(kind: str, px: float, c: str) -> str:
    return {"evt": f'<rect x="{px-4:.1f}" y="12" width="8" height="8" fill="#fff" stroke="{c}" stroke-width="1.5"/>',
            "dvt": f'<rect x="{px-4:.1f}" y="12" width="8" height="8" fill="{c}"/>',
            "pvt": f'<polygon points="{px:.1f},11 {px+5:.1f},20 {px-5:.1f},20" fill="{c}"/>',
            "mp": f'<circle cx="{px:.1f}" cy="16" r="5" fill="{c}"/>'}[kind]


def timeline_svg(projects: list[dict], today: str, start: str, months: int, late_codes: set[str], lang: str) -> tuple[str, str]:
    t0, t1 = _d(start), _add_months(_d(start), months)
    x = lambda s: (_d(s) - t0).days / (t1 - t0).days * TL_W
    in_win = lambda s: bool(s) and t0 <= _d(s) < t1
    grid = week_gridlines(start, months, TL_W)
    head, d = [], t0
    while d < t1:
        head.append(f'<text x="{x(d.isoformat())+4:.1f}" y="12" font-size="11" fill="{INK2}">{d.strftime("%Y-%m")}</text>'); d = _add_months(d, 1)
    rows = [p for p in projects if p["in_briefing"] and p["stage_cat"] != "Suspended"
            and (any(in_win(p["dates"][k]) for k in ("evt", "dvt", "pvt", "mp")) or (p["stage_cat"] == "RFQ / RFI" and not p["dates"]["mp"]))]
    rows.sort(key=lambda p: p["dates"]["mp"] or p["dates"]["pvt"] or p["dates"]["dvt"] or p["dates"]["evt"] or "9")
    out = []
    for p in rows:
        ms = [k for k in ("kickoff", "evt", "dvt", "pvt", "mp") if p["dates"][k]]
        s = grid + f'<line x1="{x(today):.1f}" x2="{x(today):.1f}" y1="0" y2="{ROW_H}" stroke="{INK}" stroke-dasharray="2 3"/>'
        for a, b in zip(ms, ms[1:]):
            xa, xb = max(0, x(p["dates"][a])), min(TL_W, x(p["dates"][b]))
            if xb > xa:
                s += f'<rect x="{xa:.1f}" y="14" width="{xb-xa:.1f}" height="4" fill="{SLATE}" opacity=".3"/>'
        for k in ms:
            if k == "kickoff" or not in_win(p["dates"][k]):
                continue
            px = x(p["dates"][k]); late = p["code"] in late_codes and _d(p["dates"][k]) < _d(today)
            c = SIGNAL if late else SLATE; right = px > TL_W - 70
            s += _marker(k, px, c) + (f'<text x="{px + (-9 if right else 9):.1f}" y="20" font-size="11" text-anchor="{"end" if right else "start"}" fill="{c}">'
                                      f'{k.upper()} {p["dates"][k][5:].replace("-", "/")}</text>')
        if not ms:
            s += f'<text x="{x(today)+8:.1f}" y="20" font-size="11" fill="{INK3}">{escape(t(lang, "no_dates", stage=p["stage"]))}</text>'
        out.append(f'<tr><td><b>{escape(p["name"])}</b></td><td>{escape(p["customer"])}</td><td>{escape(p["stage"])}</td>'
                   f'<td><svg width="{TL_W}" height="{ROW_H}">{s}</svg></td></tr>')
    return f'<svg width="{TL_W}" height="16">{"".join(head)}</svg>', "".join(out)


def _sum(projects: list[dict], role: str, field: str, n: int = 12, only_plan: bool = False) -> list[float]:
    ps = [p for p in projects if p.get("pva") and (p["has_plan"] or not only_plan)]
    return [sum((p["pva"].get(role) or {}).get(field, [0] * 12)[i] for p in ps) for i in range(n)]


def capacity_svg(projects: list[dict], capacity: list[int], latest_month: int, lang: str) -> str:
    cl = [p for p in projects if p.get("pva")]; wp = [p for p in cl if p["has_plan"]]
    act = [a + b for a, b in zip(_sum(cl, "BU RD", "actual", latest_month), _sum(cl, "PM", "actual", latest_month))]
    fu = _sum(cl, "FU RD", "actual", latest_month)
    plan = [a + b for a, b in zip(_sum(wp, "BU RD", "plan", only_plan=True), _sum(wp, "PM", "plan", only_plan=True))]
    W, H, pl, pb = 1100, 300, 40, 30; cw = (W - pl - 20) / 12
    mx = max(act + plan + capacity + [1]) * 1.12
    y = lambda v: H - pb - v / mx * (H - pb - 20); X = lambda i: pl + i * cw + cw / 2
    line = lambda arr, c, dash, w: f'<polyline fill="none" stroke="{c}" stroke-width="{w}" {f"stroke-dasharray=\"{dash}\"" if dash else ""} points="{" ".join(f"{X(i):.1f},{y(v):.1f}" for i, v in enumerate(arr))}"/>'
    ends = lambda arr, c, dy: "".join(f'<text x="{X(i):.1f}" y="{y(v)+dy:.1f}" font-size="11" text-anchor="middle" fill="{c}">{v:.0f}</text>' for i, v in enumerate(arr) if i in (0, len(arr) - 1))
    grid = "".join(f'<line x1="{pl}" x2="{W-10}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{GRID}"/><text x="{pl-6}" y="{y(v)+4:.1f}" font-size="11" text-anchor="end" fill="{INK3}">{v}</text>' for v in (50, 100, 150, 200, 250) if v < mx)
    fut = f'<rect x="{X(latest_month) - cw/2:.1f}" y="10" width="{cw*(12-latest_month):.1f}" height="{H-pb-10}" fill="#eceeeb"/>' if latest_month < 12 else ""
    note = f'<text x="{X(min(11, latest_month + 1)):.1f}" y="26" font-size="11" text-anchor="middle" fill="{INK2}">{escape(t(lang, "cap_budget_note", covered=len(wp), total=len(cl)))}</text>'
    axis = "".join(f'<text x="{X(i):.1f}" y="{H-8}" font-size="12" text-anchor="middle" fill="{INK2}">{m}</text>' for i, m in enumerate(MONTHS))
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" role="img">{grid}{fut}{note}'
            f'{line(capacity, INK, "5 4", 1.5)}{line(act, SLATE, None, 2.5)}{line(plan, SLATE, "3 4", 1.5)}{line(fu, TEAL, None, 2)}'
            f'{ends(capacity, INK, -9)}{ends(act, SLATE, 18)}{ends(fu, TEAL, -8)}{axis}</svg>')


def pva_svg(pva: dict, role: str, latest_month: int) -> str:
    v = pva.get(role) or {}; plan, act = v.get("plan", [0] * 12), v.get("actual", [0] * 12)
    W, H, pl = 360, 120, 10; cw = (W - pl) / 12; mx = max(plan + act + [0.1]); y = lambda q: H - 20 - q / mx * (H - 30)
    c = TEAL if role == "FU RD" else SLATE; out = []
    for i, m in enumerate(MONTHS):
        out.append(f'<rect x="{pl+i*cw+3:.1f}" y="{y(plan[i]):.1f}" width="{cw*0.35:.1f}" height="{H-20-y(plan[i]):.1f}" fill="{SLATE2}"/>')
        if i < latest_month:
            out.append(f'<rect x="{pl+i*cw+3+cw*0.38:.1f}" y="{y(act[i]):.1f}" width="{cw*0.45:.1f}" height="{H-20-y(act[i]):.1f}" fill="{c}"/>')
        out.append(f'<text x="{pl+i*cw+cw/2:.1f}" y="{H-6}" font-size="10" text-anchor="middle" fill="{INK3}">{m}</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img">{"".join(out)}</svg>'
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/portfolio/test_charts.py -v`
Expected: 4 PASS（若週格線數量與 26 / 5 差 1，用實際日曆核對後修正測試期望值，不改演算法）

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/render/charts.py tests/portfolio/test_charts.py
git commit -m "feat(portfolio): timeline, capacity and plan-vs-actual SVG charts"
```

---

### Task 15: render/page.py 與 render/pii.py

**Files:**
- Create: `src/portfolio/render/page.py`, `src/portfolio/render/pii.py`, `tests/portfolio/test_page.py`

**Interfaces:**
- Consumes: snapshot dict、`t`、`CSS`、charts
- Produces: `render_page(snap: dict, lang: str, today: str, cfg_thresholds: dict) -> str`；`find_pii(html: str, forbidden: set[str] = frozenset()) -> list[str]`（回傳命中的片段；`LA\d{7}`、`[A-Za-z]+\([一-鿿]{2,4}\)`、forbidden 中的字串）。

附錄用少量 inline JS（下拉切換 `display`），所有專案的附錄 HTML 都預先產生在頁面裡，JS 只做顯示切換；沒有 JS 時全部展開仍可讀。

- [ ] **Step 1: 寫測試**

`tests/portfolio/test_page.py`：
```python
import re
from dataclasses import asdict
from src.portfolio.entities import Project, PlanVsActual, Task, Exception_, HealthRow, Issue
from src.portfolio.model.load import DeptLoad
from src.portfolio.model.snapshot import build_snapshot
from src.portfolio.render.page import render_page
from src.portfolio.render.pii import find_pii

TH = {"mp_slip_days": 60, "mp_typo_days": 300, "spare_capacity_pct": 85, "suspended_fte_min": 0.05, "briefing_stale_days": 60, "upcoming_weeks": 8, "timeline_months": 6}


def snap():
    a = Project(code="BR1", name="THORPE", stage="PVT", stage_cat="Execution", customer="Trimble", in_briefing=True, in_control_list=True, has_plan=True)
    a.dates.update({"kickoff": "2024-04-02", "pvt": "2026-03-21", "mp": "2026-07-31", "mp_orig": "2025-10-13"}); a.fte[7] = 12.4
    a.pva = {"BU RD": PlanVsActual("BU RD", plan=[14.5] * 12, actual=[18] * 8 + [0] * 4)}
    a.tasks = [Task(8, "BU", "BSP", "研發三部", 3.1, "SW release"), Task(8, "FU", "SQA", "軟體三處", 0.6, "SQA")]
    b = Project(code="BR2", name="TOMY", stage="RFQ", stage_cat="RFQ / RFI", customer="Trimble", in_briefing=True)
    ex = [Exception_(1, "milestones_passed", "THORPE MP 2026-07-31 (+43d, stage PVT)", "milestones_passed", "briefing", ["BR1"], count=1),
          Exception_(2, "suspended_charging", "", "suspended_charging", "briefing_summary", [], count=0, extra={"pct": 0, "charging": 0}),
          Exception_(3, "budget_missing", " | 1 / 1", "budget_missing", "control_list_pva", [], count=0),
          Exception_(4, "mp_slipped", "THORPE 2025-10-13 -> 2026-07-31 (291d)", "mp_slipped", "briefing_mp", ["BR1"], count=1),
          Exception_(5, "spare_capacity", "", "spare_capacity", "control_list_month", [], count=0, ask_data="2")]
    hl = [HealthRow("decide", "budget_missing", "budget_missing", 0, [], "control_list"), HealthRow("ok", "names_masked", "names_masked", 3, [], "control_list")]
    return build_snapshot("202609", 8, "20260907", "2026-09-12", [a, b], [DeptLoad("D", "x", "BSP", keyed_in=[5] * 12, util=[100] * 12)], [207] * 12, ex, hl, [])


def test_page_sections_and_strings():
    html = render_page(snap(), "en", "2026-09-12", TH)
    for s in ("BU10 Portfolio Review", "Decisions this month", "1 milestones passed", "Decision needed:", "Milestones, next 8 weeks",
              "Six-month timeline", "Manpower and capacity", "Data health", "Project appendix", "Aug: 1 BU tasks, 1 FU tasks, 3.7 FTE"):
        assert s in html, s
    assert "TOMY" in html and "no dates yet" in html
    assert html.count("<details") == 1 and "<details open" not in html
    assert "·" not in html and "→" not in html
    assert 'lang="en"' in html


def test_zh_renders_without_missing_keys():
    html = render_page(snap(), "zh", "2026-09-12", TH)
    assert "本月要決定的事" in html and 'lang="zh-Hant"' in html


def test_find_pii():
    assert find_pii("ok LA0801557 x") == ["LA0801557"]
    assert find_pii("Jiayu Ong(翁家瑜)") == ["Ong(翁家瑜)"]
    assert find_pii("nothing here", {"SECRET"}) == []
    assert find_pii("by SECRET person", {"SECRET"}) == ["SECRET"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/portfolio/test_page.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 實作**

`src/portfolio/render/pii.py`：
```python
"""輸出前的負向檢查。找到任何一項就不准寫出 HTML。"""
from __future__ import annotations
import re

P_EMPID = re.compile(r"\bLA\d{7}\b")
P_LATIN_CJK = re.compile(r"[A-Za-z]+\([一-鿿]{2,4}\)")


def find_pii(html: str, forbidden: set[str] = frozenset()) -> list[str]:
    hits = P_EMPID.findall(html) + P_LATIN_CJK.findall(html)
    hits += [f for f in sorted(forbidden) if f and f in html]
    return hits
```

`src/portfolio/render/page.py`：
```python
"""組頁。所有文字走 t()，所有數字來自 snapshot dict。"""
from __future__ import annotations
import datetime as dt
from html import escape as e
from ..entities import MONTHS
from .css import CSS
from .charts import timeline_svg, capacity_svg, pva_svg
from .strings import t

STAGE_KEYS = [("RFQ / RFI", "stage_rfq"), ("POC", "stage_poc"), ("Execution", "stage_exec"), ("MP", "stage_mp"), ("Sustain / EOP", "stage_sustain"), ("Suspended", "stage_suspended")]


def _days(a: str, b: str) -> int:
    return (dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days


def _title_block(m: dict, lang: str, n_cl: int, latest_month: int) -> str:
    ym = f"{m['report_month'][:4]}-{m['report_month'][4:]}"
    rows = [(t(lang, "tb_report"), ym), (t(lang, "tb_data"), t(lang, "tb_data_v", start=f"{m['report_month'][:4]}-01", end=f"{m['report_month'][:4]}-{latest_month:02d}", n=n_cl)),
            (t(lang, "tb_snap"), t(lang, "tb_snap_v", date=f"{m['snap_date'][:4]}-{m['snap_date'][4:6]}-{m['snap_date'][6:]}", rev=m.get("snap_rev", "?"))),
            (t(lang, "tb_gen"), t(lang, "tb_gen_v", date=m["generated"], ver=m["version"]))]
    return '<div class="tb">' + "".join(f"<div><span>{e(k)}</span><span>{e(v)}</span></div>" for k, v in rows) + "</div>"


def _exceptions(snap: dict, lang: str, th: dict) -> str:
    out = []
    for x in snap["exceptions"]:
        k = x["title"]; kw = {"n": x["count"], "days": th["mp_slip_days"], "pct": th["spare_capacity_pct"], "full": x.get("ask_data", "")}
        kw.update(x.get("extra", {}))
        if k == "budget_missing":
            ev, _, cov = x["evidence"].rpartition(" | "); kw["covered"] = cov.split(" / ")[0] if cov else "0"; x = {**x, "evidence": ev}
        src_kw = {"date": f"{snap['meta']['snap_date'][4:6]}/{snap['meta']['snap_date'][6:]}"}
        out.append(f'<li><div class="n">{x["rank"]}</div><div><b>{e(t(lang, f"ex_{k}_title", **kw))}</b>'
                   f'<div class="body">{e(x["evidence"]) or e(t(lang, "none"))}</div>'
                   f'<div class="ask"><em>{e(t(lang, "decision_needed"))}</em> {e(t(lang, f"ex_{k}_ask", **kw))}</div>'
                   f'<div class="src">{e(t(lang, "source"))} {e(t(lang, f"src_{x["source"]}", **src_kw))}</div></div></li>')
    return f'<ol class="ex">{"".join(out)}</ol>'


def _stage_strip(snap: dict, lang: str, latest_month: int) -> str:
    ps = [p for p in snap["projects"] if p["in_briefing"]]
    cells = [f'<div><b class="{"sig" if cat == "Suspended" else ""}">{sum(1 for p in ps if p["stage_cat"] == cat)}</b><span>{e(t(lang, key))}</span></div>' for cat, key in STAGE_KEYS]
    total = sum(p["fte"][latest_month - 1] for p in snap["projects"])
    cells.append(f'<div><b>{total:.1f}</b><span>{e(t(lang, "stage_fte", mon=MONTHS[latest_month - 1]))}</span></div>')
    return f'<div class="stages">{"".join(cells)}</div>'


def _upcoming(snap: dict, lang: str, today: str, weeks: int) -> str:
    rows = []
    for p in snap["projects"]:
        if not p["in_briefing"] or p["stage_cat"] == "Suspended":
            continue
        for k in ("evt", "dvt", "pvt", "mp"):
            d = p["dates"][k]
            if d and -7 <= _days(d, today) <= weeks * 7:
                rows.append((d, p["name"], p["customer"], k.upper(), _days(d, today) < 0))
    rows.sort()
    body = "".join(f'<tr><td>{d[5:].replace("-", "/")}{" <span class=sig>" + e(t(lang, "passed")) + "</span>" if late else ""}</td><td><b>{e(n)}</b></td><td>{e(c)}</td><td>{m}</td></tr>' for d, n, c, m, late in rows)
    return (f'<table><thead><tr><th>{e(t(lang, "col_date"))}</th><th>{e(t(lang, "col_project"))}</th><th>{e(t(lang, "col_customer"))}</th><th>{e(t(lang, "col_milestone"))}</th></tr></thead>'
            f'<tbody>{body}</tbody></table>')


def _health(snap: dict, lang: str) -> str:
    rows = "".join(f'<tr><td><span class="dot {h["level"][0]}"></span>{e(t(lang, "lv_" + h["level"]))}</td><td>{e(t(lang, "hc_" + h["check"]))}</td>'
                   f'<td class="num {"sig" if h["level"] == "decide" and h["count"] else ""}">{h["count"]}</td>'
                   f'<td style="white-space:normal;max-width:60ch" class="dim">{e(", ".join(h["names"]))}</td><td class="dim">{e(t(lang, "hs_" + h["source"]))}</td></tr>' for h in snap["health"])
    return (f'<table><thead><tr><th>{e(t(lang, "col_level"))}</th><th>{e(t(lang, "col_check"))}</th><th class="num">{e(t(lang, "col_count"))}</th>'
            f'<th>{e(t(lang, "col_projects"))}</th><th>{e(t(lang, "col_source"))}</th></tr></thead><tbody>{rows}</tbody></table>')


def _appendix_one(p: dict, lang: str, today: str, latest_month: int, i: int) -> str:
    ms = []
    for k in ("kickoff", "evt", "dvt", "pvt", "mp"):
        d = p["dates"][k]
        sub = (t(lang, "days_ahead", d=_days(d, today)) if _days(d, today) >= 0 else t(lang, "days_ago", d=-_days(d, today))) if d else (t(lang, "not_filled") if p["in_briefing"] else t(lang, "not_in_briefing"))
        ms.append(f'<div><small>{e(t(lang, "ms_" + k))}</small><b>{e(d or "–")}</b><small>{e(sub)}</small></div>')
    if not p.get("pva"):
        body = f'<p class="dim">{e(t(lang, "no_control_list"))}</p>'
    else:
        cards = []
        for role in ("BU RD", "FU RD", "PM"):
            v = p["pva"].get(role) or {"plan": [0] * 12, "actual": [0] * 12}
            plan, act = sum(v["plan"]), sum(v["actual"][:latest_month])
            cards.append(f'<div><h4>{role}</h4><div class="s">{e(t(lang, "pva_line", plan=f"{plan:.1f}", missing="" if plan else t(lang, "pva_missing"), mon=MONTHS[latest_month - 1], actual=f"{act:.1f}"))}</div>{pva_svg(p["pva"], role, latest_month)}</div>')
        by_m: dict[int, list] = {}
        for task in p["tasks"]:
            by_m.setdefault(task["month"], []).append(task)
        dets = []
        for m in sorted(by_m, reverse=True):
            ts = sorted(by_m[m], key=lambda x: -x["fte"]); bu = sum(1 for x in ts if x["side"] == "BU"); fu = len(ts) - bu
            trs = "".join(f'<tr><td>{x["side"]}</td><td>{e(x["function"])}</td><td>{e(x["dept"])}</td><td class="num">{x["fte"]:.2f}</td><td class="desc">{e(x["description"])}</td></tr>' for x in ts)
            dets.append(f'<details><summary data-expand="{e(t(lang, "expand"))}" data-collapse="{e(t(lang, "collapse"))}"><span>{e(t(lang, "task_summary", mon=MONTHS[m - 1], bu=bu, fu=fu, fte=f"{sum(x["fte"] for x in ts):.1f}"))}</span></summary>'
                        f'<table><thead><tr><th>{e(t(lang, "col_side"))}</th><th>{e(t(lang, "col_function"))}</th><th>{e(t(lang, "col_dept"))}</th><th class="num">{e(t(lang, "col_fte"))}</th><th>{e(t(lang, "col_task"))}</th></tr></thead><tbody>{trs}</tbody></table></details>')
        body = f'<div class="pva">{"".join(cards)}</div><h3 style="font-size:15px;margin:26px 0 6px">{e(t(lang, "s_tasks"))}</h3>{"".join(dets)}'
    meta = "  ".join(x for x in (p["code"] if not p["code"].startswith("NAME:") else "", p["customer"], p["product"], p["group"]) if x)
    return f'<div class="proj" data-idx="{i}"><div class="dim">{e(meta)}</div><div class="ms">{"".join(ms)}</div>{body}</div>'


def render_page(snap: dict, lang: str, today: str, th: dict) -> str:
    m = snap["meta"]; lm = m["latest_month"]
    ps = snap["projects"]; cl = [p for p in ps if p["in_control_list"]]
    late = {c for x in snap["exceptions"] if x["title"] == "milestones_passed" for c in x["codes"]}
    start = f"{today[:7]}-01"
    head_svg, rows = timeline_svg(ps, today, start, th["timeline_months"], late, lang)
    order = sorted(range(len(ps)), key=lambda i: (0 if ps[i]["in_briefing"] and ps[i]["stage_cat"] not in ("Suspended", "Sustain / EOP") else 1, -ps[i]["fte"][lm - 1]))
    options = "".join(f'<option value="{i}">{e(ps[i]["name"])}{", " + e(ps[i]["stage"]) if ps[i]["stage"] else ""}</option>' for i in order)
    appendix = "".join(_appendix_one(ps[i], lang, today, lm, i) for i in order)
    ym = f"{m['report_month'][:4]}-{m['report_month'][4:]}"
    return f"""<!DOCTYPE html><html lang="{t(lang, "html_lang")}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(t(lang, "doc_title", ym=ym))}</title><style>{CSS}</style></head><body>
<header><div><h1>{e(t(lang, "h1"))}</h1><p>{e(t(lang, "intro"))}</p></div>{_title_block(m, lang, len(cl), lm)}</header>
<section><h2>{e(t(lang, "s_decisions"))}</h2><p class="lead">{e(t(lang, "s_decisions_lead"))}</p>{_exceptions(snap, lang, th)}</section>
<section>{_stage_strip(snap, lang, lm)}<div class="two"><div><h2>{e(t(lang, "s_upcoming", weeks=th["upcoming_weeks"]))}</h2><p class="lead">{e(t(lang, "s_upcoming_lead"))}</p>{_upcoming(snap, lang, today, th["upcoming_weeks"])}</div>
<div><h2>{e(t(lang, "s_timeline"))}</h2><p class="lead">{e(t(lang, "s_timeline_lead"))}</p><div class="tl"><table><thead><tr><th>{e(t(lang, "col_project"))}</th><th>{e(t(lang, "col_customer"))}</th><th>{e(t(lang, "col_stage"))}</th><th>{head_svg}</th></tr></thead><tbody>{rows}</tbody></table>
<div class="legend"><span>{e(t(lang, "legend_marks"))}</span><span><i style="background:#E8590C"></i>{e(t(lang, "legend_late"))}</span><span>{e(t(lang, "legend_today"))}</span></div></div></div></div></section>
<section><h2>{e(t(lang, "s_capacity"))}</h2><p class="lead">{e(t(lang, "s_capacity_lead"))}</p>{capacity_svg(ps, snap["capacity"], lm, lang)}
<div class="legend"><span><i style="background:#22262A"></i>{e(t(lang, "lg_capacity"))}</span><span><i></i>{e(t(lang, "lg_actual"))}</span><span><i style="background:#A9B8CC"></i>{e(t(lang, "lg_budget"))}</span><span><i style="background:#5C8D89"></i>{e(t(lang, "lg_fu"))}</span></div></section>
<section><h2>{e(t(lang, "s_health"))}</h2><p class="lead">{e(t(lang, "s_health_lead"))}</p>{_health(snap, lang)}</section>
<section><h2>{e(t(lang, "s_appendix"))}</h2><p class="lead">{e(t(lang, "s_appendix_lead"))}</p><select id="pick">{options}</select><div id="projects">{appendix}</div></section>
<footer><p>{e(t(lang, "foot_1"))}</p><p>{e(t(lang, "foot_2"))}</p><p>{e(t(lang, "foot_3"))}</p></footer>
<script>(function(){{var s=document.getElementById('pick'),ps=document.querySelectorAll('#projects .proj');function show(i){{ps.forEach(function(p){{p.style.display=p.dataset.idx===String(i)?'':'none';}});}}s.addEventListener('change',function(){{show(s.value);}});show(s.value);}})();</script>
</body></html>"""
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python -m pytest tests/portfolio/test_page.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/render/page.py src/portfolio/render/pii.py tests/portfolio/test_page.py
git commit -m "feat(portfolio): page assembly and PII negative check"
```

---

### Task 16: cli.py、真實資料端到端、視覺驗證、文件

**Files:**
- Create: `src/portfolio/cli.py`, `tests/portfolio/test_cli.py`
- Modify: `AGENTS.md`（新增「Portfolio Review 管線」一節）

**Interfaces:**
- Produces: `python -m src.portfolio.cli --input input-08 --report-month 202609 [--today 2026-09-12] [--lang en] [--snapshots data/snapshots] [--out out]`。輸出 `out/portfolio_<report_month>_<lang>.html` 與 `data/snapshots/<report_month>/portfolio.json`。找到 PII 時 exit code 2 且不寫 HTML。

- [ ] **Step 1: 寫測試（用 Task 5 的 fixture 組一整包最小 input）**

`tests/portfolio/test_cli.py`：
```python
import json
from pathlib import Path
from tests.portfolio.conftest import make_xlsx
from tests.portfolio.test_briefing import HDR as BHDR, PRE, row as brow
from tests.portfolio.test_control_list import sheets as cl_sheets
from tests.portfolio.test_resource_summary import block, M
from src.portfolio.cli import main


def build_input(d: Path):
    make_xlsx(d / "Project List-202609.xlsx", {"project": [["BU", "維護月份", "PROJECTCODE", "PROJECTNAME", "PROJECTGROUP", "產品別", "當月生失效", "通知人員"],
                                                          ["BU10", "202609", "BR0000015346", "THORPE", "Trenton", "BU10_IPC", "Y", "X"]]})
    make_xlsx(d / "BU10_Project_Briefing_20260907.xlsx", {"20260907": PRE + [BHDR, brow("1", "PVT", "THORPE", pvt="3/21/2026", mpo="10/13/2025", mp="7/31/2026", code="BR0000015346")]})
    make_xlsx(d / "2026 EIS Resource Summary.xlsx", {"Trenton": block("THORPE", [12.0] * 8 + [0] * 4, [1e6] * 8 + [0] * 4)})
    make_xlsx(d / "2026  EIS Resource Control List-THORPE (Some One).xlsx", cl_sheets())


def test_end_to_end(tmp_path, capsys):
    inp = tmp_path / "input-09"; inp.mkdir(); build_input(inp)
    rc = main(["--input", str(inp), "--report-month", "202609", "--today", "2026-09-12", "--snapshots", str(tmp_path / "snaps"), "--out", str(tmp_path / "out")])
    assert rc == 0
    html = (tmp_path / "out" / "portfolio_202609_en.html").read_text(encoding="utf-8")
    assert "Decisions this month" in html and "THORPE" in html and "LA0801557" not in html and "SECRET_NAME" not in html
    snap = json.loads((tmp_path / "snaps" / "202609" / "portfolio.json").read_text())
    assert snap["meta"]["latest_month"] == 8 and snap["projects"][0]["code"] == "BR0000015346"
    # 第二次跑（假裝下個月），要能讀到上月快照
    rc2 = main(["--input", str(inp), "--report-month", "202610", "--today", "2026-10-12", "--snapshots", str(tmp_path / "snaps"), "--out", str(tmp_path / "out")])
    assert rc2 == 0 and (tmp_path / "snaps" / "202610" / "portfolio.json").exists()


def test_missing_master_fails(tmp_path):
    inp = tmp_path / "empty"; inp.mkdir()
    assert main(["--input", str(inp), "--report-month", "202609", "--out", str(tmp_path / "o"), "--snapshots", str(tmp_path / "s")]) == 1
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/portfolio/test_cli.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 實作**

`src/portfolio/cli.py`：
```python
"""python -m src.portfolio.cli --input input-09 --report-month 202610"""
from __future__ import annotations
import argparse
import datetime as dt
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
    loads, i6 = build_dept_loads(cls); issues += i6
    snap_iso = f"{snap_date[:4]}-{snap_date[4:6]}-{snap_date[6:]}"
    for r in briefing:
        if r.snap == snap_date and r.updated and days_between(snap_iso, r.updated) > th["briefing_stale_days"]:
            issues.append(Issue("track", "briefing_stale", f"{r.name} last updated {r.updated}", "Briefing", r.code))
    prev = read_previous(a.snapshots, a.report_month)
    issues += cross_month_corrections(prev, projects, lm)
    exceptions = build_exceptions(projects, loads, lm, cfg, a.today)
    health = build_health(projects, loads, issues, cfg, a.today, snap_date)
    stale = [i for i in issues if i.check == "briefing_stale"]
    for h in health:
        if h.check == "briefing_stale":
            h.count, h.names = len(stale), [i.detail for i in stale]
    snap = build_snapshot(a.report_month, lm, snap_date, a.today, projects, loads, capacity_by_month(loads), exceptions, health, issues)
    snap["meta"]["snap_rev"] = len({r.snap for r in briefing})
    write_snapshot(snap, a.snapshots)
    html = render_page(snap, a.lang, a.today, th)
    pii = find_pii(html)
    if pii:
        print(f"PII found, refusing to write HTML: {pii[:5]}", file=sys.stderr); return 2
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    f = out / f"portfolio_{a.report_month}_{a.lang}.html"; f.write_text(html, encoding="utf-8")
    print(f"wrote {f} ({len(html)} bytes); {len(projects)} projects; {len(cls)} control lists; latest month {lm}; snapshot {snap_date}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑全部測試**

Run: `python -m pytest tests/portfolio -v`
Expected: 全部 PASS

- [ ] **Step 5: 對真實資料跑一次並做視覺與 PII 驗證（本機）**

```bash
python -m src.portfolio.cli --input input-08 --report-month 202609 --today 2026-09-12
grep -c "LA0[0-9]\{6\}" out/portfolio_202609_en.html          # 期待 0
python - <<'EOF'
# 用 input-08 的「人力」分頁抽真實姓名做負向檢查（只在本機，結果不落地）
import glob, openpyxl, re
names=set()
for f in glob.glob("input-08/2026*Control List-*.xlsx"):
    wb=openpyxl.load_workbook(f,read_only=True,data_only=True)
    if "人力" in wb.sheetnames:
        for r in list(wb["人力"].iter_rows(values_only=True))[1:]:
            if r and r[3]: names.add(str(r[3]).split("(")[0].strip())
html=open("out/portfolio_202609_en.html",encoding="utf-8").read()
print("names checked:",len(names),"| leaked:",[n for n in names if len(n)>4 and n in html])
EOF
cd out && (python -m http.server 8765 --bind 127.0.0.1 >/dev/null 2>&1 &) ; sleep 1
timeout 60 "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --hide-scrollbars --window-size=1280,4200 --user-data-dir=/tmp/hc_final_$RANDOM --virtual-time-budget=4000 --screenshot=/tmp/portfolio_1280.png "http://127.0.0.1:8765/portfolio_202609_en.html" >/dev/null 2>&1
timeout 60 "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --hide-scrollbars --window-size=1024,4200 --user-data-dir=/tmp/hc_final2_$RANDOM --virtual-time-budget=4000 --screenshot=/tmp/portfolio_1024.png "http://127.0.0.1:8765/portfolio_202609_en.html" >/dev/null 2>&1
pkill -f "http.server 8765"
```
用 Read 工具看兩張截圖，逐項核對：五條例外文字完整、時程表沒有超出右緣、產能圖端點標籤不重疊、健康度表每列都有來源、附錄預設收合。任何一項不符就回到對應 Task 修，不在這裡打補丁。

- [ ] **Step 6: 文件**

在 `AGENTS.md` 末尾追加：
```markdown
## Portfolio Review 管線（src/portfolio，2026-09 起）

- 目的：每月給 BU10 主管的英文單頁報告，第一屏是規則算出的「Decisions this month」。設計：docs/superpowers/specs/2026-09-12-bu10-portfolio-dashboard-design.md
- 跑法：`python -m src.portfolio.cli --input input-YY --report-month YYYYMM [--lang zh]`
- 輸入：一包目錄（Project List、Briefing、Resource Summary、N 份 Control List）。`input-*/` 與 `data/snapshots/` 都 gitignored。
- 主鍵：PROJECTCODE。名稱備援對照在 config/portfolio_aliases.yaml（與舊 config/aliases.yaml 無關）。
- 門檻：config/thresholds.yaml 的 `portfolio:`；stage 分類：config/stages.yaml。
- PII：不讀「人力」「實名制」分頁；任務文字遮罩；輸出前 find_pii 擋下工號與姓名，命中則不寫檔（exit 2）。
- 跨月：每月 snapshot JSON 留在 data/snapshots/YYYYMM/，下個月自動比對過去月份數字是否被改。
- 測試：`python -m pytest tests/portfolio`。
```

- [ ] **Step 7: 清掉 mock**

```bash
rm -f out/mock_bu10_portfolio.html out/mock_bu10_portfolio_v2.html out/mock_bu10_portfolio_v3.html
```

- [ ] **Step 8: Commit**

```bash
git add src/portfolio/cli.py tests/portfolio/test_cli.py AGENTS.md
git commit -m "feat(portfolio): CLI end-to-end, real-data verification, docs"
```

---

## 自我檢查（已執行）

- **Spec 覆蓋**：§2 輸入 → Task 1–5；§3 模型與主鍵 → Task 0、7、9；§3.2a 最新月 → Task 4；§3.4 部門負載 → Task 10；§4.1 例外五條 → Task 11；§4.2 十一項健康度 → Task 11（briefing_stale 在 Task 16 計算）、Task 12（跨月）；§4.3 遮罩與不讀分頁 → Task 5、8、15；§5 八個區塊與英文文案 → Task 13、15；§6 token → Task 13；§7 架構與 snapshot → Task 12、16；§8 驗證 → Task 15 pii、Task 16；§9 測試 → 每個 Task；§10 不做的都沒做；§11 三個決定 → 門檻 0.05 在 Task 6、第五條保留在 Task 11、NTD 只進 snapshot 不進頁面。
- **Placeholder**：無 TBD / TODO；Task 11 測試裡那段含糊斷言已明確指示改成兩行清楚版本。
- **型別一致**：`Exception_` 在 Task 0 定義、Task 11 擴充三欄，Task 15 使用 `count / ask_data / extra` 與之相符；`HealthRow.source` 用 key（`control_list` 等），Task 13 字串表有對應 `hs_*`；`Issue.check` 名稱在 Task 5、9、10、12、16 與 Task 11 的 `CHECKS` / `DRIFT_CHECKS` 一致；`latest_month` 一律 1..12 整數，索引時減一。
- **已知取捨**：例外的 `evidence` 是語言中立字串（案名加數字），不做完整翻譯；`budget_missing` 的涵蓋率用 `" | a / b"` 尾綴傳遞，在 page.py 拆開，是為了不擴 dataclass 欄位，Task 15 已處理。
