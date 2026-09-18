# EIS MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一支內網 HTTP 服務，讓 uploader 上傳每月 EIS Excel 包並觸發 ingest，讓所有人透過 MCP client 查詢專案 EIS 狀態（單案、總覽與例外、部門負載、跨月比較）。

**Architecture:** 一個 Starlette app 同時掛 `/mcp`（Streamable HTTP MCP）與 `POST /upload/{YYYYMM}`；Bearer token middleware 認證、tool 內判角色；ingest 呼叫從 `cli.main()` 抽出的 `portfolio.pipeline.build_month()`，產物沿用既有 `portfolio.json` 快照格式；查詢 tools 直接讀快照，不建 SQL 表。

**Tech Stack:** Python 3.12+、`mcp>=2.2,<3`（`mcp.server.mcpserver.MCPServer`，**不是** 1.x 的 `FastMCP`）、Starlette、uvicorn、python-multipart、sqlite3、PyYAML、pytest、httpx（測試用 ASGI transport）。

**Spec:** `docs/superpowers/specs/2026-09-18-eis-mcp-server-design.md`

## Global Constraints

- Python 3.12 以上；開發機為 3.14。`/tmp/dashboard_eis_venv` 已壞（無 pip），Task 1 重建 `.venv/`（已在 `.gitignore`）。
- 所有指令在 repo 根目錄執行；`python` 指 `.venv/bin/python`。
- **AGENTS.md 第一守則**：tool 回傳只能是快照裡既有的欄位，server 端不推算、不補值；每個回傳都帶 `meta`。
- **PII 零容忍**：ingest 命中即不寫快照；每個 tool 回傳序列化後再過 `find_pii()`。
- 原檔只落在 `server_data/input/`（0700）；沒有任何 tool/resource 讀它。
- 既有 `tests/portfolio/test_cli.py` **不得修改**，重構後必須原樣通過（它 monkeypatch `src.portfolio.cli.find_pii`，所以 `cli.py` 要保留這個 import 並以參數傳給 `build_month`）。
- 不自動 commit / push（使用者全域規則）。計畫裡的 commit 步驟由執行者在使用者同意後執行；未同意就停在「測試通過」。
- SDK 事實（已 spike 驗證）：tool 函式加 `ctx: Context` 參數即注入；`ctx.headers` 是小寫鍵的 mapping；template resource（URI 含 `{var}`）可注入 `Context`，**靜態 resource 不行**；`ToolError` 訊息會原樣進 `content` 給模型讀；client 端屬性是 `r.content[0].text`、`r.contents[0].mime_type`、`tool.input_schema`。

---

## File Structure

| 檔案 | 責任 |
|---|---|
| `src/portfolio/pipeline.py` | **新增**。`build_month()`：讀輸入包 → 快照 dict + HTML + issues + PII 命中。不寫檔。三個例外類別。`find_one()`。 |
| `src/portfolio/cli.py` | **修改**。改呼叫 `build_month()`，只負責印訊息、結束碼、寫檔。 |
| `src/eis_mcp/__init__.py` | 空。 |
| `src/eis_mcp/store.py` | 資料根目錄佈局；上傳登錄 `_upload.json`；`ingest.json`；快照載入與快取；`months()`；權限檢查；檔名分類。 |
| `src/eis_mcp/auth.py` | `Principal`、`load_tokens()`、`principal_from_headers()`、`BearerAuthMiddleware`、`Audit`（SQLite）。 |
| `src/eis_mcp/state.py` | `ServerState`（store、tokens、audit、cfg）給 app 與 tools 共用。 |
| `src/eis_mcp/app.py` | `build_app()`：組 `MCPServer`、upload route、middleware、transport security。 |
| `src/eis_mcp/__main__.py` | CLI 進入點：載 tokens、檢查權限、`uvicorn.run`。 |
| `src/eis_mcp/ingest.py` | `run_ingest()`：檔案鎖、呼叫 `build_month()`、寫結果與 `ingest.json`。 |
| `src/eis_mcp/tools/_common.py` | `principal()`、`guarded()`（角色、稽核、PII 出口保險）、`resolve_month()`、`with_meta()`。 |
| `src/eis_mcp/tools/admin.py` | `ingest_month`、`list_months`。 |
| `src/eis_mcp/tools/project.py` | `get_project`、`search_projects`、`resolve_project()`。 |
| `src/eis_mcp/tools/overview.py` | `get_exceptions`、`get_health`、`get_upcoming_milestones`、`upcoming_milestones()`。 |
| `src/eis_mcp/tools/load.py` | `get_dept_loads`、`get_capacity`。 |
| `src/eis_mcp/tools/diff.py` | `diff_project`、`get_corrections`、`diff_values()`。 |
| `src/eis_mcp/tools/resources.py` | `eis://months`、`eis://{month}/report.html`。 |
| `src/eis_mcp/tools/__init__.py` | `register_all(mcp, state)`。 |
| `scripts/eis-upload.sh` | curl 包裝。 |
| `tests/portfolio/test_pipeline.py` | `build_month()` 與 CLI 等價、三種例外、`pii_check` 注入。 |
| `tests/eis_mcp/conftest.py` | fixtures：`store`、`input_pack`、`app`、`uploaded`、`ingested`；helpers：`call_tool()`、`read_resource()`、`post_upload()`。 |
| `tests/eis_mcp/test_store.py`、`test_auth.py`、`test_app.py`、`test_ingest.py`、`test_tools_project.py`、`test_tools_overview.py`、`test_tools_load.py`、`test_tools_diff.py`、`test_resources.py`、`test_main.py` | 逐模組測試。 |

---

### Task 1: 抽出 `portfolio.pipeline.build_month()`，CLI 改為呼叫它

**Files:**
- Create: `src/portfolio/pipeline.py`
- Modify: `src/portfolio/cli.py`（整個 `main()` 與 import 區）
- Modify: `requirements.txt`
- Test: `tests/portfolio/test_pipeline.py`

**Interfaces:**
- Consumes: 既有 `src/portfolio/extract/*`、`model/*`、`render/*`（簽名見 `cli.py` 現況）。
- Produces:
  ```python
  class MissingInput(Exception):      # .missing: list[str]，值為 "master" | "briefing" | "summary"
  class InputUnreadable(Exception)    # str(ex) 為原 ValueError 訊息
  class NoManpowerMonth(Exception)    # str(ex) 為完整訊息
  INPUT_GLOBS: dict[str, str]         # {"master": "Project List-*.xlsx", "briefing": "BU10_Project_Briefing_*.xlsx", "summary": "*Resource Summary.xlsx"}
  @dataclass class BuildResult: snap: dict; html: str; issues: list[Issue]; pii_hits: list[str]; summary: dict
  def find_one(d: Path, pattern: str) -> Path | None
  def build_month(input_dir: str | Path, report_month: str, today: str, snapshots_dir: str | Path,
                  cfg: Config, lang: str = "en", pii_check: Callable[[str], list[str]] = find_pii) -> BuildResult
  ```
  `summary` 固定四鍵：`projects`（int）、`control_lists`（int）、`latest_month`（int 1..12）、`snap_date`（"YYYYMMDD"）。

- [ ] **Step 1: 重建 venv 並確認現有測試全綠**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -q -r requirements.txt
.venv/bin/python -m pytest tests/portfolio -q
```
Expected: `102 passed`

- [ ] **Step 2: 加新依賴到 `requirements.txt`**

把檔案內容改成：

```
openpyxl>=3.1
pyxlsb>=1.0.10
PyYAML>=6.0
pytest>=8.0
# EIS MCP server（src/eis_mcp）
mcp>=2.2,<3
starlette>=0.40
uvicorn>=0.30
python-multipart>=0.0.9
httpx>=0.27
```

```bash
.venv/bin/python -m pip install -q -r requirements.txt
.venv/bin/python -c "from mcp.server.mcpserver import MCPServer; print('ok')"
```
Expected: `ok`

- [ ] **Step 3: 寫失敗測試 `tests/portfolio/test_pipeline.py`**

```python
import json
from src.portfolio.cli import main
from src.portfolio.config import load_config
from src.portfolio.pipeline import build_month, MissingInput, NoManpowerMonth, InputUnreadable
from tests.portfolio.conftest import make_xlsx
from tests.portfolio.test_cli import build_input
from tests.portfolio.test_resource_summary import block


def test_build_month_matches_cli_output(tmp_path):
    inp = tmp_path / "input-09"; inp.mkdir(); build_input(inp)
    snaps, out = tmp_path / "snaps", tmp_path / "out"
    assert main(["--input", str(inp), "--report-month", "202609", "--today", "2026-09-12", "--snapshots", str(snaps), "--out", str(out)]) == 0
    res = build_month(inp, "202609", "2026-09-12", snaps, load_config())
    assert res.snap == json.loads((snaps / "202609" / "portfolio.json").read_text(encoding="utf-8"))
    assert res.html == (out / "portfolio_202609_en.html").read_text(encoding="utf-8")
    assert res.pii_hits == []
    assert set(res.summary) == {"projects", "control_lists", "latest_month", "snap_date"}
    assert res.summary["latest_month"] == 8 and res.summary["snap_date"] == "20260907" and res.summary["control_lists"] == 1


def test_build_month_does_not_write_files(tmp_path):
    inp = tmp_path / "input-09"; inp.mkdir(); build_input(inp)
    build_month(inp, "202609", "2026-09-12", tmp_path / "snaps", load_config())
    assert not (tmp_path / "snaps").exists()


def test_missing_input_lists_categories(tmp_path):
    empty = tmp_path / "empty"; empty.mkdir()
    try:
        build_month(empty, "202609", "2026-09-12", tmp_path / "s", load_config())
        assert False, "expected MissingInput"
    except MissingInput as ex:
        assert ex.missing == ["master", "briefing", "summary"]


def test_no_manpower_month_raises(tmp_path):
    inp = tmp_path / "input-zero"; inp.mkdir(); build_input(inp)
    make_xlsx(inp / "2026 EIS Resource Summary.xlsx", {"Trenton": block("THORPE", [0] * 12, [0] * 12)})
    try:
        build_month(inp, "202609", "2026-09-12", tmp_path / "s", load_config())
        assert False, "expected NoManpowerMonth"
    except NoManpowerMonth as ex:
        assert "Resource Summary.xlsx" in str(ex)


def test_unreadable_master_raises(tmp_path):
    inp = tmp_path / "input-bad"; inp.mkdir(); build_input(inp)
    make_xlsx(inp / "Project List-202609.xlsx", {"project": [["nothing", "useful"]]})
    try:
        build_month(inp, "202609", "2026-09-12", tmp_path / "s", load_config())
        assert False, "expected InputUnreadable"
    except InputUnreadable:
        pass


def test_pii_check_is_injectable(tmp_path):
    inp = tmp_path / "input-09"; inp.mkdir(); build_input(inp)
    res = build_month(inp, "202609", "2026-09-12", tmp_path / "s", load_config(), pii_check=lambda text: ["LA0000001"])
    assert "LA0000001" in res.pii_hits
```

- [ ] **Step 4: 跑測試確認失敗**

```bash
.venv/bin/python -m pytest tests/portfolio/test_pipeline.py -q
```
Expected: 收集階段 `ModuleNotFoundError: No module named 'src.portfolio.pipeline'`

- [ ] **Step 5: 建立 `src/portfolio/pipeline.py`**

```python
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
```

- [ ] **Step 6: 重寫 `src/portfolio/cli.py`**

整檔改成：

```python
"""python -m src.portfolio.cli --input input-09 --report-month 202610"""
from __future__ import annotations
import argparse
import datetime as dt
import sys
from pathlib import Path
from .config import load_config
from .model.snapshot import write_snapshot
from .pipeline import build_month, InputUnreadable, MissingInput, NoManpowerMonth
from .render.pii import find_pii  # 保留：tests/portfolio/test_cli.py 會 monkeypatch 這個名字


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True); ap.add_argument("--report-month", required=True)
    ap.add_argument("--today", default=dt.date.today().isoformat()); ap.add_argument("--lang", default="en")
    ap.add_argument("--snapshots", default="data/snapshots"); ap.add_argument("--out", default="out")
    a = ap.parse_args(argv)
    d = Path(a.input)
    try:
        res = build_month(d, a.report_month, a.today, a.snapshots, load_config(), a.lang, pii_check=find_pii)
    except MissingInput:
        print(f"missing master/briefing/summary in {d}", file=sys.stderr); return 1
    except (InputUnreadable, NoManpowerMonth) as ex:
        print(str(ex), file=sys.stderr); return 1
    # 負向檢查在任何寫檔之前，HTML 與 snapshot JSON 都要過；命中就兩個檔案都不寫。
    if res.pii_hits:
        print(f"PII found, refusing to write HTML or snapshot: {res.pii_hits[:5]}", file=sys.stderr); return 2
    write_snapshot(res.snap, a.snapshots)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    f = out / f"portfolio_{a.report_month}_{a.lang}.html"; f.write_text(res.html, encoding="utf-8")
    s = res.summary
    print(f"wrote {f} ({len(res.html)} bytes); {s['projects']} projects; {s['control_lists']} control lists; latest month {s['latest_month']}; snapshot {s['snap_date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: 跑全部 portfolio 測試**

```bash
.venv/bin/python -m pytest tests/portfolio -q
```
Expected: `108 passed`（原 102 + 新 6），`test_cli.py` 四個測試原樣通過。

- [ ] **Step 8: Commit（需使用者同意）**

```bash
git add src/portfolio/pipeline.py src/portfolio/cli.py tests/portfolio/test_pipeline.py requirements.txt
git commit -m "refactor(portfolio): extract build_month() from cli.main for reuse by the MCP server"
```

---

### Task 2: `eis_mcp/store.py` — 資料根目錄佈局、上傳登錄、快照載入

**Files:**
- Create: `src/eis_mcp/__init__.py`（空檔）
- Create: `src/eis_mcp/store.py`
- Create: `tests/eis_mcp/__init__.py`（空檔）
- Create: `tests/eis_mcp/conftest.py`（此任務先放 `store`、`input_pack`；Task 4 會整檔覆蓋成完整版）
- Test: `tests/eis_mcp/test_store.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `src.portfolio.model.snapshot.write_snapshot(d, snapshots_dir)`。
- Produces:
  ```python
  MONTH_RE: re.Pattern                      # ^\d{6}$
  PATTERNS: list[tuple[str, re.Pattern]]    # [("master", ...), ("briefing", ...), ("summary", ...), ("control_list", ...)]
  ALLOWED_DESCRIPTIONS: list[str]           # 給 400 回應用的人讀樣式
  def classify_filename(name: str) -> str | None
  class UnknownMonth(Exception)             # str(ex) == month
  class SnapshotBroken(Exception)           # str(ex) == month
  @dataclass class Store:
      root: Path
      tokens_file / audit_db / input_root / snapshots_root / locks_root : Path   (properties)
      def init_layout(self) -> None
      def check_permissions(self) -> list[str]           # 空表示 OK；否則每項是一條可執行的 chmod 指令
      def input_dir(self, month) -> Path ; def snapshot_dir(self, month) -> Path
      def register_upload(self, month, name, data: bytes, by: str) -> dict   # {name,size,sha256,uploaded_by,uploaded_at}
      def uploads(self, month) -> list[dict]
      def record_ingest(self, month, rec: dict) -> None ; def ingests(self, month) -> list[dict]
      def write_result(self, month, snap: dict, html: str) -> None
      def invalidate(self, month: str | None = None) -> None
      def load_snapshot(self, month) -> dict            # raises UnknownMonth / SnapshotBroken
      def report_html(self, month) -> str               # raises UnknownMonth
      def months(self) -> list[dict]                    # [{month,status,uploads,last_ingest}] 由新到舊；status ∈ ok|broken|uploaded_only
      def latest_month(self) -> str | None              # 最新 status=="ok" 的月份
  ```

- [ ] **Step 1: `.gitignore` 加 server 資料目錄**

在 `.gitignore` 最後加：

```
# MCP server 資料根目錄：原檔、快照、token、稽核，全部不進版控
server_data/
```

- [ ] **Step 2: 建空的 package 檔與最小 conftest**

```bash
touch src/eis_mcp/__init__.py tests/eis_mcp/__init__.py
```

`tests/eis_mcp/conftest.py`：

```python
import pytest
from src.eis_mcp.store import Store
from tests.portfolio.test_cli import build_input


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "data"); s.init_layout()
    return s


@pytest.fixture
def input_pack(tmp_path):
    d = tmp_path / "pack"; d.mkdir(); build_input(d)
    return d
```

- [ ] **Step 3: 寫失敗測試 `tests/eis_mcp/test_store.py`**

```python
import json
import stat
from src.eis_mcp.store import Store, classify_filename, UnknownMonth, SnapshotBroken


def test_classify_filename_accepts_the_four_kinds_and_rejects_the_rest():
    assert classify_filename("Project List-202609.xlsx") == "master"
    assert classify_filename("BU10_Project_Briefing_20260907.xlsx") == "briefing"
    assert classify_filename("2026 EIS Resource Summary.xlsx") == "summary"
    assert classify_filename("2026  EIS Resource Control List-THORPE (Some One).xlsx") == "control_list"
    assert classify_filename("2026 EIS Resource Control List-RFQ_OTHERS(PM).xlsb") == "control_list"
    for bad in ("~$Project List-202609.xlsx", "../Project List-202609.xlsx", "x/Project List-202609.xlsx",
                "evil.exe", "Project List-202609.xlsx.bak", ".hidden.xlsx", ""):
        assert classify_filename(bad) is None, bad


def test_init_layout_and_permissions(store):
    assert store.input_root.is_dir() and store.snapshots_root.is_dir() and store.locks_root.is_dir()
    assert stat.S_IMODE(store.input_root.stat().st_mode) == 0o700
    assert store.check_permissions() == []
    store.input_root.chmod(0o755)
    store.tokens_file.write_text("tokens: []"); store.tokens_file.chmod(0o644)
    problems = store.check_permissions()
    assert any(p == f"chmod 700 {store.input_root}" for p in problems)
    assert any(p == f"chmod 600 {store.tokens_file}" for p in problems)


def test_register_upload_appends_registry_and_overwrites_file(store):
    r1 = store.register_upload("202609", "Project List-202609.xlsx", b"one", "Alice")
    r2 = store.register_upload("202609", "Project List-202609.xlsx", b"three", "Bob")
    assert (store.input_dir("202609") / "Project List-202609.xlsx").read_bytes() == b"three"
    assert r1["size"] == 3 and r2["size"] == 5 and r1["sha256"] != r2["sha256"]
    regs = store.uploads("202609")
    assert [r["uploaded_by"] for r in regs] == ["Alice", "Bob"] and all("uploaded_at" in r for r in regs)
    assert store.uploads("202610") == []


def test_ingest_log_roundtrip(store):
    store.record_ingest("202609", {"at": "t1", "by": "Alice", "status": "rejected_pii"})
    store.record_ingest("202609", {"at": "t2", "by": "Alice", "status": "ok"})
    assert [r["status"] for r in store.ingests("202609")] == ["rejected_pii", "ok"]


def _snap(month):
    return {"meta": {"version": "1", "report_month": month, "latest_month": 8, "snap_date": "20260907", "generated": "2026-09-12"},
            "projects": [], "loads": [], "capacity": [0] * 12, "exceptions": [], "health": [], "issues": []}


def test_write_result_then_load_and_months(store):
    store.write_result("202609", _snap("202609"), "<html>r</html>")
    assert store.load_snapshot("202609")["meta"]["report_month"] == "202609"
    assert store.report_html("202609") == "<html>r</html>"
    store.register_upload("202610", "Project List-202610.xlsx", b"x", "Alice")
    (store.snapshot_dir("202608")).mkdir(parents=True); (store.snapshot_dir("202608") / "portfolio.json").write_text("{not json")
    months = store.months()
    assert [m["month"] for m in months] == ["202610", "202609", "202608"]
    assert {m["month"]: m["status"] for m in months} == {"202610": "uploaded_only", "202609": "ok", "202608": "broken"}
    assert months[0]["uploads"][0]["uploaded_by"] == "Alice" and months[1]["last_ingest"] is None
    assert store.latest_month() == "202609"


def test_load_snapshot_errors_and_cache_invalidation(store):
    try:
        store.load_snapshot("202601"); assert False
    except UnknownMonth as ex:
        assert str(ex) == "202601"
    store.write_result("202609", _snap("202609"), "")
    first = store.load_snapshot("202609")
    assert store.load_snapshot("202609") is first            # 快取命中
    (store.snapshot_dir("202609") / "portfolio.json").write_text("{broken")
    store.invalidate("202609")
    try:
        store.load_snapshot("202609"); assert False
    except SnapshotBroken as ex:
        assert str(ex) == "202609"
    assert store.latest_month() is None
```

- [ ] **Step 4: 跑測試確認失敗**

```bash
.venv/bin/python -m pytest tests/eis_mcp/test_store.py -q
```
Expected: `ModuleNotFoundError: No module named 'src.eis_mcp.store'`

- [ ] **Step 5: 建立 `src/eis_mcp/store.py`**

```python
"""server 資料根目錄的佈局與讀寫。所有路徑都從這裡出去，別的模組不自己拼路徑。

server_data/
├── tokens.yaml            0600
├── audit.sqlite
├── input/{YYYYMM}/        0700；原檔 + _upload.json
├── snapshots/{YYYYMM}/    portfolio.json + report_en.html + ingest.json
└── locks/{YYYYMM}.lock
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from ..portfolio.model.snapshot import write_snapshot

MONTH_RE = re.compile(r"^\d{6}$")
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("master", re.compile(r"^Project List-\d{6}\.xlsx$")),
    ("briefing", re.compile(r"^BU10_Project_Briefing_\d{8}\.xlsx$")),
    ("summary", re.compile(r"^.+Resource Summary\.xlsx$")),
    ("control_list", re.compile(r"^.+Resource Control List-.+\.(xlsx|xlsb)$")),
]
ALLOWED_DESCRIPTIONS = ["Project List-YYYYMM.xlsx", "BU10_Project_Briefing_YYYYMMDD.xlsx",
                        "<year> EIS Resource Summary.xlsx", "<year> EIS Resource Control List-<project> (<pm>).xlsx|.xlsb"]
_FORBIDDEN_CHARS = ("/", "\\", "\0")


def classify_filename(name: str) -> str | None:
    if not name or name.startswith("~$") or name.startswith(".") or ".." in name or any(c in name for c in _FORBIDDEN_CHARS):
        return None
    for cat, rx in PATTERNS:
        if rx.match(name):
            return cat
    return None


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class UnknownMonth(Exception):
    pass


class SnapshotBroken(Exception):
    pass


def _read_list(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _append(path: Path, rec: dict) -> None:
    rows = _read_list(path); rows.append(rec)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


@dataclass
class Store:
    root: Path
    _cache: dict[str, tuple[int, dict]] = field(default_factory=dict, init=False, repr=False)

    @property
    def tokens_file(self) -> Path: return self.root / "tokens.yaml"
    @property
    def audit_db(self) -> Path: return self.root / "audit.sqlite"
    @property
    def input_root(self) -> Path: return self.root / "input"
    @property
    def snapshots_root(self) -> Path: return self.root / "snapshots"
    @property
    def locks_root(self) -> Path: return self.root / "locks"

    def init_layout(self) -> None:
        for d in (self.input_root, self.snapshots_root, self.locks_root):
            d.mkdir(parents=True, exist_ok=True)
        self.input_root.chmod(0o700)

    def check_permissions(self) -> list[str]:
        problems = []
        if stat.S_IMODE(self.input_root.stat().st_mode) & 0o077:
            problems.append(f"chmod 700 {self.input_root}")
        if self.tokens_file.exists() and stat.S_IMODE(self.tokens_file.stat().st_mode) & 0o077:
            problems.append(f"chmod 600 {self.tokens_file}")
        return problems

    def input_dir(self, month: str) -> Path: return self.input_root / month
    def snapshot_dir(self, month: str) -> Path: return self.snapshots_root / month

    # ---- 上傳 ----
    def register_upload(self, month: str, name: str, data: bytes, by: str) -> dict:
        d = self.input_dir(month); d.mkdir(parents=True, exist_ok=True)
        (d / name).write_bytes(data)
        rec = {"name": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "uploaded_by": by, "uploaded_at": now_iso()}
        _append(d / "_upload.json", rec)
        return rec

    def uploads(self, month: str) -> list[dict]:
        return _read_list(self.input_dir(month) / "_upload.json")

    # ---- ingest ----
    def record_ingest(self, month: str, rec: dict) -> None:
        _append(self.snapshot_dir(month) / "ingest.json", rec)

    def ingests(self, month: str) -> list[dict]:
        return _read_list(self.snapshot_dir(month) / "ingest.json")

    def write_result(self, month: str, snap: dict, html: str) -> None:
        write_snapshot(snap, self.snapshots_root)
        (self.snapshot_dir(month) / "report_en.html").write_text(html, encoding="utf-8")
        self.invalidate(month)

    # ---- 快照 ----
    def invalidate(self, month: str | None = None) -> None:
        if month is None:
            self._cache.clear()
        else:
            self._cache.pop(month, None)

    def load_snapshot(self, month: str) -> dict:
        f = self.snapshot_dir(month) / "portfolio.json"
        if not f.exists():
            raise UnknownMonth(month)
        mtime = f.stat().st_mtime_ns
        hit = self._cache.get(month)
        if hit and hit[0] == mtime:
            return hit[1]
        try:
            snap = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as ex:
            raise SnapshotBroken(month) from ex
        self._cache[month] = (mtime, snap)
        return snap

    def report_html(self, month: str) -> str:
        f = self.snapshot_dir(month) / "report_en.html"
        if not f.exists():
            raise UnknownMonth(month)
        return f.read_text(encoding="utf-8")

    def _status(self, month: str) -> str:
        f = self.snapshot_dir(month) / "portfolio.json"
        if not f.exists():
            return "uploaded_only"
        try:
            self.load_snapshot(month)
            return "ok"
        except SnapshotBroken:
            return "broken"

    def months(self) -> list[dict]:
        names = set()
        for root in (self.input_root, self.snapshots_root):
            if root.exists():
                names |= {p.name for p in root.iterdir() if p.is_dir() and MONTH_RE.match(p.name)}
        out = []
        for m in sorted(names, reverse=True):
            ing = self.ingests(m)
            out.append({"month": m, "status": self._status(m), "uploads": self.uploads(m), "last_ingest": ing[-1] if ing else None})
        return out

    def latest_month(self) -> str | None:
        for m in self.months():
            if m["status"] == "ok":
                return m["month"]
        return None
```

- [ ] **Step 6: 跑測試**

```bash
.venv/bin/python -m pytest tests/eis_mcp/test_store.py -q
```
Expected: `6 passed`

- [ ] **Step 7: Commit（需使用者同意）**

```bash
git add .gitignore src/eis_mcp/__init__.py src/eis_mcp/store.py tests/eis_mcp/
git commit -m "feat(eis_mcp): data-root store with upload registry, ingest log and snapshot cache"
```

---

### Task 3: `eis_mcp/auth.py` — token、角色、middleware、稽核

**Files:**
- Create: `src/eis_mcp/auth.py`
- Test: `tests/eis_mcp/test_auth.py`

**Interfaces:**
- Produces:
  ```python
  ROLES = ("uploader", "viewer")
  @dataclass(frozen=True) class Principal: name: str; role: str
  def load_tokens(path: Path) -> dict[str, Principal]              # ValueError 訊息可讀
  def principal_from_headers(headers: Mapping[str, str], tokens: dict[str, Principal]) -> Principal | None
  class BearerAuthMiddleware(BaseHTTPMiddleware): __init__(self, app, tokens: dict[str, Principal])   # 401 JSON；成功時 request.state.principal
  class Audit:
      def __init__(self, db: Path)
      def record(self, principal: Principal | None, kind: str, action: str, args: dict, status: str, duration_ms: int, detail: str = "") -> None
      def rows(self) -> list[dict]     # 依 id 升冪，鍵同欄位名
  ```

- [ ] **Step 1: 寫失敗測試 `tests/eis_mcp/test_auth.py`**

```python
import asyncio
import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from src.eis_mcp.auth import Audit, BearerAuthMiddleware, Principal, load_tokens, principal_from_headers

TOKENS = {"tok-up": Principal("Alice", "uploader"), "tok-view": Principal("Bob", "viewer")}


def test_load_tokens_ok_and_errors(tmp_path):
    f = tmp_path / "tokens.yaml"
    f.write_text("tokens:\n  - token: abc\n    name: Alice\n    role: uploader\n  - token: def\n    name: Bob\n    role: viewer\n")
    assert load_tokens(f) == {"abc": Principal("Alice", "uploader"), "def": Principal("Bob", "viewer")}
    f.write_text("tokens:\n  - token: abc\n    name: Alice\n    role: admin\n")
    with pytest.raises(ValueError, match="role"):
        load_tokens(f)
    f.write_text("tokens:\n  - token: abc\n    name: A\n    role: viewer\n  - token: abc\n    name: B\n    role: viewer\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_tokens(f)
    f.write_text("tokens: []\n")
    with pytest.raises(ValueError, match="no tokens"):
        load_tokens(f)


def test_principal_from_headers():
    assert principal_from_headers({"authorization": "Bearer tok-up"}, TOKENS) == Principal("Alice", "uploader")
    assert principal_from_headers({"authorization": "bearer tok-view "}, TOKENS) == Principal("Bob", "viewer")
    assert principal_from_headers({"authorization": "Basic tok-up"}, TOKENS) is None
    assert principal_from_headers({}, TOKENS) is None
    assert principal_from_headers({"authorization": "Bearer nope"}, TOKENS) is None


def _app():
    async def who(request):
        return JSONResponse({"name": request.state.principal.name, "role": request.state.principal.role})
    app = Starlette(routes=[Route("/who", who)])
    app.add_middleware(BearerAuthMiddleware, tokens=TOKENS)
    return app


def _get(app, headers):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", headers=headers) as c:
            return await c.get("/who")
    return asyncio.run(go())


def test_middleware_401_without_token_and_sets_principal():
    app = _app()
    r = _get(app, {}); assert r.status_code == 401 and r.json()["error"] == "unauthorized"
    r = _get(app, {"Authorization": "Bearer nope"}); assert r.status_code == 401
    r = _get(app, {"Authorization": "Bearer tok-view"}); assert r.status_code == 200 and r.json() == {"name": "Bob", "role": "viewer"}


def test_audit_records_rows(tmp_path):
    a = Audit(tmp_path / "audit.sqlite")
    a.record(Principal("Alice", "uploader"), "tool", "ingest_month", {"report_month": "202609"}, "ok", 1234)
    a.record(None, "upload", "upload:202609", {}, "error", 5, "bad month")
    rows = a.rows()
    assert len(rows) == 2
    assert rows[0]["name"] == "Alice" and rows[0]["role"] == "uploader" and rows[0]["kind"] == "tool" and rows[0]["status"] == "ok"
    assert rows[0]["args_json"] == '{"report_month": "202609"}' and rows[0]["duration_ms"] == 1234 and rows[0]["at"]
    assert rows[1]["name"] is None and rows[1]["detail"] == "bad month"
```

- [ ] **Step 2: 跑測試確認失敗**

```bash
.venv/bin/python -m pytest tests/eis_mcp/test_auth.py -q
```
Expected: `ModuleNotFoundError: No module named 'src.eis_mcp.auth'`

- [ ] **Step 3: 建立 `src/eis_mcp/auth.py`**

```python
"""靜態 Bearer token 認證、角色、稽核。tokens.yaml 由管理者手動維護，改了要重啟。"""
from __future__ import annotations
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import yaml
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from .store import now_iso

ROLES = ("uploader", "viewer")


@dataclass(frozen=True)
class Principal:
    name: str
    role: str


def load_tokens(path: Path) -> dict[str, Principal]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, Principal] = {}
    for i, row in enumerate(doc.get("tokens") or []):
        tok, name, role = row.get("token"), row.get("name"), row.get("role")
        if not tok or not name or role not in ROLES:
            raise ValueError(f"tokens.yaml entry {i}: need token, name and role in {ROLES}")
        if str(tok) in out:
            raise ValueError(f"tokens.yaml: duplicate token used by {out[str(tok)].name} and {name}")
        out[str(tok)] = Principal(str(name), role)
    if not out:
        raise ValueError("tokens.yaml has no tokens")
    return out


def principal_from_headers(headers: Mapping[str, str], tokens: dict[str, Principal]) -> Principal | None:
    auth = headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    return tokens.get(auth[7:].strip())


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, tokens: dict[str, Principal]):
        super().__init__(app)
        self.tokens = tokens

    async def dispatch(self, request: Request, call_next):
        p = principal_from_headers(request.headers, self.tokens)
        if p is None:
            return JSONResponse({"error": "unauthorized", "detail": "send 'Authorization: Bearer <token>'; ask the server owner for a token"}, status_code=401)
        request.state.principal = p
        return await call_next(request)


class Audit:
    """每次 upload / tool / resource 一列。只存參數，不存回傳。"""
    COLUMNS = ("id", "at", "name", "role", "kind", "action", "args_json", "status", "duration_ms", "detail")

    def __init__(self, db: Path):
        self.db = Path(db)
        with sqlite3.connect(self.db) as c:
            c.execute("CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at TEXT, name TEXT, role TEXT, kind TEXT, "
                      "action TEXT, args_json TEXT, status TEXT, duration_ms INTEGER, detail TEXT)")

    def record(self, principal: Principal | None, kind: str, action: str, args: dict, status: str, duration_ms: int, detail: str = "") -> None:
        with sqlite3.connect(self.db) as c:
            c.execute("INSERT INTO audit(at, name, role, kind, action, args_json, status, duration_ms, detail) VALUES (?,?,?,?,?,?,?,?,?)",
                      (now_iso(), principal.name if principal else None, principal.role if principal else None, kind, action,
                       json.dumps(args, ensure_ascii=False), status, duration_ms, detail))

    def rows(self) -> list[dict]:
        with sqlite3.connect(self.db) as c:
            return [dict(zip(self.COLUMNS, r)) for r in c.execute("SELECT " + ", ".join(self.COLUMNS) + " FROM audit ORDER BY id")]
```

- [ ] **Step 4: 跑測試**

```bash
.venv/bin/python -m pytest tests/eis_mcp/test_auth.py -q
```
Expected: `4 passed`

- [ ] **Step 5: Commit（需使用者同意）**

```bash
git add src/eis_mcp/auth.py tests/eis_mcp/test_auth.py
git commit -m "feat(eis_mcp): bearer token auth middleware, roles and sqlite audit"
```

---

### Task 4: `eis_mcp/app.py` + `state.py` + `__main__.py` — 組 app、upload route、啟動檢查

**Files:**
- Create: `src/eis_mcp/state.py`
- Create: `src/eis_mcp/app.py`
- Create: `src/eis_mcp/__main__.py`
- Modify: `tests/eis_mcp/conftest.py`（整檔覆蓋）
- Test: `tests/eis_mcp/test_app.py`、`tests/eis_mcp/test_main.py`

**Interfaces:**
- Consumes: Task 2 `Store`、`MONTH_RE`、`classify_filename`、`ALLOWED_DESCRIPTIONS`；Task 3 `Principal`、`load_tokens`、`BearerAuthMiddleware`、`Audit`。
- Produces:
  ```python
  # state.py
  @dataclass class ServerState: store: Store; tokens: dict[str, Principal]; audit: Audit; cfg: Config
  # app.py
  INSTRUCTIONS: str
  def build_app(store: Store, tokens: dict[str, Principal], *, cfg: Config | None = None,
                host: str = "0.0.0.0", allowed_hosts: list[str] | None = None) -> Starlette   # app.state.eis 是 ServerState
  def register_upload_route(mcp: MCPServer, state: ServerState) -> None
  # __main__.py
  def main(argv: list[str] | None = None) -> int
  ```
  **Task 5 會在 `build_app()` 裡加一行 `register_all(mcp, state)`；本任務先不註冊任何 tool。**

- [ ] **Step 1: 整檔覆蓋 `tests/eis_mcp/conftest.py`**

```python
"""eis_mcp 測試共用：fixtures 與跨 ASGI 的 MCP client helper（不需要 pytest-asyncio）。"""
import asyncio
import json
import httpx
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from src.eis_mcp.app import build_app
from src.eis_mcp.auth import Principal
from src.eis_mcp.store import Store
from tests.portfolio.test_cli import build_input

TOKENS = {"tok-up": Principal("Alice", "uploader"), "tok-view": Principal("Bob", "viewer")}
TODAY = "2026-09-12"


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "data"); s.init_layout()
    return s


@pytest.fixture
def input_pack(tmp_path):
    d = tmp_path / "pack"; d.mkdir(); build_input(d)
    return d


@pytest.fixture
def app(store):
    return build_app(store, TOKENS)


@pytest.fixture
def uploaded(app, input_pack):
    files = {p.name: p.read_bytes() for p in input_pack.iterdir()}
    r = post_upload(app, "tok-up", "202609", files)
    assert r.status_code == 200, r.text
    return app


@pytest.fixture
def ingested(uploaded):
    from src.eis_mcp.ingest import run_ingest
    out = run_ingest(uploaded.state.eis, "202609", TODAY, "Alice")
    assert out["status"] == "ok", out
    return uploaded


def http(app, token):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers)


def call_tool(app, token, name, args=None):
    """回 (is_error, payload)。成功時 payload 是 dict；失敗時是錯誤字串。"""
    async def go():
        async with app.router.lifespan_context(app):
            async with Client(streamable_http_client("http://test/mcp", http_client=http(app, token))) as cl:
                r = await cl.call_tool(name, args or {})
                text = r.content[0].text
                return r.is_error, (text if r.is_error else json.loads(text))
    return asyncio.run(go())


def read_resource(app, token, uri):
    """回 (text, mime_type)；讀不到時 raise。"""
    async def go():
        async with app.router.lifespan_context(app):
            async with Client(streamable_http_client("http://test/mcp", http_client=http(app, token))) as cl:
                r = await cl.read_resource(uri)
                return r.contents[0].text, r.contents[0].mime_type
    return asyncio.run(go())


def post_upload(app, token, month, files):
    """files: {filename: bytes}。回 httpx.Response。"""
    async def go():
        async with app.router.lifespan_context(app):
            async with http(app, token) as c:
                return await c.post(f"/upload/{month}", files=[("file", (n, b)) for n, b in files.items()])
    return asyncio.run(go())


def post_raw(app, token, path, **kw):
    async def go():
        async with app.router.lifespan_context(app):
            async with http(app, token) as c:
                return await c.post(path, **kw)
    return asyncio.run(go())
```

- [ ] **Step 2: 寫失敗測試 `tests/eis_mcp/test_app.py`**

```python
from tests.eis_mcp.conftest import post_raw, post_upload


def test_no_token_is_401_on_both_endpoints(app):
    assert post_raw(app, None, "/mcp", json={}).status_code == 401
    assert post_upload(app, None, "202609", {"Project List-202609.xlsx": b"x"}).status_code == 401


def test_viewer_cannot_upload(app):
    r = post_upload(app, "tok-view", "202609", {"Project List-202609.xlsx": b"x"})
    assert r.status_code == 403 and r.json()["error"] == "forbidden"
    assert app.state.eis.audit.rows()[-1]["status"] == "forbidden"


def test_bad_month_is_400(app):
    r = post_upload(app, "tok-up", "2026-09", {"Project List-202609.xlsx": b"x"})
    assert r.status_code == 400 and r.json()["error"] == "bad_month"


def test_bad_filename_rejects_whole_request(app):
    files = {"Project List-202609.xlsx": b"ok", "evil.exe": b"no", "~$Project List-202609.xlsx": b"lock"}
    r = post_upload(app, "tok-up", "202609", files)
    assert r.status_code == 400 and r.json()["error"] == "bad_filename"
    assert sorted(r.json()["rejected"]) == ["evil.exe", "~$Project List-202609.xlsx"]
    assert "allowed" in r.json()
    assert not (app.state.eis.store.input_dir("202609") / "Project List-202609.xlsx").exists()


def test_no_files_is_400(app):
    assert post_raw(app, "tok-up", "/upload/202609", data={"x": "y"}).status_code == 400


def test_uploader_stores_pack_and_registry(app, input_pack):
    files = {p.name: p.read_bytes() for p in input_pack.iterdir()}
    r = post_upload(app, "tok-up", "202609", files)
    assert r.status_code == 200
    body = r.json()
    assert body["month"] == "202609" and len(body["stored"]) == 4
    assert {s["category"] for s in body["stored"]} == {"master", "briefing", "summary", "control_list"}
    store = app.state.eis.store
    assert all((store.input_dir("202609") / n).read_bytes() == b for n, b in files.items())
    assert len(store.uploads("202609")) == 4
    post_upload(app, "tok-up", "202609", {"Project List-202609.xlsx": files["Project List-202609.xlsx"]})
    assert len(store.uploads("202609")) == 5
    row = store.audit_db and app.state.eis.audit.rows()[-1]
    assert row["kind"] == "upload" and row["action"] == "upload:202609" and row["status"] == "ok" and row["name"] == "Alice"
```

- [ ] **Step 3: 寫失敗測試 `tests/eis_mcp/test_main.py`**

```python
from src.eis_mcp.__main__ import main


def test_main_refuses_without_tokens_file(tmp_path, capsys):
    assert main(["--data", str(tmp_path / "d")]) == 1
    assert "tokens.yaml" in capsys.readouterr().err


def test_main_refuses_bad_permissions(tmp_path, capsys):
    d = tmp_path / "d"; d.mkdir()
    (d / "tokens.yaml").write_text("tokens:\n  - token: a\n    name: A\n    role: viewer\n"); (d / "tokens.yaml").chmod(0o644)
    assert main(["--data", str(d)]) == 1
    assert f"chmod 600 {d / 'tokens.yaml'}" in capsys.readouterr().err


def test_main_runs_uvicorn_with_args(tmp_path, monkeypatch):
    d = tmp_path / "d"; d.mkdir()
    (d / "tokens.yaml").write_text("tokens:\n  - token: a\n    name: A\n    role: viewer\n"); (d / "tokens.yaml").chmod(0o600)
    calls = {}
    monkeypatch.setattr("src.eis_mcp.__main__.uvicorn.run", lambda app, **kw: calls.update(kw, app=app))
    assert main(["--data", str(d), "--host", "10.0.0.5", "--port", "9000", "--allowed-host", "eis.example:9000"]) == 0
    assert calls["host"] == "10.0.0.5" and calls["port"] == 9000 and calls["app"].state.eis.store.root == d
```

- [ ] **Step 4: 跑測試確認失敗**

```bash
.venv/bin/python -m pytest tests/eis_mcp/test_app.py tests/eis_mcp/test_main.py -q
```
Expected: `ModuleNotFoundError: No module named 'src.eis_mcp.app'`

- [ ] **Step 5: 建立 `src/eis_mcp/state.py`**

```python
"""app 與所有 tools 共用的執行期狀態。"""
from __future__ import annotations
from dataclasses import dataclass
from ..portfolio.config import Config
from .auth import Audit, Principal
from .store import Store


@dataclass
class ServerState:
    store: Store
    tokens: dict[str, Principal]
    audit: Audit
    cfg: Config
```

- [ ] **Step 6: 建立 `src/eis_mcp/app.py`**

```python
"""組裝 Starlette app：/mcp（Streamable HTTP）+ POST /upload/{month}，共用 Bearer middleware。"""
from __future__ import annotations
import time
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from ..portfolio.config import Config, load_config
from .auth import Audit, BearerAuthMiddleware, Principal
from .state import ServerState
from .store import ALLOWED_DESCRIPTIONS, MONTH_RE, Store, classify_filename

INSTRUCTIONS = (
    "EIS project status for BU10, built from the monthly EIS Excel export. Every tool response carries "
    "meta.report_month and meta.latest_month: quote them when answering. Values come straight from the "
    "snapshot; never infer or fill numbers the tools did not return. Uploaders upload the monthly pack over "
    "HTTP (scripts/eis-upload.sh) and then call ingest_month; everyone else queries with get_project, "
    "search_projects, get_exceptions, get_health, get_upcoming_milestones, get_dept_loads, get_capacity, "
    "diff_project, get_corrections and list_months."
)


def register_upload_route(mcp: MCPServer, state: ServerState) -> None:
    @mcp.custom_route("/upload/{month}", methods=["POST"])
    async def upload(request: Request) -> Response:
        t0 = time.monotonic()
        month = request.path_params["month"]
        p: Principal = request.state.principal
        action = f"upload:{month}"

        def done(status: str, detail: str = "") -> None:
            state.audit.record(p, "upload", action, {"month": month}, status, int((time.monotonic() - t0) * 1000), detail)

        if not MONTH_RE.match(month):
            done("error", "bad_month")
            return JSONResponse({"error": "bad_month", "detail": "month must be YYYYMM, e.g. /upload/202610"}, status_code=400)
        if p.role != "uploader":
            done("forbidden")
            return JSONResponse({"error": "forbidden", "detail": f"token '{p.name}' has role '{p.role}'; uploads need an uploader token"}, status_code=403)
        form = await request.form()
        files = [f for f in form.getlist("file") if isinstance(f, UploadFile)]
        if not files:
            done("error", "no_files")
            return JSONResponse({"error": "no_files", "detail": "send one or more multipart fields named 'file'"}, status_code=400)
        rejected = [f.filename or "" for f in files if classify_filename(f.filename or "") is None]
        if rejected:
            done("error", "bad_filename: " + ", ".join(rejected))
            return JSONResponse({"error": "bad_filename", "rejected": rejected, "allowed": ALLOWED_DESCRIPTIONS,
                                 "detail": "nothing was stored; rename or drop the rejected files and resend the whole pack"}, status_code=400)
        stored = []
        for f in files:
            rec = state.store.register_upload(month, f.filename, await f.read(), p.name)
            rec["category"] = classify_filename(f.filename)
            stored.append(rec)
        done("ok", ", ".join(s["name"] for s in stored))
        return JSONResponse({"month": month, "stored": stored})


def build_app(store: Store, tokens: dict[str, Principal], *, cfg: Config | None = None,
              host: str = "0.0.0.0", allowed_hosts: list[str] | None = None) -> Starlette:
    state = ServerState(store, tokens, Audit(store.audit_db), cfg or load_config())
    mcp = MCPServer("eis", instructions=INSTRUCTIONS)
    register_upload_route(mcp, state)
    if allowed_hosts:
        ts = TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=list(allowed_hosts), allowed_origins=[])
    else:
        ts = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = mcp.streamable_http_app(host=host, transport_security=ts)
    app.add_middleware(BearerAuthMiddleware, tokens=tokens)
    app.state.eis = state
    return app
```

- [ ] **Step 7: 建立 `src/eis_mcp/__main__.py`**

```python
"""python -m src.eis_mcp --data server_data --host 0.0.0.0 --port 8765 [--allowed-host eis-host:8765]"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
import uvicorn
from .app import build_app
from .auth import load_tokens
from .store import Store


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="EIS MCP server")
    ap.add_argument("--data", default="server_data", help="data root (tokens.yaml, input/, snapshots/, audit.sqlite)")
    ap.add_argument("--host", default="0.0.0.0"); ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--allowed-host", action="append", default=None,
                    help="Host header values to accept (enables DNS-rebinding protection); repeatable, e.g. eis-host:8765")
    a = ap.parse_args(argv)
    store = Store(Path(a.data)); store.init_layout()
    if not store.tokens_file.exists():
        print(f"{store.tokens_file} not found. Create it with entries like:\n"
              "tokens:\n  - token: <secrets.token_urlsafe(32)>\n    name: Alice\n    role: uploader\n"
              f"then: chmod 600 {store.tokens_file}", file=sys.stderr)
        return 1
    problems = store.check_permissions()
    if problems:
        print("refusing to start; fix permissions first:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    try:
        tokens = load_tokens(store.tokens_file)
    except ValueError as ex:
        print(str(ex), file=sys.stderr); return 1
    app = build_app(store, tokens, host=a.host, allowed_hosts=a.allowed_host)
    uvicorn.run(app, host=a.host, port=a.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 8: 跑測試**

```bash
.venv/bin/python -m pytest tests/eis_mcp -q
```
Expected: 全綠（store 6 + auth 4 + app 6 + main 3 = `19 passed`）。

- [ ] **Step 9: Commit（需使用者同意）**

```bash
git add src/eis_mcp/state.py src/eis_mcp/app.py src/eis_mcp/__main__.py tests/eis_mcp/conftest.py tests/eis_mcp/test_app.py tests/eis_mcp/test_main.py
git commit -m "feat(eis_mcp): starlette app with /mcp, authenticated upload route and CLI entrypoint"
```

---

### Task 5: `ingest.py` + `tools/_common.py` + `tools/admin.py` — ingest_month、list_months

**Files:**
- Create: `src/eis_mcp/ingest.py`
- Create: `src/eis_mcp/tools/__init__.py`
- Create: `src/eis_mcp/tools/_common.py`
- Create: `src/eis_mcp/tools/admin.py`
- Modify: `src/eis_mcp/app.py`（`build_app()` 加一行）
- Test: `tests/eis_mcp/test_ingest.py`

**Interfaces:**
- Consumes: Task 1 `build_month`、`MissingInput`、`InputUnreadable`、`NoManpowerMonth`、`INPUT_GLOBS`；Task 2 `Store`、`UnknownMonth`、`SnapshotBroken`、`MONTH_RE`；Task 3 `Principal`、`principal_from_headers`；Task 4 `ServerState`。
- Produces:
  ```python
  # ingest.py
  class IngestBusy(Exception)
  def run_ingest(state: ServerState, month: str, today: str, by: str) -> dict
      # {"status": "ok", "summary", "health": [{level,check,count}], "issues_count", "warnings": [str]}
      # 或 {"status": "rejected_pii", "hits": [str], "summary", "warnings", "next": str}
      # raises IngestBusy / MissingInput / InputUnreadable / NoManpowerMonth / ValueError(bad month)
  # tools/_common.py
  def principal(state, ctx: Context) -> Principal
  def guarded(state, ctx, action: str, args: dict, fn: Callable[[Principal], dict], *, requires: str | None = None) -> dict
  def resolve_month(state, month: str | None) -> tuple[str, dict]
  def with_meta(snap: dict, **payload) -> dict      # {"meta": snap["meta"], **payload}
  # tools/__init__.py
  def register_all(mcp: MCPServer, state: ServerState) -> None
  # tools/admin.py
  def register(mcp, state) -> None   # tools: ingest_month(report_month, today?) ; list_months()
  ```

- [ ] **Step 1: 寫失敗測試 `tests/eis_mcp/test_ingest.py`**

```python
import fcntl
import pytest
from src.eis_mcp.ingest import IngestBusy, run_ingest
from tests.eis_mcp.conftest import TODAY, call_tool


def test_viewer_cannot_ingest(uploaded):
    err, text = call_tool(uploaded, "tok-view", "ingest_month", {"report_month": "202609", "today": TODAY})
    assert err and "forbidden" in text and "uploader" in text
    assert uploaded.state.eis.audit.rows()[-1]["status"] == "forbidden"


def test_ingest_without_files_names_missing_categories(app):
    err, text = call_tool(app, "tok-up", "ingest_month", {"report_month": "202609", "today": TODAY})
    assert err and "missing_input" in text and "master" in text and "eis-upload.sh 202609" in text


def test_ingest_bad_month(app):
    err, text = call_tool(app, "tok-up", "ingest_month", {"report_month": "2026-09"})
    assert err and "bad_month" in text


def test_ingest_ok_writes_snapshot_and_log(uploaded):
    err, out = call_tool(uploaded, "tok-up", "ingest_month", {"report_month": "202609", "today": TODAY})
    assert not err, out
    assert out["status"] == "ok" and out["summary"]["latest_month"] == 8 and out["summary"]["control_lists"] == 1
    assert isinstance(out["health"], list) and {"level", "check", "count"} <= set(out["health"][0])
    assert out["warnings"] == []
    store = uploaded.state.eis.store
    assert (store.snapshot_dir("202609") / "portfolio.json").exists() and (store.snapshot_dir("202609") / "report_en.html").exists()
    log = store.ingests("202609")
    assert len(log) == 1 and log[0]["status"] == "ok" and log[0]["by"] == "Alice"
    row = uploaded.state.eis.audit.rows()[-1]
    assert row["action"] == "ingest_month" and row["status"] == "ok" and row["name"] == "Alice"


def test_ingest_warns_when_no_control_list(app, input_pack):
    from tests.eis_mcp.conftest import post_upload
    files = {p.name: p.read_bytes() for p in input_pack.iterdir() if "Control List" not in p.name}
    assert post_upload(app, "tok-up", "202609", files).status_code == 200
    err, out = call_tool(app, "tok-up", "ingest_month", {"report_month": "202609", "today": TODAY})
    assert not err and out["status"] == "ok" and any("Control List" in w for w in out["warnings"])


def test_ingest_rejected_pii_writes_nothing(uploaded, monkeypatch):
    monkeypatch.setattr("src.eis_mcp.ingest.find_pii", lambda text, *a, **kw: ["LA0000001"])
    err, out = call_tool(uploaded, "tok-up", "ingest_month", {"report_month": "202609", "today": TODAY})
    assert not err and out["status"] == "rejected_pii" and out["hits"] == ["LA0000001", "LA0000001"] and "next" in out
    store = uploaded.state.eis.store
    assert not (store.snapshot_dir("202609") / "portfolio.json").exists()
    assert store.ingests("202609")[-1]["status"] == "rejected_pii"
    assert (store.input_dir("202609") / "Project List-202609.xlsx").exists()   # 原檔保留
    assert uploaded.state.eis.audit.rows()[-1]["status"] == "ok"                # tool 本身正常結束


def test_ingest_busy_when_lock_held(uploaded):
    state = uploaded.state.eis
    lock = state.store.locks_root / "202609.lock"
    fh = open(lock, "w"); fcntl.flock(fh, fcntl.LOCK_EX)
    try:
        with pytest.raises(IngestBusy):
            run_ingest(state, "202609", TODAY, "Alice")
        err, text = call_tool(uploaded, "tok-up", "ingest_month", {"report_month": "202609", "today": TODAY})
        assert err and "busy" in text
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN); fh.close()


def test_list_months_shows_uploads_and_ingest(ingested):
    err, out = call_tool(ingested, "tok-view", "list_months")
    assert not err
    m = out["months"][0]
    assert m["month"] == "202609" and m["status"] == "ok" and len(m["uploads"]) == 4
    assert m["last_ingest"]["by"] == "Alice" and m["last_ingest"]["status"] == "ok"


def test_rerun_appends_ingest_log(ingested):
    err, out = call_tool(ingested, "tok-up", "ingest_month", {"report_month": "202609", "today": TODAY})
    assert not err and len(ingested.state.eis.store.ingests("202609")) == 2
```

- [ ] **Step 2: 跑測試確認失敗**

```bash
.venv/bin/python -m pytest tests/eis_mcp/test_ingest.py -q
```
Expected: `ModuleNotFoundError: No module named 'src.eis_mcp.ingest'`

- [ ] **Step 3: 建立 `src/eis_mcp/ingest.py`**

```python
"""ingest 一個月份：檔案鎖 → build_month() → 寫快照/HTML/ingest.json。PII 命中就什麼都不寫。"""
from __future__ import annotations
import fcntl
from ..portfolio.pipeline import build_month
from ..portfolio.render.pii import find_pii   # 獨立 import：測試會 monkeypatch src.eis_mcp.ingest.find_pii
from .state import ServerState
from .store import MONTH_RE, now_iso


class IngestBusy(Exception):
    pass


def run_ingest(state: ServerState, month: str, today: str, by: str) -> dict:
    if not MONTH_RE.match(month):
        raise ValueError(f"bad_month: '{month}' must be YYYYMM")
    lock_path = state.store.locks_root / f"{month}.lock"
    with open(lock_path, "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise IngestBusy(month) from None
        try:
            return _ingest_locked(state, month, today, by)
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _ingest_locked(state: ServerState, month: str, today: str, by: str) -> dict:
    store = state.store
    res = build_month(store.input_dir(month), month, today, store.snapshots_root, state.cfg, pii_check=find_pii)
    warnings = []
    if res.summary["control_lists"] == 0:
        warnings.append("no Control List was uploaded for this month: plan-vs-actual, tasks and dept loads are empty")
    base = {"at": now_iso(), "by": by, "today": today, "summary": res.summary, "issues_count": len(res.issues)}
    if res.pii_hits:
        store.record_ingest(month, {**base, "status": "rejected_pii", "pii_hits": res.pii_hits[:5]})
        return {"status": "rejected_pii", "hits": res.pii_hits[:5], "summary": res.summary, "warnings": warnings,
                "next": "nothing was written; fix the source file (usually a Control List task description), re-upload it and call ingest_month again"}
    store.write_result(month, res.snap, res.html)
    store.record_ingest(month, {**base, "status": "ok"})
    return {"status": "ok", "summary": res.summary,
            "health": [{"level": h["level"], "check": h["check"], "count": h["count"]} for h in res.snap["health"]],
            "issues_count": len(res.issues), "warnings": warnings}
```

- [ ] **Step 4: 建立 `src/eis_mcp/tools/_common.py`**

```python
"""所有 tool 共用：取呼叫者、角色檢查、稽核、PII 出口保險、月份解析。"""
from __future__ import annotations
import json
import time
from collections.abc import Callable
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from ...portfolio.render.pii import find_pii
from ..auth import Principal, principal_from_headers
from ..state import ServerState
from ..store import SnapshotBroken, UnknownMonth


def principal(state: ServerState, ctx: Context) -> Principal:
    p = principal_from_headers(ctx.headers or {}, state.tokens)
    if p is None:
        raise ToolError("unauthorized: this connection carries no valid token; reconnect with 'Authorization: Bearer <token>'")
    return p


def guarded(state: ServerState, ctx: Context, action: str, args: dict, fn: Callable[[Principal], dict], *, requires: str | None = None) -> dict:
    t0 = time.monotonic()
    p = principal(state, ctx)

    def ms() -> int:
        return int((time.monotonic() - t0) * 1000)

    if requires and p.role != requires:
        state.audit.record(p, "tool", action, args, "forbidden", ms())
        raise ToolError(f"forbidden: {action} requires role '{requires}'; token '{p.name}' has role '{p.role}'. Ask an uploader to run it.")
    try:
        out = fn(p)
    except ToolError as ex:
        state.audit.record(p, "tool", action, args, "error", ms(), str(ex)); raise
    except Exception as ex:
        state.audit.record(p, "tool", action, args, "error", ms(), repr(ex)); raise
    hits = find_pii(json.dumps(out, ensure_ascii=False))
    if hits:
        state.audit.record(p, "tool", action, args, "rejected_pii", ms(), "; ".join(hits[:5]))
        raise ToolError(f"rejected_pii: the {action} response contained {len(hits)} PII-shaped fragment(s) and was withheld. "
                        "Tell the server owner; an uploader should fix the source and re-run ingest_month for this month.")
    state.audit.record(p, "tool", action, args, "ok", ms())
    return out


def resolve_month(state: ServerState, month: str | None) -> tuple[str, dict]:
    store = state.store
    if month is None:
        month = store.latest_month()
        if month is None:
            raise ToolError("no_snapshot: nothing has been ingested yet. An uploader must upload a month and call ingest_month first.")
    try:
        return month, store.load_snapshot(month)
    except UnknownMonth:
        avail = [m["month"] for m in store.months() if m["status"] == "ok"]
        raise ToolError(f"unknown_month: {month} has no snapshot. Available: {', '.join(avail) or 'none'}. Call list_months for details.") from None
    except SnapshotBroken:
        raise ToolError(f"snapshot_broken: portfolio.json for {month} is unreadable. Ask an uploader to run ingest_month('{month}') again.") from None


def with_meta(snap: dict, **payload) -> dict:
    return {"meta": snap["meta"], **payload}
```

- [ ] **Step 5: 建立 `src/eis_mcp/tools/admin.py`**

```python
"""uploader 用的 tools：ingest_month、list_months（list_months 兩種角色都可）。"""
from __future__ import annotations
import datetime as dt
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from ...portfolio.pipeline import INPUT_GLOBS, InputUnreadable, MissingInput, NoManpowerMonth
from ..ingest import IngestBusy, run_ingest
from ..state import ServerState
from ._common import guarded


def register(mcp: MCPServer, state: ServerState) -> None:
    @mcp.tool()
    def ingest_month(report_month: str, ctx: Context, today: str | None = None) -> dict:
        """Build the snapshot for one month from the Excel pack already uploaded to /upload/{report_month}. Uploader role only.

        Args: report_month "YYYYMM"; today "YYYY-MM-DD" (optional) as the reference date for overdue/upcoming milestones,
        pass it when re-running a past month. Returns status "ok" with summary/health/issues_count/warnings, or
        status "rejected_pii" (nothing written) with the offending fragments. Errors name what to do next.
        """
        def go(p):
            try:
                return run_ingest(state, report_month, today or dt.date.today().isoformat(), p.name)
            except ValueError as ex:
                raise ToolError(str(ex)) from None
            except IngestBusy:
                raise ToolError(f"busy: an ingest for {report_month} is already running. Wait, then call list_months to see its result.") from None
            except MissingInput as ex:
                want = ", ".join(f"{k} ({INPUT_GLOBS[k]})" for k in ex.missing)
                raise ToolError(f"missing_input: {want} not found in input/{report_month}. "
                                f"Upload the pack first: scripts/eis-upload.sh {report_month} <dir>") from None
            except InputUnreadable as ex:
                raise ToolError(f"input_unreadable: {ex}. Re-export that file from EIS/PM and upload it again.") from None
            except NoManpowerMonth as ex:
                raise ToolError(f"no_manpower_month: {ex}. Check the Resource Summary has at least one month with non-zero Total EIS 人力.") from None
        return guarded(state, ctx, "ingest_month", {"report_month": report_month, "today": today}, go, requires="uploader")

    @mcp.tool()
    def list_months(ctx: Context) -> dict:
        """List every month the server knows: status (ok | broken | uploaded_only), the uploaded files with uploader and time,
        and the last ingest (by, at, status). Newest first. Use it to pick a month or to see whether an upload was ingested."""
        return guarded(state, ctx, "list_months", {}, lambda p: {"months": state.store.months()})
```

- [ ] **Step 6: 建立 `src/eis_mcp/tools/__init__.py`**

```python
"""把所有 tool / resource 模組註冊到 MCPServer。新模組在這裡加一行。"""
from __future__ import annotations
from mcp.server.mcpserver import MCPServer
from ..state import ServerState
from . import admin


def register_all(mcp: MCPServer, state: ServerState) -> None:
    admin.register(mcp, state)
```

- [ ] **Step 7: 在 `src/eis_mcp/app.py` 的 `build_app()` 註冊 tools**

import 區加：

```python
from .tools import register_all
```

`build_app()` 內 `register_upload_route(mcp, state)` 的下一行加：

```python
    register_all(mcp, state)
```

- [ ] **Step 8: 跑測試**

```bash
.venv/bin/python -m pytest tests/eis_mcp -q
```
Expected: `28 passed`（19 + ingest 9）。

- [ ] **Step 9: Commit（需使用者同意）**

```bash
git add src/eis_mcp/ingest.py src/eis_mcp/tools/ src/eis_mcp/app.py tests/eis_mcp/test_ingest.py
git commit -m "feat(eis_mcp): ingest_month and list_months tools with lock, audit and PII gate"
```

---

### Task 6: `tools/project.py` — get_project、search_projects

**Files:**
- Create: `src/eis_mcp/tools/project.py`
- Modify: `src/eis_mcp/tools/__init__.py`
- Test: `tests/eis_mcp/test_tools_project.py`

**Interfaces:**
- Consumes: Task 5 `guarded`、`resolve_month`、`with_meta`；`src.portfolio.config.normalize_name`、`Config.aliases`（正規化 alias → 正規化正名）。
- Produces:
  ```python
  def resolve_project(snap: dict, query: str, cfg: Config) -> dict | list[dict]   # dict = 唯一命中；list = 0 或多個候選
  def register(mcp, state) -> None   # tools: get_project(query, month?) ; search_projects(stage_cat?, group?, customer?, text?, month?)
  ```

- [ ] **Step 1: 寫失敗測試 `tests/eis_mcp/test_tools_project.py`**

```python
import json
from tests.eis_mcp.conftest import call_tool

CODE = "BR0000015346"


def _add_twin(app):
    """快照裡多放一個 THORPE2，讓「多筆候選」有東西可測。"""
    store = app.state.eis.store
    f = store.snapshot_dir("202609") / "portfolio.json"
    snap = json.loads(f.read_text(encoding="utf-8"))
    twin = dict(snap["projects"][0]); twin["code"] = "BR0000099999"; twin["name"] = "THORPE2"
    snap["projects"].append(twin)
    f.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8"); store.invalidate()


def test_get_project_by_code_name_and_case(ingested):
    for q in (CODE, "THORPE", "thorpe", "  Thorpe "):
        err, out = call_tool(ingested, "tok-view", "get_project", {"query": q})
        assert not err, out
        assert out["project"]["code"] == CODE and out["project"]["stage"] == "PVT" and out["meta"]["report_month"] == "202609"
        assert out["project"]["fte"][7] == 12.0 and "pva" in out["project"] and "tasks" in out["project"]


def test_get_project_partial_single_hit_and_candidates(ingested):
    err, out = call_tool(ingested, "tok-view", "get_project", {"query": "THOR"})
    assert not err and out["project"]["code"] == CODE
    _add_twin(ingested)
    err, out = call_tool(ingested, "tok-view", "get_project", {"query": "THOR"})
    assert not err and "project" not in out
    assert sorted(c["code"] for c in out["candidates"]) == [CODE, "BR0000099999"] and "hint" in out
    err, out = call_tool(ingested, "tok-view", "get_project", {"query": "THORPE"})
    assert not err and out["project"]["code"] == CODE   # 全名精確命中不受部分匹配影響


def test_get_project_not_found_and_unknown_month(ingested):
    err, text = call_tool(ingested, "tok-view", "get_project", {"query": "nope"})
    assert err and "not_found" in text and "search_projects" in text
    err, text = call_tool(ingested, "tok-view", "get_project", {"query": "THORPE", "month": "202501"})
    assert err and "unknown_month" in text and "202609" in text


def test_get_project_before_any_ingest(app):
    err, text = call_tool(app, "tok-view", "get_project", {"query": "THORPE"})
    assert err and "no_snapshot" in text


def test_search_projects_filters(ingested):
    err, out = call_tool(ingested, "tok-view", "search_projects", {})
    assert not err and out["count"] >= 1
    row = next(r for r in out["projects"] if r["code"] == CODE)
    assert set(row) == {"code", "name", "stage", "stage_cat", "customer", "group", "latest_fte"} and row["latest_fte"] == 12.0
    err, out = call_tool(ingested, "tok-view", "search_projects", {"stage_cat": "execution"})
    assert not err and any(r["code"] == CODE for r in out["projects"])
    err, out = call_tool(ingested, "tok-view", "search_projects", {"stage_cat": "Suspended"})
    assert not err and all(r["code"] != CODE for r in out["projects"])
    err, out = call_tool(ingested, "tok-view", "search_projects", {"text": "thor"})
    assert not err and out["count"] == 1
    err, out = call_tool(ingested, "tok-view", "search_projects", {"group": "trenton"})
    assert not err and out["count"] == 1
```

- [ ] **Step 2: 跑測試確認失敗**

```bash
.venv/bin/python -m pytest tests/eis_mcp/test_tools_project.py -q
```
Expected: 每個測試 FAIL，錯誤字串含 `Unknown tool: get_project`（或 `search_projects`）。

- [ ] **Step 3: 建立 `src/eis_mcp/tools/project.py`**

```python
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
        stage_cat, dates {kickoff, evt, dvt, pvt, mp, mp_orig}, in_briefing, in_control_list, has_plan, fte[12], ntd[12],
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
                        text: str | None = None, month: str | None = None) -> dict:
        """List projects, optionally filtered. stage_cat is one of RFQ / RFI, POC, Execution, MP, Sustain / EOP, Suspended, Other
        (case-insensitive). group and customer match whole values; text matches a substring of name, customer or product.
        Returns {"meta", "count", "projects": [{code, name, stage, stage_cat, customer, group, latest_fte}]} where latest_fte is
        the FTE of meta.latest_month. Use get_project for the full record.
        """
        def go(p):
            _, snap = resolve_month(state, month)
            lm = snap["meta"]["latest_month"]
            nt = normalize_name(text) if text else ""
            ng, nc = (normalize_name(group) if group else ""), (normalize_name(customer) if customer else "")
            rows = [q for q in snap["projects"]
                    if (not stage_cat or q["stage_cat"].lower() == stage_cat.lower())
                    and (not ng or normalize_name(q["group"]) == ng)
                    and (not nc or normalize_name(q["customer"]) == nc)
                    and (not nt or any(nt in normalize_name(q[k]) for k in ("name", "customer", "product")))]
            return with_meta(snap, count=len(rows), projects=[
                {"code": q["code"], "name": q["name"], "stage": q["stage"], "stage_cat": q["stage_cat"], "customer": q["customer"],
                 "group": q["group"], "latest_fte": q["fte"][lm - 1]} for q in rows])
        return guarded(state, ctx, "search_projects", {"stage_cat": stage_cat, "group": group, "customer": customer, "text": text, "month": month}, go)
```

- [ ] **Step 4: 在 `src/eis_mcp/tools/__init__.py` 註冊**

把檔案改成：

```python
"""把所有 tool / resource 模組註冊到 MCPServer。新模組在這裡加一行。"""
from __future__ import annotations
from mcp.server.mcpserver import MCPServer
from ..state import ServerState
from . import admin, project


def register_all(mcp: MCPServer, state: ServerState) -> None:
    admin.register(mcp, state)
    project.register(mcp, state)
```

- [ ] **Step 5: 跑測試**

```bash
.venv/bin/python -m pytest tests/eis_mcp -q
```
Expected: `33 passed`

- [ ] **Step 6: Commit（需使用者同意）**

```bash
git add src/eis_mcp/tools/project.py src/eis_mcp/tools/__init__.py tests/eis_mcp/test_tools_project.py
git commit -m "feat(eis_mcp): get_project and search_projects tools"
```

---

### Task 7: `tools/overview.py` — get_exceptions、get_health、get_upcoming_milestones

**Files:**
- Create: `src/eis_mcp/tools/overview.py`
- Modify: `src/eis_mcp/tools/__init__.py`
- Test: `tests/eis_mcp/test_tools_overview.py`

**Interfaces:**
- Consumes: Task 5 `guarded`、`resolve_month`、`with_meta`；`src.portfolio.model.rules.days_between(a, b) -> int`（= a − b 的天數）。
- Produces:
  ```python
  MILESTONES = ("evt", "dvt", "pvt", "mp")
  def upcoming_milestones(snap: dict, today: str, weeks: int) -> list[dict]   # [{code,name,stage_cat,milestone,date,days_left}] 依 days_left 升冪
  def register(mcp, state) -> None   # tools: get_exceptions(month?) ; get_health(month?) ; get_upcoming_milestones(weeks=8, month?, today?)
  ```

- [ ] **Step 1: 寫失敗測試 `tests/eis_mcp/test_tools_overview.py`**

```python
from src.eis_mcp.tools.overview import upcoming_milestones
from tests.eis_mcp.conftest import TODAY, call_tool

CODE = "BR0000015346"


def test_get_exceptions_and_health_return_snapshot_rows(ingested):
    err, out = call_tool(ingested, "tok-view", "get_exceptions")
    assert not err and out["meta"]["report_month"] == "202609"
    snap = ingested.state.eis.store.load_snapshot("202609")
    assert out["exceptions"] == snap["exceptions"] and out["count"] == len(snap["exceptions"])
    err, out = call_tool(ingested, "tok-view", "get_health")
    assert not err and out["health"] == snap["health"] and {"level", "check", "count", "names", "source"} <= set(out["health"][0])


def test_upcoming_milestones_pure_function():
    snap = {"projects": [
        {"code": "A", "name": "A", "stage_cat": "Execution", "in_briefing": True, "dates": {"evt": None, "dvt": None, "pvt": "2026-03-21", "mp": "2026-07-31"}},
        {"code": "S", "name": "S", "stage_cat": "Suspended", "in_briefing": True, "dates": {"evt": None, "dvt": None, "pvt": None, "mp": "2026-09-20"}},
        {"code": "N", "name": "N", "stage_cat": "Execution", "in_briefing": False, "dates": {"evt": None, "dvt": None, "pvt": None, "mp": "2026-09-20"}},
        {"code": "B", "name": "B", "stage_cat": "POC", "in_briefing": True, "dates": {"evt": "2026-10-01", "dvt": None, "pvt": None, "mp": None}},
    ]}
    rows = upcoming_milestones(snap, "2026-09-12", 8)
    assert [(r["code"], r["milestone"], r["days_left"]) for r in rows] == [("A", "mp", -43), ("B", "evt", 19)]
    assert upcoming_milestones(snap, "2026-09-12", 30)[0] == {"code": "A", "name": "A", "stage_cat": "Execution", "milestone": "pvt", "date": "2026-03-21", "days_left": -175}


def test_get_upcoming_milestones_tool(ingested):
    err, out = call_tool(ingested, "tok-view", "get_upcoming_milestones", {"today": TODAY})
    assert not err and out["weeks"] == 8 and out["today"] == TODAY
    assert out["milestones"] == [{"code": CODE, "name": "THORPE", "stage_cat": "Execution", "milestone": "mp", "date": "2026-07-31", "days_left": -43}]
    err, out = call_tool(ingested, "tok-view", "get_upcoming_milestones", {"today": TODAY, "weeks": 30})
    assert not err and [m["milestone"] for m in out["milestones"]] == ["pvt", "mp"]
    err, text = call_tool(ingested, "tok-view", "get_upcoming_milestones", {"today": "12/09/2026"})
    assert err and "bad_date" in text
```

- [ ] **Step 2: 跑測試確認失敗**

```bash
.venv/bin/python -m pytest tests/eis_mcp/test_tools_overview.py -q
```
Expected: `ModuleNotFoundError: No module named 'src.eis_mcp.tools.overview'`

- [ ] **Step 3: 建立 `src/eis_mcp/tools/overview.py`**

```python
"""組合總覽：報告第一屏的 exceptions、health 表、以及里程碑視窗。"""
from __future__ import annotations
import datetime as dt
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from ...portfolio.model.rules import days_between
from ..state import ServerState
from ._common import guarded, resolve_month, with_meta

MILESTONES = ("evt", "dvt", "pvt", "mp")


def upcoming_milestones(snap: dict, today: str, weeks: int) -> list[dict]:
    """與 rules._active() 同條件：只看 in_briefing 且非 Suspended 的專案；視窗前後各 weeks 週；已過期者 days_left 為負。"""
    span = weeks * 7
    out = []
    for p in snap["projects"]:
        if not p.get("in_briefing") or p.get("stage_cat") == "Suspended":
            continue
        for ms in MILESTONES:
            d = p["dates"].get(ms)
            if not d:
                continue
            left = days_between(d, today)
            if -span <= left <= span:
                out.append({"code": p["code"], "name": p["name"], "stage_cat": p["stage_cat"], "milestone": ms, "date": d, "days_left": left})
    return sorted(out, key=lambda r: (r["days_left"], r["code"]))


def _check_date(s: str) -> str:
    try:
        dt.date.fromisoformat(s)
    except ValueError:
        raise ToolError(f"bad_date: '{s}' must be YYYY-MM-DD") from None
    return s


def register(mcp: MCPServer, state: ServerState) -> None:
    @mcp.tool()
    def get_exceptions(ctx: Context, month: str | None = None) -> dict:
        """The 'Decisions this month' list of the portfolio report: ranked exceptions with evidence, the decision asked for,
        source and affected project codes. Returns {"meta", "count", "exceptions"} exactly as stored in the snapshot.
        month "YYYYMM" defaults to the latest ingested month."""
        def go(p):
            _, snap = resolve_month(state, month)
            return with_meta(snap, count=len(snap["exceptions"]), exceptions=snap["exceptions"])
        return guarded(state, ctx, "get_exceptions", {"month": month}, go)

    @mcp.tool()
    def get_health(ctx: Context, month: str | None = None) -> dict:
        """Data-health table: each row has level (decide | track | ok), check id, label, count, the project names involved and
        the source file. Returns {"meta", "health"} as stored in the snapshot. month "YYYYMM" defaults to the latest month."""
        def go(p):
            _, snap = resolve_month(state, month)
            return with_meta(snap, health=snap["health"])
        return guarded(state, ctx, "get_health", {"month": month}, go)

    @mcp.tool()
    def get_upcoming_milestones(ctx: Context, weeks: int = 8, month: str | None = None, today: str | None = None) -> dict:
        """EVT/DVT/PVT/MP dates within +/- weeks*7 days of today for active (in briefing, not suspended) projects.
        days_left < 0 means already passed. Returns {"meta", "today", "weeks", "milestones": [{code, name, stage_cat,
        milestone, date, days_left}]} sorted by days_left. today "YYYY-MM-DD" defaults to the server date."""
        def go(p):
            _, snap = resolve_month(state, month)
            t = _check_date(today) if today else dt.date.today().isoformat()
            return with_meta(snap, today=t, weeks=weeks, milestones=upcoming_milestones(snap, t, weeks))
        return guarded(state, ctx, "get_upcoming_milestones", {"weeks": weeks, "month": month, "today": today}, go)
```

- [ ] **Step 4: 在 `src/eis_mcp/tools/__init__.py` 註冊**

import 行改成 `from . import admin, overview, project`，`register_all()` 內加 `overview.register(mcp, state)`。

- [ ] **Step 5: 跑測試**

```bash
.venv/bin/python -m pytest tests/eis_mcp -q
```
Expected: `36 passed`

- [ ] **Step 6: Commit（需使用者同意）**

```bash
git add src/eis_mcp/tools/overview.py src/eis_mcp/tools/__init__.py tests/eis_mcp/test_tools_overview.py
git commit -m "feat(eis_mcp): exceptions, health and upcoming-milestone tools"
```

---

### Task 8: `tools/load.py` — get_dept_loads、get_capacity

**Files:**
- Create: `src/eis_mcp/tools/load.py`
- Modify: `src/eis_mcp/tools/__init__.py`
- Test: `tests/eis_mcp/test_tools_load.py`

**Interfaces:**
- Consumes: Task 5 `guarded`、`resolve_month`、`with_meta`。快照 `loads[]` 每列：`dept_code, dept_name, function, keyed_in[12], allocated[12], util[12]`；`capacity` 是 12 個數字的 list。
- Produces: `def register(mcp, state) -> None`，tools：`get_dept_loads(month?, min_util?)`、`get_capacity(month?)`。

- [ ] **Step 1: 寫失敗測試 `tests/eis_mcp/test_tools_load.py`**

```python
from tests.eis_mcp.conftest import call_tool


def test_get_dept_loads_sorted_and_filtered(ingested):
    err, out = call_tool(ingested, "tok-view", "get_dept_loads")
    assert not err and out["count"] >= 1 and out["latest_month"] == 8
    rows = out["loads"]
    assert {"dept_code", "dept_name", "function", "keyed_in", "allocated", "util", "latest_util"} <= set(rows[0])
    assert [r["latest_util"] for r in rows] == sorted((r["latest_util"] for r in rows), reverse=True)
    assert all(r["latest_util"] == r["util"][7] for r in rows)
    err, out = call_tool(ingested, "tok-view", "get_dept_loads", {"min_util": 99.0})
    assert not err and out["count"] == 0 and out["loads"] == []
    err, out = call_tool(ingested, "tok-view", "get_dept_loads", {"min_util": 0.0})
    assert not err and out["count"] == len(rows)


def test_get_capacity(ingested):
    err, out = call_tool(ingested, "tok-view", "get_capacity")
    assert not err
    snap = ingested.state.eis.store.load_snapshot("202609")
    assert out["capacity"] == snap["capacity"] and len(out["capacity"]) == 12 and out["months"] == ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
```

- [ ] **Step 2: 跑測試確認失敗**

```bash
.venv/bin/python -m pytest tests/eis_mcp/test_tools_load.py -q
```
Expected: FAIL，錯誤含 `Unknown tool: get_dept_loads`。

- [ ] **Step 3: 建立 `src/eis_mcp/tools/load.py`**

```python
"""部門負載與產能。load% 的分母是「有填報的人數」不是編制——docstring 要講。"""
from __future__ import annotations
from mcp.server.mcpserver import Context, MCPServer
from ...portfolio.entities import MONTHS
from ..state import ServerState
from ._common import guarded, resolve_month, with_meta


def register(mcp: MCPServer, state: ServerState) -> None:
    @mcp.tool()
    def get_dept_loads(ctx: Context, month: str | None = None, min_util: float | None = None) -> dict:
        """Department load rows from the Control Lists: dept_code, dept_name, function, keyed_in[12] (people who reported),
        allocated[12] (FTE managers allocated), util[12] = allocated / keyed_in, plus latest_util for meta.latest_month.
        The denominator is people who keyed in, not headcount. min_util keeps rows with latest_util >= min_util (1.0 = 100%).
        Sorted by latest_util descending. Returns {"meta", "latest_month", "count", "loads"}."""
        def go(p):
            _, snap = resolve_month(state, month)
            lm = snap["meta"]["latest_month"]
            rows = [{**r, "latest_util": r["util"][lm - 1]} for r in snap["loads"]]
            if min_util is not None:
                rows = [r for r in rows if r["latest_util"] >= min_util]
            rows.sort(key=lambda r: (-r["latest_util"], r["dept_code"]))
            return with_meta(snap, latest_month=lm, count=len(rows), loads=rows)
        return guarded(state, ctx, "get_dept_loads", {"month": month, "min_util": min_util}, go)

    @mcp.tool()
    def get_capacity(ctx: Context, month: str | None = None) -> dict:
        """Capacity ceiling per calendar month (sum of keyed-in people across departments), Jan..Dec, from the Control Lists.
        Returns {"meta", "months": ["Jan", ...], "capacity": [12 numbers]}. Months after meta.latest_month carry the last
        reported value forward."""
        def go(p):
            _, snap = resolve_month(state, month)
            return with_meta(snap, months=list(MONTHS), capacity=snap["capacity"])
        return guarded(state, ctx, "get_capacity", {"month": month}, go)
```

- [ ] **Step 4: 在 `src/eis_mcp/tools/__init__.py` 註冊**

import 行改成 `from . import admin, load, overview, project`，`register_all()` 內加 `load.register(mcp, state)`。

- [ ] **Step 5: 跑測試**

```bash
.venv/bin/python -m pytest tests/eis_mcp -q
```
Expected: `38 passed`

- [ ] **Step 6: Commit（需使用者同意）**

```bash
git add src/eis_mcp/tools/load.py src/eis_mcp/tools/__init__.py tests/eis_mcp/test_tools_load.py
git commit -m "feat(eis_mcp): dept load and capacity tools"
```

---

### Task 9: `tools/diff.py` — diff_project、get_corrections

**Files:**
- Create: `src/eis_mcp/tools/diff.py`
- Modify: `src/eis_mcp/tools/__init__.py`
- Test: `tests/eis_mcp/test_tools_diff.py`

**Interfaces:**
- Consumes: Task 5 `guarded`、`resolve_month`、`with_meta`；`src.portfolio.model.diff.cross_month_corrections` 產生的 issue `check == "cross_month_correction"`。
- Produces:
  ```python
  TOL = 0.05
  def diff_values(a, b, tol: float = TOL) -> dict | None   # None = 無差異；數值 list 逐項容差；dict list 只比長度
  def register(mcp, state) -> None   # tools: diff_project(code, month_a, month_b) ; get_corrections(month?)
  ```

- [ ] **Step 1: 寫失敗測試 `tests/eis_mcp/test_tools_diff.py`**

```python
import json
from src.eis_mcp.ingest import run_ingest
from src.eis_mcp.tools.diff import diff_values
from src.portfolio.model.snapshot import write_snapshot
from tests.eis_mcp.conftest import TODAY, call_tool

CODE = "BR0000015346"


def test_diff_values_rules():
    assert diff_values({"a": 1, "b": [1.0, 2.0]}, {"a": 1, "b": [1.02, 2.0]}) is None
    assert diff_values({"stage": "PVT", "fte": [1.0, 2.0]}, {"stage": "MP", "fte": [1.0, 5.0]}) == {"stage": {"a": "PVT", "b": "MP"}, "fte": {"a": [1.0, 2.0], "b": [1.0, 5.0]}}
    assert diff_values({"dates": {"mp": None}}, {"dates": {"mp": "2026-01-01"}}) == {"dates": {"mp": {"a": None, "b": "2026-01-01"}}}
    assert diff_values({"tasks": [{"x": 1}]}, {"tasks": [{"x": 1}, {"x": 2}]}) == {"tasks": {"a_count": 1, "b_count": 2}}
    assert diff_values({"tasks": [{"x": 1}]}, {"tasks": [{"x": 9}]}) is None
    assert diff_values({"only_a": 1}, {}) == {"only_a": {"a": 1, "b": None}}
    assert diff_values(True, False) == {"a": True, "b": False}


def _make_202610_copy(app, **changes):
    store = app.state.eis.store
    snap = json.loads((store.snapshot_dir("202609") / "portfolio.json").read_text(encoding="utf-8"))
    snap["meta"]["report_month"] = "202610"
    snap["projects"][0].update(changes)
    write_snapshot(snap, store.snapshots_root); store.invalidate()


def test_diff_project_reports_only_changed_fields(ingested):
    _make_202610_copy(ingested, stage="MP", fte=[12.0] * 8 + [5.0] + [0.0] * 3)
    err, out = call_tool(ingested, "tok-view", "diff_project", {"code": CODE, "month_a": "202609", "month_b": "202610"})
    assert not err, out
    assert out["code"] == CODE and out["month_a"] == "202609" and out["month_b"] == "202610"
    assert set(out["changed"]) == {"stage", "fte"} and out["changed"]["stage"] == {"a": "PVT", "b": "MP"}
    assert out["meta_a"]["report_month"] == "202609" and out["meta_b"]["report_month"] == "202610"
    err, out = call_tool(ingested, "tok-view", "diff_project", {"code": CODE, "month_a": "202609", "month_b": "202609"})
    assert not err and out["changed"] == {}


def test_diff_project_errors(ingested):
    err, text = call_tool(ingested, "tok-view", "diff_project", {"code": "BR0000000000", "month_a": "202609", "month_b": "202609"})
    assert err and "not_found" in text
    err, text = call_tool(ingested, "tok-view", "diff_project", {"code": CODE, "month_a": "202609", "month_b": "202501"})
    assert err and "unknown_month" in text


def test_get_corrections_lists_cross_month_issues(ingested):
    store = ingested.state.eis.store
    f = store.snapshot_dir("202609") / "portfolio.json"
    snap = json.loads(f.read_text(encoding="utf-8")); snap["projects"][0]["fte"][6] = 17.0
    f.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8"); store.invalidate()
    assert run_ingest(ingested.state.eis, "202610", "2026-10-12", "Alice")["status"] == "ok"
    err, out = call_tool(ingested, "tok-view", "get_corrections", {"month": "202610"})
    assert not err and out["count"] == 1
    c = out["corrections"][0]
    assert c["check"] == "cross_month_correction" and c["code"] == CODE and "Jul" in c["detail"] and "17.0" in c["detail"]
    err, out = call_tool(ingested, "tok-view", "get_corrections", {"month": "202609"})
    assert not err and out["count"] == 0
```

- [ ] **Step 2: 跑測試確認失敗**

```bash
.venv/bin/python -m pytest tests/eis_mcp/test_tools_diff.py -q
```
Expected: `ModuleNotFoundError: No module named 'src.eis_mcp.tools.diff'`

- [ ] **Step 3: 建立 `src/eis_mcp/tools/diff.py`**

```python
"""跨月比較：同一專案兩份快照的欄位差異，以及 ingest 時抓到的「歷史月份數字被改」清單。"""
from __future__ import annotations
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from ..state import ServerState
from ._common import guarded, resolve_month, with_meta

TOL = 0.05   # 與 model/diff.cross_month_corrections 的預設容差一致
CORRECTION_CHECK = "cross_month_correction"


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def diff_values(a, b, tol: float = TOL) -> dict | None:
    if isinstance(a, dict) and isinstance(b, dict):
        out = {}
        for k in sorted(set(a) | set(b)):
            d = diff_values(a.get(k), b.get(k), tol)
            if d is not None:
                out[k] = d
        return out or None
    if isinstance(a, list) and isinstance(b, list):
        if a and b and all(_is_num(x) for x in a + b):
            if len(a) != len(b) or any(abs(x - y) > tol for x, y in zip(a, b)):
                return {"a": a, "b": b}
            return None
        if any(isinstance(x, dict) for x in a + b):
            return None if len(a) == len(b) else {"a_count": len(a), "b_count": len(b)}
        return None if a == b else {"a": a, "b": b}
    if _is_num(a) and _is_num(b):
        return None if abs(a - b) <= tol else {"a": a, "b": b}
    return None if a == b else {"a": a, "b": b}


def register(mcp: MCPServer, state: ServerState) -> None:
    @mcp.tool()
    def diff_project(code: str, month_a: str, month_b: str, ctx: Context) -> dict:
        """Compare one project's snapshot record between two ingested months. Returns {"code", "month_a", "month_b",
        "meta_a", "meta_b", "changed": {field: {"a", "b"}}}: only fields that differ appear; nested fields (dates, pva)
        are compared key by key; numeric lists (fte, ntd, plan, actual) use a 0.05 tolerance; task/history lists report
        only a count change as {"a_count", "b_count"}. An empty "changed" means identical."""
        def go(p):
            ma, sa = resolve_month(state, month_a)
            mb, sb = resolve_month(state, month_b)
            pa = next((q for q in sa["projects"] if q["code"].upper() == code.upper()), None)
            pb = next((q for q in sb["projects"] if q["code"].upper() == code.upper()), None)
            if pa is None or pb is None:
                where = " and ".join(m for m, q in ((ma, pa), (mb, pb)) if q is None)
                raise ToolError(f"not_found: {code} is not in the snapshot for {where}. Use get_project to find the right code.")
            return {"code": pa["code"], "month_a": ma, "month_b": mb, "meta_a": sa["meta"], "meta_b": sb["meta"],
                    "changed": diff_values(pa, pb) or {}}
        return guarded(state, ctx, "diff_project", {"code": code, "month_a": month_a, "month_b": month_b}, go)

    @mcp.tool()
    def get_corrections(ctx: Context, month: str | None = None) -> dict:
        """Past-month numbers that changed between the previous snapshot and this one (PM corrected history after the fact).
        Each row: level, check == "cross_month_correction", detail ("<name> <Mon> FTE <old> -> <new>"), source, code.
        Returns {"meta", "count", "corrections"}. Empty for the first ingested month."""
        def go(p):
            _, snap = resolve_month(state, month)
            rows = [i for i in snap["issues"] if i["check"] == CORRECTION_CHECK]
            return with_meta(snap, count=len(rows), corrections=rows)
        return guarded(state, ctx, "get_corrections", {"month": month}, go)
```

- [ ] **Step 4: 在 `src/eis_mcp/tools/__init__.py` 註冊**

import 行改成 `from . import admin, diff, load, overview, project`，`register_all()` 內加 `diff.register(mcp, state)`。

- [ ] **Step 5: 跑測試**

```bash
.venv/bin/python -m pytest tests/eis_mcp -q
```
Expected: `42 passed`

- [ ] **Step 6: Commit（需使用者同意）**

```bash
git add src/eis_mcp/tools/diff.py src/eis_mcp/tools/__init__.py tests/eis_mcp/test_tools_diff.py
git commit -m "feat(eis_mcp): diff_project and get_corrections tools"
```

---

### Task 10: `tools/resources.py` + PII 出口保險測試

**Files:**
- Create: `src/eis_mcp/tools/resources.py`
- Modify: `src/eis_mcp/tools/__init__.py`
- Test: `tests/eis_mcp/test_resources.py`

**Interfaces:**
- Consumes: Task 5 `principal`；Task 2 `Store.months()`、`Store.report_html()`、`UnknownMonth`。
- Produces: `def register(mcp, state) -> None`，resources：`eis://months`（靜態，**SDK 不允許注入 Context，故不寫稽核**）、`eis://{month}/report.html`（template，有稽核）。

- [ ] **Step 1: 寫失敗測試 `tests/eis_mcp/test_resources.py`**

```python
import json
import pytest
from tests.eis_mcp.conftest import call_tool, read_resource


def test_months_resource(ingested):
    text, mime = read_resource(ingested, "tok-view", "eis://months")
    assert mime == "application/json"
    assert json.loads(text)["months"][0]["month"] == "202609"


def test_report_resource_and_audit(ingested):
    text, mime = read_resource(ingested, "tok-view", "eis://202609/report.html")
    assert mime == "text/html" and "Decisions this month" in text and "THORPE" in text
    row = ingested.state.eis.audit.rows()[-1]
    assert row["kind"] == "resource" and row["action"] == "eis://202609/report.html" and row["status"] == "ok" and row["name"] == "Bob"


def test_report_resource_unknown_month(ingested):
    with pytest.raises(Exception) as ex:
        read_resource(ingested, "tok-view", "eis://202501/report.html")
    assert "202501" in str(ex.value)
    assert ingested.state.eis.audit.rows()[-1]["status"] == "error"


def test_tool_output_pii_guard(ingested, monkeypatch):
    """出口保險：快照被塞入工號時，tool 要擋下並記 rejected_pii。"""
    store = ingested.state.eis.store
    snap = store.load_snapshot("202609")
    poisoned = json.loads(json.dumps(snap)); poisoned["projects"][0]["name"] = "THORPE LA0000001"
    monkeypatch.setattr(store, "load_snapshot", lambda month: poisoned)
    err, text = call_tool(ingested, "tok-view", "get_project", {"query": "BR0000015346"})
    assert err and "rejected_pii" in text and "LA0000001" not in text
    assert ingested.state.eis.audit.rows()[-1]["status"] == "rejected_pii"
```

- [ ] **Step 2: 跑測試確認失敗**

```bash
.venv/bin/python -m pytest tests/eis_mcp/test_resources.py -q
```
Expected: 前三個 FAIL（resource 不存在），第四個 PASS（保險已在 Task 5 的 `guarded()` 裡）。

- [ ] **Step 3: 建立 `src/eis_mcp/tools/resources.py`**

```python
"""MCP resources。eis://months 是靜態 URI，SDK 不允許注入 Context，因此讀它不進稽核（list_months tool 有）。"""
from __future__ import annotations
import json
import time
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError
from ..state import ServerState
from ..store import UnknownMonth
from ._common import principal


def register(mcp: MCPServer, state: ServerState) -> None:
    @mcp.resource("eis://months", mime_type="application/json")
    def months() -> str:
        """Every month the server knows, with status, uploads and last ingest (same as the list_months tool)."""
        return json.dumps({"months": state.store.months()}, ensure_ascii=False)

    @mcp.resource("eis://{month}/report.html", mime_type="text/html")
    def report(month: str, ctx: Context) -> str:
        """The self-contained monthly portfolio review HTML for {month} (YYYYMM), as produced by ingest_month."""
        t0 = time.monotonic(); p = principal(state, ctx); uri = f"eis://{month}/report.html"
        try:
            html = state.store.report_html(month)
        except UnknownMonth:
            state.audit.record(p, "resource", uri, {"month": month}, "error", int((time.monotonic() - t0) * 1000), "unknown_month")
            raise ResourceNotFoundError(f"no report for {month}; read eis://months to see ingested months") from None
        state.audit.record(p, "resource", uri, {"month": month}, "ok", int((time.monotonic() - t0) * 1000))
        return html
```

- [ ] **Step 4: 在 `src/eis_mcp/tools/__init__.py` 註冊**

整檔改成：

```python
"""把所有 tool / resource 模組註冊到 MCPServer。新模組在這裡加一行。"""
from __future__ import annotations
from mcp.server.mcpserver import MCPServer
from ..state import ServerState
from . import admin, diff, load, overview, project, resources


def register_all(mcp: MCPServer, state: ServerState) -> None:
    admin.register(mcp, state)
    project.register(mcp, state)
    overview.register(mcp, state)
    load.register(mcp, state)
    diff.register(mcp, state)
    resources.register(mcp, state)
```

- [ ] **Step 5: 跑全部測試**

```bash
.venv/bin/python -m pytest tests -q
```
Expected: `154 passed`（portfolio 108 + eis_mcp 46）。

- [ ] **Step 6: Commit（需使用者同意）**

```bash
git add src/eis_mcp/tools/resources.py src/eis_mcp/tools/__init__.py tests/eis_mcp/test_resources.py
git commit -m "feat(eis_mcp): months and report resources; PII exit-guard test"
```

---

### Task 11: 上傳腳本、README、端到端手動驗證

**Files:**
- Create: `scripts/eis-upload.sh`
- Modify: `README.md`（在「## 7. 已知限制」之前插入新章節，並把原第 7 節改為第 8 節）

- [ ] **Step 1: 建立 `scripts/eis-upload.sh`**

```bash
#!/usr/bin/env bash
# 把一個月份的 EIS Excel 包上傳到 EIS MCP server。
# 用法: EIS_URL=http://eis-host:8765 EIS_TOKEN=<token> scripts/eis-upload.sh 202610 ./input-10
set -euo pipefail
month="${1:?usage: eis-upload.sh <YYYYMM> <dir>}"
dir="${2:?usage: eis-upload.sh <YYYYMM> <dir>}"
: "${EIS_URL:?set EIS_URL, e.g. http://eis-host:8765}"
: "${EIS_TOKEN:?set EIS_TOKEN to your uploader token}"
[[ "$month" =~ ^[0-9]{6}$ ]] || { echo "month must be YYYYMM, got '$month'" >&2; exit 2; }
args=()
while IFS= read -r -d '' f; do args+=(-F "file=@$f"); done \
  < <(find "$dir" -maxdepth 1 -type f \( -name '*.xlsx' -o -name '*.xlsb' \) ! -name '~$*' -print0)
[ ${#args[@]} -gt 0 ] || { echo "no .xlsx/.xlsb files in $dir" >&2; exit 2; }
echo "uploading ${#args[@]} file(s) to $EIS_URL/upload/$month" >&2
curl -sS --fail-with-body -H "Authorization: Bearer $EIS_TOKEN" "${args[@]}" "$EIS_URL/upload/$month"
echo
echo "done. Now call ingest_month(\"$month\") from your MCP client." >&2
```

```bash
chmod +x scripts/eis-upload.sh
bash -n scripts/eis-upload.sh && echo syntax-ok
```
Expected: `syntax-ok`

- [ ] **Step 2: README 加「MCP server」章節**

在 `## 7. 已知限制` 之前插入，並把原 `## 7. 已知限制` 改為 `## 8. 已知限制`：

````markdown
## 7. MCP server（內網共用查詢）

`src/eis_mcp` 把同一條管線包成 Streamable HTTP MCP server：uploader 上傳每月 Excel 包並執行 `ingest_month`，其他人用 Claude Desktop / Claude Code 查詢。設計文件：`docs/superpowers/specs/2026-09-18-eis-mcp-server-design.md`。

### 7.1 伺服器端（做一次）

```bash
mkdir -p server_data
cat > server_data/tokens.yaml <<'EOF'
tokens:
  - token: <python3 -c "import secrets;print(secrets.token_urlsafe(32))">
    name: Alice
    role: uploader        # uploader | viewer
EOF
chmod 600 server_data/tokens.yaml
python -m src.eis_mcp --data server_data --host 0.0.0.0 --port 8765
```

- 原檔落在 `server_data/input/<YYYYMM>/`（0700），快照在 `server_data/snapshots/<YYYYMM>/`，稽核在 `server_data/audit.sqlite`。整個 `server_data/` 不進版控。
- 權限不對（`input/` 非 0700、`tokens.yaml` 非 0600）會拒絕啟動並印出 `chmod` 指令。
- 改 `tokens.yaml` 後要重啟。
- 若要防 DNS rebinding，加 `--allowed-host eis-host:8765`（可重複）。TLS 由前置 nginx 處理。

### 7.2 client 端設定

```json
{"mcpServers": {"eis": {"url": "http://eis-host:8765/mcp",
                         "headers": {"Authorization": "Bearer <token>"}}}}
```

### 7.3 每月流程（uploader）

```bash
EIS_URL=http://eis-host:8765 EIS_TOKEN=<token> scripts/eis-upload.sh 202610 ./input-10
```

然後在 Claude 裡說「ingest 202610」（呼叫 `ingest_month("202610")`）。回傳 `rejected_pii` 代表原檔含姓名工號形狀的字串，什麼都不會寫；修好原檔重傳再跑。

### 7.4 可用的 tools

| tool | 用途 |
|---|---|
| `ingest_month(report_month, today?)` | uploader 限定；跑管線、寫快照 |
| `list_months()` | 已有月份、誰何時上傳、ingest 狀態 |
| `get_project(query, month?)` | 代碼 / 名稱 / alias 查單案 |
| `search_projects(stage_cat?, group?, customer?, text?, month?)` | 篩選清單 |
| `get_exceptions(month?)` / `get_health(month?)` | 第一屏 Decisions 與 Data health |
| `get_upcoming_milestones(weeks=8, month?, today?)` | 前後 N 週的 EVT/DVT/PVT/MP |
| `get_dept_loads(month?, min_util?)` / `get_capacity(month?)` | 部門負載與產能 |
| `diff_project(code, month_a, month_b)` / `get_corrections(month?)` | 跨月差異、歷史數字被改 |

Resources：`eis://months`、`eis://<YYYYMM>/report.html`（月報 HTML）。

所有回傳都帶 `meta.report_month`；每個 tool 回傳出口都再過一次 PII 檢查。

### 7.5 測試

```bash
python -m pytest tests -q
```
````

- [ ] **Step 3: 端到端手動驗證（本機）**

```bash
rm -rf /tmp/eis_e2e && mkdir -p /tmp/eis_e2e && printf 'tokens:\n  - token: up1\n    name: Alice\n    role: uploader\n  - token: v1\n    name: Bob\n    role: viewer\n' > /tmp/eis_e2e/tokens.yaml && chmod 600 /tmp/eis_e2e/tokens.yaml
.venv/bin/python -m src.eis_mcp --data /tmp/eis_e2e --host 127.0.0.1 --port 8765 &
sleep 2
EIS_URL=http://127.0.0.1:8765 EIS_TOKEN=up1 scripts/eis-upload.sh 202608 ./input-08
.venv/bin/python - <<'EOF'
import asyncio, json, httpx
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
async def main():
    hc = httpx.AsyncClient(base_url="http://127.0.0.1:8765", headers={"Authorization": "Bearer up1"}, timeout=180)
    async with Client(streamable_http_client("http://127.0.0.1:8765/mcp", http_client=hc)) as cl:
        r = await cl.call_tool("ingest_month", {"report_month": "202608"}); print("ingest", r.is_error, r.content[0].text[:400])
        r = await cl.call_tool("list_months", {}); print("months", json.loads(r.content[0].text)["months"][0]["status"])
        r = await cl.call_tool("get_exceptions", {}); print("exceptions", json.loads(r.content[0].text)["count"])
asyncio.run(main())
EOF
kill %1
```
Expected：`ingest False {"status": "ok", ...}`、`months ok`、`exceptions <n>`。`input-08/` 若不存在（原檔不進版控），這一步改用 `tests/portfolio/test_cli.py::build_input` 產生的合成包：`.venv/bin/python -c "from pathlib import Path; from tests.portfolio.test_cli import build_input; d=Path('/tmp/eis_pack'); d.mkdir(exist_ok=True); build_input(d)"` 後把 `./input-08` 換成 `/tmp/eis_pack`。

- [ ] **Step 4: 跑全部測試**

```bash
.venv/bin/python -m pytest tests -q
```
Expected: `154 passed`

- [ ] **Step 5: Commit（需使用者同意）**

```bash
git add scripts/eis-upload.sh README.md
git commit -m "docs(eis_mcp): upload script and README section for the MCP server"
```

---

## Self-Review

**Spec coverage**

| Spec 節 | Task |
|---|---|
| §2 架構、`/mcp` + `/upload`、目錄 | 2、4 |
| §3 `build_month()` 抽取、CLI 行為不變 | 1 |
| §4.1 token、§4.2 授權、§4.3 稽核、§4.4 原檔保護（0700/0600 啟動檢查、不暴露原檔、出口 PII） | 3、4、5、10 |
| §5 上傳與 ingest 流程（檔名過濾、覆蓋登錄、鎖、PII 拒絕、重跑） | 4、5 |
| §6 tools 十個 + resources 兩個 | 5、6、7、8、9、10 |
| §7 錯誤表（401/403/400、missing_input、input_unreadable、no_manpower_month、busy、unknown_month、snapshot_broken、rejected_pii、啟動權限） | 3、4、5、10 |
| §8 測試 | 每個 task |
| §9 依賴與執行、client 設定、上傳腳本 | 1、11 |

與 spec 的兩處偏差（已依實測調整，spec 同步修正）：`mcp` 是 2.x（`MCPServer`），非 1.x `FastMCP`；靜態 resource `eis://months` 無法注入 Context，因此不進稽核。

**Placeholder scan**：無 TBD / TODO；每個程式步驟都有完整程式碼。

**Type consistency**：`ServerState(store, tokens, audit, cfg)` 四欄位在 Task 4 定義、Task 5–10 一致使用；`guarded(state, ctx, action, args, fn, *, requires)` 簽名一致；`Store` 方法名 `register_upload / uploads / record_ingest / ingests / write_result / invalidate / load_snapshot / report_html / months / latest_month` 在 Task 2 定義、後續一致；`run_ingest(state, month, today, by)` 在 Task 5 定義並於 conftest `ingested` fixture 與 Task 9 使用；conftest 的 `call_tool / read_resource / post_upload / post_raw` 回傳型別與各測試一致。
