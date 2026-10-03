# EIS LLM 導入（Briefing 狀態說明＋AI 工作重點）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 單案頁顯示 Briefing 狀態說明原文；另提供一個與 ingest 分開的指令，用 Cambrian 替大專案每月 task 分群命名，結果存 `ai.json` 並顯示在單案頁。

**Architecture:** 狀態說明走既有管線（Briefing → `Project.status_text` → `portfolio.json` → 網頁），不用 LLM。AI 部分是新套件 `src/eis_mcp/ai/`：程式分群並計算 FTE、Cambrian 只回 `theme`/`summary`、grounding 檢查擋掉原文沒有的數字詞、輸入雜湊做快取與過期偵測；寫進 `snapshots/<月>/ai.json`，`portfolio.json` 與 `ingest_month` 完全不動。

**Tech Stack:** Python 3.11+、httpx（既有依賴，呼叫 Cambrian 的 OpenAI 相容 API）、Starlette（既有 `/ui/`）、pytest。不新增任何套件。

**Spec:** `docs/superpowers/specs/2026-10-01-eis-llm-enrichment-design.md`

## Global Constraints

- 不新增 Python 依賴；Cambrian 用 `httpx` 直接呼叫 `POST {base}/v1/chat/completions`。
- LLM 不輸出數字：FTE、task 筆數由程式計算；LLM 回的 JSON 只取 `theme`（截到 40 字元）與 `summary`（截到 200 字元）。
- `portfolio.json` 不含任何 LLM 產出；`ingest_month` 不呼叫 LLM。
- token 只從 `EIS_CAMBRIAN_TOKEN_FILE` 指向的檔案讀；任何訊息、例外、`ai.json` 都不得含 token。
- 所有輸出照舊過 `find_pii`（只擋工號與「英文名(中文名)」配對）；人名可以顯示（需求方 2026-10-01）。
- 網頁全部文字跳脫（`html.escape`）；中英並列沿用 `pages_home.bi` / `zh-inline` 樣式。
- 設定放 `config/thresholds.yaml` 的 `portfolio:` 底下（`load_config` 只讀這層）：`ai_min_task_rows: 100`、`ai_max_groups: 5`。
- 測試指令：`.venv/bin/python -m pytest tests -q`，完成時必須全綠（目前基線 243 passed）。
- 不自動 push；每個 Task 結尾 commit 一次，commit 訊息結尾附專案慣用的 Co-Authored-By 與 Claude-Session 兩行。

## Review Focus

1. **快照在 AI 摘要產生後被重新 ingest**：task 內容變了，網頁必須顯示「摘要已過期」，絕不能顯示舊摘要（Task 7 測試 `test_ai_section_out_of_date`）。
2. **Cambrian 回應格式不對或中途斷線**：該專案記 `failed`，其他專案照常產生；全部失敗時 CLI 回 exit 3（Task 4、5、6 測試）。
3. **LLM 編出原文沒有的數字或版號**（例如「DVT-2」「12 issues」）：該群文字清空、標 `ungrounded`，網頁顯示請看原文（Task 3、5、7 測試）。
4. **狀態說明含 HTML 或角括號**（PM 從信件貼上）：必須跳脫顯示，不能變成標籤（Task 1 測試 `test_status_text_is_escaped`）。
5. **舊快照沒有 `status_text` 欄位、或沒有 `ai.json`、或 `ai.json` 壞掉**：單案頁照常 200，對應區塊不顯示或顯示一句說明（Task 1、7 測試）。

---

### Task 1: Briefing 狀態說明進快照並顯示在單案頁

**Files:**
- Modify: `src/portfolio/entities.py`（`Project` 加欄位）
- Modify: `src/portfolio/model/normalize.py:58-64`（最新 Briefing 區塊）
- Modify: `src/eis_mcp/web/pages_project.py`（新增 `status_section`，`project_body` 加參數）
- Modify: `src/eis_mcp/web/routes.py`（單案頁傳 `snap_date`）
- Modify: `src/eis_mcp/web/shell.py`（`WEB_CSS` 加 `.status-text`）
- Test: `tests/portfolio/test_normalize.py`、`tests/eis_mcp/test_web.py`

**Interfaces:**
- Produces: `Project.status_text: str`（快照 project dict 的 `"status_text"` 鍵；舊快照沒有這個鍵）
- Produces: `pages_project.status_section(p: dict, snap_date: str) -> str`
- Produces: `pages_project.project_body(month, p, today, lm, prev, snap_date: str = "", ai_html: str = "") -> str`

- [ ] **Step 1: 寫失敗的測試**

`tests/portfolio/test_normalize.py` 檔尾加：

```python
def test_latest_briefing_status_text_reaches_project():
    from src.portfolio.config import load_config
    from src.portfolio.entities import BriefingRow, MasterProject
    from src.portfolio.model.normalize import build_projects
    master = [MasterProject("BR0000015346", "THORPE")]
    old = BriefingRow("20260907", "THORPE", "BR0000015346", "PVT", status_text="old week")
    new = BriefingRow("20260929", "THORPE", "BR0000015346", "PVT", status_text="9/30:\nRenee to check")
    projects, _, _ = build_projects(master, [old, new], [], [], load_config())
    p = next(x for x in projects if x.code == "BR0000015346")
    assert p.status_text == "9/30:\nRenee to check"
```

`tests/eis_mcp/test_web.py` 檔尾加：

```python
# ---- Briefing 狀態說明（2026-10-01）----
def set_project_fields(app, **fields):
    """直接改 202609 快照第一個專案的欄位（模擬 ingest 後的內容）。"""
    store = app.state.eis.store
    f = store.snapshot_dir("202609") / "portfolio.json"
    snap = json.loads(f.read_text(encoding="utf-8"))
    for k, v in fields.items():
        if v is None:
            snap["projects"][0].pop(k, None)
        else:
            snap["projects"][0][k] = v
    f.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8"); store.invalidate()


def test_status_text_shown_on_project_page(ingested):
    set_project_fields(ingested, status_text="9/30:\n1. DVT8 shipment\nRenee to check")
    t = html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
    assert "PM status" in t and "PM 狀態說明" in t and "Renee to check" in t and "Briefing 2026-09-07" in t
    assert t.index("PM status") < t.index("Milestones, plan vs actual, tasks")


def test_status_text_is_escaped(ingested):
    set_project_fields(ingested, status_text="<b>bold</b> & <script>x</script>")
    t = html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
    assert "&lt;b&gt;bold&lt;/b&gt; &amp; &lt;script&gt;" in t and "<script>x" not in t


def test_status_section_hidden_when_missing_or_blank(ingested):
    set_project_fields(ingested, status_text=None)                 # 舊快照沒有這個鍵
    assert "PM status" not in html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
    set_project_fields(ingested, status_text="   ")
    assert "PM status" not in html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/portfolio/test_normalize.py::test_latest_briefing_status_text_reaches_project tests/eis_mcp/test_web.py -k "status_text or status_section" -q`
Expected: FAIL（`Project` 沒有 `status_text`；頁面沒有「PM status」）

- [ ] **Step 3: 實作**

`src/portfolio/entities.py`，`Project` 最後一個欄位 `history` 之後加：

```python
    status_text: str = ""           # 最新 Briefing 的 Project status 原文（含人名；內網可顯示，需求方 2026-10-01）
```

`src/portfolio/model/normalize.py`，在 `if r.snap == latest:` 區塊內 `p.biz_type, p.category, p.panel_size = ...` 那行之後加：

```python
            p.status_text = r.status_text
```

`src/eis_mcp/web/pages_project.py`，在 `def project_body(` 之前加：

```python
def status_section(p: dict, snap_date: str) -> str:
    """Briefing 的 Project status 原文，照 PM 寫的樣子顯示（換行保留、全文跳脫）。舊快照沒有這個鍵或內容空白就不顯示。"""
    text = (p.get("status_text") or "").strip()
    if not text:
        return ""
    d = f"{snap_date[:4]}-{snap_date[4:6]}-{snap_date[6:]}" if len(snap_date) == 8 else snap_date
    return (f'<section><h2>PM status <span class="zh-inline" lang="zh-Hant">PM 狀態說明</span></h2>'
            f'<p class="dim">Project status column of the Briefing {e(d)}, as written by the PM.</p>'
            f'<div class="status-text">{e(text)}</div></section>')
```

把 `project_body` 的簽章改成：

```python
def project_body(month: str, p: dict, today: str, lm: int, prev: str | None, snap_date: str = "", ai_html: str = "") -> str:
```

並把它的 `return (f'<section>{kv}{cmp_}</section>'` 改成：

```python
    return (f'<section>{kv}{cmp_}</section>{status_section(p, snap_date)}{ai_html}'
```

（其餘回傳內容不變。）

`src/eis_mcp/web/routes.py`，單案頁 handler 中：

```python
            body = pages_project.project_body(month, p, today, snap["meta"]["latest_month"], prev)
```

改成：

```python
            body = pages_project.project_body(month, p, today, snap["meta"]["latest_month"], prev, snap_date=snap["meta"]["snap_date"])
```

`src/eis_mcp/web/shell.py`，在 `WEB_CSS` 的 `pre.prompt{...}` 那行之後加：

```css
.status-text{white-space:pre-wrap;overflow-wrap:anywhere;max-width:110ch;background:#fff;border:1px solid var(--rule);padding:12px 14px;font-size:13px;line-height:1.6}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests -q`
Expected: 全部 PASS（新增 4 個）

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/entities.py src/portfolio/model/normalize.py src/eis_mcp/web/pages_project.py src/eis_mcp/web/routes.py src/eis_mcp/web/shell.py tests/portfolio/test_normalize.py tests/eis_mcp/test_web.py
git commit -m "feat: show the Briefing project status text on the project page"
```

---

### Task 2: task 分群與輸入雜湊（`groups.py`）

**Files:**
- Create: `src/eis_mcp/ai/__init__.py`
- Create: `src/eis_mcp/ai/groups.py`
- Test: `tests/eis_mcp/test_ai_groups.py`

**Interfaces:**
- Produces: `Group(side: str, function: str, fte: float, n_tasks: int, texts: tuple[str, ...], other: bool = False)`（frozen dataclass）
- Produces: `build_groups(project: dict, month: int, max_groups: int) -> list[Group]`
- Produces: `task_count(project: dict, month: int) -> int`
- Produces: `input_hash(month: int, groups: list[Group]) -> str`

- [ ] **Step 1: 寫失敗的測試**

`tests/eis_mcp/test_ai_groups.py`：

```python
from src.eis_mcp.ai.groups import build_groups, input_hash, task_count


def t(month, side, fn, fte, desc):
    return {"month": month, "side": side, "function": fn, "dept": "x", "fte": fte, "description": desc}


def test_groups_by_side_and_function_sorted_by_fte_with_other_bucket():
    p = {"tasks": [t(8, "BU", "ME", 2.8, "DVT-1 build issues"), t(8, "BU", "me ", 0.7, "DVT-1 build issues"),
                   t(8, "FU", "Thermal", 0.08, "N/A"), t(8, "BU", "SW", 0.5, "A15 regression"),
                   t(7, "BU", "ME", 9.0, "July only"), t(8, "FU", "ID", 0.4, "System build readiness")]}
    g = build_groups(p, 8, 2)
    assert [(x.side, x.function, x.fte, x.n_tasks) for x in g] == [("BU", "ME", 3.5, 2), ("BU", "SW", 0.5, 1), ("*", "Other", 0.48, 2)]
    assert g[0].texts == ("DVT-1 build issues",)                 # 同一句只留一次
    assert g[-1].other and g[-1].texts == ()                    # Other 不送 LLM，所以不帶原文
    assert task_count(p, 8) == 5


def test_placeholder_descriptions_are_dropped():
    p = {"tasks": [t(8, "FU", "Thermal", 0.1, "N/A"), t(8, "FU", "Thermal", 0.1, " na "), t(8, "FU", "Thermal", 0.1, ""),
                   t(8, "FU", "Thermal", 0.1, "-")]}
    g = build_groups(p, 8, 5)
    assert len(g) == 1 and g[0].texts == () and g[0].n_tasks == 4


def test_blank_function_is_grouped_as_none():
    g = build_groups({"tasks": [t(8, "BU", "  ", 1.0, "x")]}, 8, 5)
    assert g[0].function == "(none)"


def test_input_hash_is_stable_and_sensitive():
    p = {"tasks": [t(8, "BU", "ME", 1.0, "a")]}
    h = input_hash(8, build_groups(p, 8, 5))
    assert h == input_hash(8, build_groups({"tasks": [dict(p["tasks"][0])]}, 8, 5))
    assert h != input_hash(8, build_groups({"tasks": [t(8, "BU", "ME", 1.0, "b")]}, 8, 5))
    assert h != input_hash(8, build_groups({"tasks": [t(8, "BU", "ME", 2.0, "a")]}, 8, 5))
    assert h != input_hash(7, build_groups(p, 8, 5))
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/eis_mcp/test_ai_groups.py -q`
Expected: FAIL（`ModuleNotFoundError: src.eis_mcp.ai`）

- [ ] **Step 3: 實作**

`src/eis_mcp/ai/__init__.py`：

```python
"""選用的 AI 摘要（Cambrian）。與 ingest 分開執行，結果另存 snapshots/<月>/ai.json；portfolio.json 不含任何 LLM 產出。"""
```

`src/eis_mcp/ai/groups.py`：

```python
"""把單一專案某個月的 tasks 依 (side, function) 分群。FTE 與筆數全部在這裡算好，LLM 只替每群命名。"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass

PLACEHOLDERS = {"", "N/A", "NA", "-", "--", "TBD"}


@dataclass(frozen=True)
class Group:
    side: str
    function: str
    fte: float
    n_tasks: int
    texts: tuple[str, ...]          # 去重後的可用描述；Other 群為空
    other: bool = False


def _clean(desc: str) -> str:
    return " ".join((desc or "").split())


def task_count(project: dict, month: int) -> int:
    return sum(1 for t in project.get("tasks", []) if t.get("month") == month)


def build_groups(project: dict, month: int, max_groups: int) -> list[Group]:
    acc: dict[tuple[str, str], dict] = {}
    for t in project.get("tasks", []):
        if t.get("month") != month:
            continue
        key = (t.get("side") or "?", (t.get("function") or "").strip().upper() or "(none)")
        g = acc.setdefault(key, {"fte": 0.0, "n": 0, "texts": []})
        g["fte"] += float(t.get("fte") or 0)
        g["n"] += 1
        d = _clean(t.get("description", ""))
        if d.upper() not in PLACEHOLDERS and d not in g["texts"]:
            g["texts"].append(d)
    ordered = sorted(acc.items(), key=lambda kv: (-kv[1]["fte"], kv[0]))
    out = [Group(s, f, round(v["fte"], 2), v["n"], tuple(v["texts"])) for (s, f), v in ordered[:max_groups]]
    rest = ordered[max_groups:]
    if rest:
        out.append(Group("*", "Other", round(sum(v["fte"] for _, v in rest), 2), sum(v["n"] for _, v in rest), (), other=True))
    return out


def input_hash(month: int, groups: list[Group]) -> str:
    """產生摘要時的輸入指紋。網頁重算後不一致 → 摘要已過期。"""
    payload = [month, [[g.side, g.function, g.fte, g.n_tasks, list(g.texts), g.other] for g in groups]]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode("utf-8")).hexdigest()
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/eis_mcp/test_ai_groups.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/eis_mcp/ai/__init__.py src/eis_mcp/ai/groups.py tests/eis_mcp/test_ai_groups.py
git commit -m "feat(ai): group a project's monthly tasks by side and function with an input hash"
```

---

### Task 3: Grounding 檢查（`grounding.py`）

**Files:**
- Create: `src/eis_mcp/ai/grounding.py`
- Test: `tests/eis_mcp/test_ai_grounding.py`

**Interfaces:**
- Produces: `numeric_tokens(text: str) -> list[str]`
- Produces: `grounded(output: str, source: str) -> bool`

- [ ] **Step 1: 寫失敗的測試**

`tests/eis_mcp/test_ai_grounding.py`：

```python
from src.eis_mcp.ai.grounding import grounded, numeric_tokens

SRC = "DVT-1 build issues management\nA15_Pre RC_V02.00.26 Reg. test\nDVT8 shipment 9/30"


def test_numeric_tokens_only_keeps_words_with_digits():
    assert numeric_tokens("DVT-1 build, A15 regression on 9/30; 3 units.") == ["DVT-1", "A15", "9/30", "3"]


def test_grounded_accepts_tokens_that_appear_in_the_source():
    assert grounded("Managing DVT-1 build issues", SRC)
    assert grounded("A15 regression testing", SRC)                  # A15_Pre 的前段，邊界是底線
    assert grounded("DVT8 shipment on 9/30", SRC)
    assert grounded("Build issue management", SRC)                  # 沒有數字詞一律通過


def test_grounded_rejects_numbers_not_in_the_source():
    assert not grounded("DVT-2 build issues", SRC)
    assert not grounded("Resolved 12 issues", SRC)
    assert not grounded("A16 regression", SRC)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/eis_mcp/test_ai_grounding.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 實作**

`src/eis_mcp/ai/grounding.py`：

```python
"""LLM 輸出裡任何含數字的詞（版號、日期、數量、型號）都必須在原文出現過；否則視為編造。
中文數字（例如「九月」）不在檢查範圍，由 PM 抽查補位。"""
from __future__ import annotations
import re

TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:\-]*")


def numeric_tokens(text: str) -> list[str]:
    out = []
    for m in TOKEN.finditer(text):
        tok = m.group(0).rstrip(".-/:")
        if tok and any(c.isdigit() for c in tok):
            out.append(tok)
    return out


def grounded(output: str, source: str) -> bool:
    src = source.casefold()
    for tok in numeric_tokens(output):
        pat = r"(?<![a-z0-9])" + re.escape(tok.casefold()) + r"(?![a-z0-9])"
        if not re.search(pat, src):
            return False
    return True
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/eis_mcp/test_ai_grounding.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/eis_mcp/ai/grounding.py tests/eis_mcp/test_ai_grounding.py
git commit -m "feat(ai): grounding check rejects numbers and codes not in the source text"
```

---

### Task 4: Cambrian 客戶端（`cambrian.py`）

**Files:**
- Create: `src/eis_mcp/ai/cambrian.py`
- Test: `tests/eis_mcp/test_ai_cambrian.py`

**Interfaces:**
- Produces: `CambrianConfig(base_url: str, token: str, model: str, verify_ssl: bool = False, timeout: float = 120.0)`（frozen dataclass）
- Produces: `CambrianClient(cfg: CambrianConfig, transport: httpx.BaseTransport | None = None)`，方法 `name_group(system: str, user: str) -> dict[str, str]`（鍵 `theme`、`summary`）
- Produces: `CambrianError(Exception)`（訊息不含 token）

- [ ] **Step 1: 寫失敗的測試**

`tests/eis_mcp/test_ai_cambrian.py`：

```python
import json
import httpx
import pytest
from src.eis_mcp.ai.cambrian import CambrianClient, CambrianConfig, CambrianError


def client(handler):
    cfg = CambrianConfig("https://cambrian.test", "tok-c", "LLAMA 3.3 70B")
    return CambrianClient(cfg, transport=httpx.MockTransport(handler))


def reply(content):
    return {"choices": [{"message": {"content": content}}]}


def test_request_shape_and_parsed_reply():
    seen = {}

    def h(req):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers["authorization"], json.loads(req.content)
        return httpx.Response(200, json=reply(json.dumps({"theme": " DVT-1 build ", "summary": "Fixing DVT-1 build issues."})))

    assert client(h).name_group("sys", "usr") == {"theme": "DVT-1 build", "summary": "Fixing DVT-1 build issues."}
    assert seen["url"] == "https://cambrian.test/v1/chat/completions" and seen["auth"] == "Bearer tok-c"
    b = seen["body"]
    assert b["model"] == "LLAMA 3.3 70B" and b["response_format"] == {"type": "json_object"} and b["temperature"] == 0
    assert [m["role"] for m in b["messages"]] == ["system", "user"] and b["messages"][1]["content"] == "usr"


def test_long_fields_are_truncated():
    body = reply(json.dumps({"theme": "T" * 100, "summary": "S" * 500}))
    r = client(lambda req: httpx.Response(200, json=body)).name_group("s", "u")
    assert len(r["theme"]) == 40 and len(r["summary"]) == 200


@pytest.mark.parametrize("make", [
    lambda: httpx.Response(500, text="boom"),
    lambda: httpx.Response(200, text="not json"),
    lambda: httpx.Response(200, json=reply("not json")),
    lambda: httpx.Response(200, json=reply(json.dumps({"summary": "x"}))),
    lambda: httpx.Response(200, json=reply(json.dumps({"theme": " ", "summary": "x"}))),
    lambda: httpx.Response(200, json={"choices": []}),
])
def test_bad_replies_raise(make):
    with pytest.raises(CambrianError):
        client(lambda req: make()).name_group("s", "u")


def test_network_error_raises_without_leaking_the_token():
    def h(req):
        raise httpx.ConnectError("down")
    with pytest.raises(CambrianError) as ex:
        client(h).name_group("s", "u")
    assert "tok-c" not in str(ex.value)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/eis_mcp/test_ai_cambrian.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 實作**

`src/eis_mcp/ai/cambrian.py`：

```python
"""Cambrian（公司內部 LLM Gateway，OpenAI 相容）的最小客戶端：一次請求替一個 task 群組命名。
內網自簽憑證，verify_ssl 預設 False（EIS_CAMBRIAN_VERIFY_SSL=1 才驗證）。錯誤訊息只帶類別，不帶 token 或回應全文。"""
from __future__ import annotations
import json
from dataclasses import dataclass
import httpx

THEME_MAX, SUMMARY_MAX = 40, 200


class CambrianError(Exception):
    pass


@dataclass(frozen=True)
class CambrianConfig:
    base_url: str
    token: str
    model: str
    verify_ssl: bool = False
    timeout: float = 120.0


class CambrianClient:
    def __init__(self, cfg: CambrianConfig, transport: httpx.BaseTransport | None = None):
        self._model = cfg.model
        self._http = httpx.Client(base_url=cfg.base_url.rstrip("/"), verify=cfg.verify_ssl, timeout=cfg.timeout,
                                  transport=transport, headers={"Authorization": f"Bearer {cfg.token}"})

    def name_group(self, system: str, user: str) -> dict[str, str]:
        body = {"model": self._model, "temperature": 0, "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        try:
            r = self._http.post("/v1/chat/completions", json=body)
        except httpx.HTTPError as ex:
            raise CambrianError(f"request failed: {type(ex).__name__}") from None
        if r.status_code != 200:
            raise CambrianError(f"status {r.status_code}")
        try:
            data = json.loads(r.json()["choices"][0]["message"]["content"])
        except (ValueError, KeyError, IndexError, TypeError):
            raise CambrianError("reply is not the expected JSON") from None
        theme, summary = data.get("theme") if isinstance(data, dict) else None, data.get("summary") if isinstance(data, dict) else None
        if not isinstance(theme, str) or not isinstance(summary, str) or not theme.strip():
            raise CambrianError("reply has no theme/summary")
        return {"theme": theme.strip()[:THEME_MAX], "summary": summary.strip()[:SUMMARY_MAX]}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/eis_mcp/test_ai_cambrian.py -q`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/eis_mcp/ai/cambrian.py tests/eis_mcp/test_ai_cambrian.py
git commit -m "feat(ai): minimal Cambrian chat-completions client with JSON mode"
```

---

### Task 5: 產生月份 AI 結果（`enrich.py`）

**Files:**
- Create: `src/eis_mcp/ai/enrich.py`
- Test: `tests/eis_mcp/test_ai_enrich.py`

**Interfaces:**
- Consumes: `build_groups`、`input_hash`、`task_count`（Task 2）；`grounded`（Task 3）；`CambrianError`（Task 4）
- Produces: `PROMPT_VERSION = "1"`、`SYSTEM: str`
- Produces: `select_codes(snap: dict, min_rows: int, extra: Sequence[str] = ()) -> list[str]`
- Produces: `enrich_project(project: dict, month: int, max_groups: int, namer) -> dict`（`{"status","reason","input_hash","groups"}`）
- Produces: `enrich_month(snap: dict, namer, *, model: str, max_groups: int, min_rows: int, extra_codes=(), previous: dict | None = None, now: datetime | None = None) -> dict`
- Produces: `write_ai(doc: dict, path: Path, pii_check=find_pii) -> Path`；命中 PII 丟 `PiiInOutput`
- `namer` 是任何有 `name_group(system, user) -> {"theme","summary"}` 的物件（`CambrianClient` 或測試替身）

- [ ] **Step 1: 寫失敗的測試**

`tests/eis_mcp/test_ai_enrich.py`：

```python
import datetime as dt
import json
import pytest
from src.eis_mcp.ai.cambrian import CambrianError
from src.eis_mcp.ai.enrich import PROMPT_VERSION, PiiInOutput, enrich_month, select_codes, write_ai

NOW = dt.datetime(2026, 10, 2, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=8)))


def task(fn, fte, desc, side="BU", month=8):
    return {"month": month, "side": side, "function": fn, "dept": "x", "fte": fte, "description": desc}


def proj(code, tasks):
    return {"code": code, "name": code.lower(), "stage": "DVT", "tasks": tasks}


def snap(*projects):
    return {"meta": {"report_month": "202609", "latest_month": 8}, "projects": list(projects)}


class FakeNamer:
    def __init__(self, reply=None, fail_on=None):
        self.calls, self.reply, self.fail_on = [], reply, fail_on

    def name_group(self, system, user):
        self.calls.append(user)
        if self.fail_on and self.fail_on in user:
            raise CambrianError("status 500")
        return self.reply or {"theme": "Build issues", "summary": "Handling build issues."}   # 不含數字：對任何群組都 grounded


BIG = proj("BIG", [task("ME", 2.0, "DVT-1 build issues"), task("SW", 1.0, "A15 regression"), task("EE", 0.5, "N/A")])
SMALL = proj("SMALL", [task("ME", 1.0, "x")])


def run(s, namer, **kw):
    return enrich_month(s, namer, model="M", max_groups=kw.pop("max_groups", 5), min_rows=kw.pop("min_rows", 3), now=NOW, **kw)


def test_select_codes_by_task_rows_plus_extra():
    s = snap(BIG, SMALL)
    assert select_codes(s, 3) == ["BIG"]
    assert select_codes(s, 3, ["SMALL", "NOPE"]) == ["BIG", "SMALL"]


def test_enrich_names_groups_but_numbers_come_from_the_program():
    namer = FakeNamer()
    doc = run(snap(BIG, SMALL), namer)
    assert doc["meta"] == {"report_month": "202609", "month": 8, "model": "M", "prompt_version": PROMPT_VERSION,
                           "max_groups": 5, "generated": "2026-10-02T09:00:00+08:00"}
    assert list(doc["projects"]) == ["BIG"]
    rows = doc["projects"]["BIG"]["groups"]
    assert [(r["function"], r["fte"], r["n_tasks"], r["note"]) for r in rows] == [("ME", 2.0, 1, ""), ("SW", 1.0, 1, ""), ("EE", 0.5, 1, "no_text")]
    assert rows[0]["theme"] == "Build issues" and rows[0]["grounded"] is True
    assert len(namer.calls) == 2                                       # no_text 群不呼叫 LLM
    assert "DVT-1 build issues" in namer.calls[0] and "Function: ME" in namer.calls[0]


def test_other_bucket_is_not_sent():
    namer = FakeNamer()
    rows = run(snap(BIG), namer, max_groups=1)["projects"]["BIG"]["groups"]
    assert [r["note"] for r in rows] == ["", "other"] and len(namer.calls) == 1


def test_ungrounded_reply_is_cleared():
    rows = run(snap(BIG), FakeNamer(reply={"theme": "DVT-2 issues", "summary": "Resolved 12 issues."}))["projects"]["BIG"]["groups"]
    assert rows[0]["note"] == "ungrounded" and rows[0]["theme"] == "" and rows[0]["summary"] == "" and rows[0]["grounded"] is False


def test_one_failing_project_does_not_stop_the_others():
    other = proj("OTHER", [task("QTC", 1.0, "Reg. test"), task("QTC", 1.0, "Reg. test 2"), task("QTC", 1.0, "Reg. test 3")])
    doc = run(snap(BIG, other), FakeNamer(fail_on="Function: SW"))
    assert doc["projects"]["BIG"]["status"] == "failed" and doc["projects"]["BIG"]["reason"] == "status 500"
    assert doc["projects"]["BIG"]["groups"] == []
    assert doc["projects"]["OTHER"]["status"] == "ok"


def test_unchanged_input_reuses_previous_result():
    first = run(snap(BIG), FakeNamer())
    namer = FakeNamer()
    again = run(snap(BIG), namer, previous=first)
    assert namer.calls == [] and again["projects"]["BIG"] == first["projects"]["BIG"]
    changed = proj("BIG", [task("ME", 2.0, "DVT-1 build issues, new"), task("SW", 1.0, "A15 regression"), task("EE", 0.5, "N/A")])
    namer2 = FakeNamer()
    run(snap(changed), namer2, previous=first)
    assert len(namer2.calls) == 2
    namer3 = FakeNamer()
    enrich_month(snap(BIG), namer3, model="OTHER MODEL", max_groups=5, min_rows=3, previous=first, now=NOW)
    assert len(namer3.calls) == 2                                      # 換模型不沿用


def test_failed_result_is_retried_not_reused():
    first = run(snap(BIG), FakeNamer(fail_on="Function: ME"))
    namer = FakeNamer()
    run(snap(BIG), namer, previous=first)
    assert len(namer.calls) == 2


def test_write_ai_refuses_pii(tmp_path):
    doc = run(snap(BIG), FakeNamer())
    with pytest.raises(PiiInOutput):
        write_ai(doc, tmp_path / "ai.json", pii_check=lambda text: ["LA0000001"])
    assert not (tmp_path / "ai.json").exists()
    write_ai(doc, tmp_path / "ai.json")
    assert json.loads((tmp_path / "ai.json").read_text(encoding="utf-8")) == doc
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/eis_mcp/test_ai_enrich.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 實作**

`src/eis_mcp/ai/enrich.py`：

```python
"""產生一個月份的 AI 工作重點：選專案 → 分群 → 每群請 LLM 命名 → grounding 檢查 → 快取 → ai.json。
與 ingest 分開；任何失敗只影響該專案，不影響 portfolio.json。"""
from __future__ import annotations
import datetime as dt
import json
import os
from collections.abc import Sequence
from pathlib import Path
from ...portfolio.render.pii import find_pii
from .cambrian import CambrianError
from .groups import Group, build_groups, input_hash, task_count
from .grounding import grounded

PROMPT_VERSION = "1"
SYSTEM = ("You label one group of engineering task descriptions from a project's monthly control list. "
          'Reply with a JSON object {"theme": "a short label of at most 6 words", "summary": "one sentence"}. '
          "Use only facts stated in the descriptions. Do not add numbers, dates, counts, FTE or names that are not written in the descriptions. "
          "Write in the main language of the descriptions.")
MAX_TEXTS, MAX_TEXT_LEN = 40, 300


class PiiInOutput(Exception):
    pass


def user_prompt(project: dict, g: Group) -> str:
    lines = "\n".join(f"- {t[:MAX_TEXT_LEN]}" for t in g.texts[:MAX_TEXTS])
    return (f"Project: {project.get('name', '')}\nStage: {project.get('stage', '')}\nSide: {g.side}\nFunction: {g.function}\n"
            f"Task descriptions:\n{lines}")


def select_codes(snap: dict, min_rows: int, extra: Sequence[str] = ()) -> list[str]:
    lm = snap["meta"]["latest_month"]
    codes = [p["code"] for p in snap["projects"] if task_count(p, lm) >= min_rows]
    known = {p["code"] for p in snap["projects"]}
    return codes + [c for c in extra if c in known and c not in codes]


def _row(g: Group, theme: str = "", summary: str = "", ok: bool = False, note: str = "") -> dict:
    return {"side": g.side, "function": g.function, "fte": g.fte, "n_tasks": g.n_tasks,
            "theme": theme, "summary": summary, "grounded": ok, "note": note}


def enrich_project(project: dict, month: int, max_groups: int, namer) -> dict:
    groups = build_groups(project, month, max_groups)
    h = input_hash(month, groups)
    rows = []
    for g in groups:
        if g.other:
            rows.append(_row(g, note="other"))
            continue
        if not g.texts:
            rows.append(_row(g, note="no_text"))
            continue
        try:
            r = namer.name_group(SYSTEM, user_prompt(project, g))
        except CambrianError as ex:
            return {"status": "failed", "reason": str(ex), "input_hash": h, "groups": []}
        if grounded(f"{r['theme']} {r['summary']}", "\n".join(g.texts)):
            rows.append(_row(g, r["theme"], r["summary"], True))
        else:
            rows.append(_row(g, note="ungrounded"))
    return {"status": "ok", "reason": "", "input_hash": h, "groups": rows}


def _reusable(previous: dict | None, model: str, max_groups: int, month: int) -> dict:
    m = (previous or {}).get("meta", {})
    same = (m.get("model") == model and m.get("prompt_version") == PROMPT_VERSION
            and m.get("max_groups") == max_groups and m.get("month") == month)
    return (previous or {}).get("projects", {}) if same else {}


def enrich_month(snap: dict, namer, *, model: str, max_groups: int, min_rows: int, extra_codes: Sequence[str] = (),
                 previous: dict | None = None, now: dt.datetime | None = None) -> dict:
    lm = snap["meta"]["latest_month"]
    reuse = _reusable(previous, model, max_groups, lm)
    by_code = {p["code"]: p for p in snap["projects"]}
    out: dict[str, dict] = {}
    for code in select_codes(snap, min_rows, extra_codes):
        p = by_code[code]
        old = reuse.get(code)
        if old and old.get("status") == "ok" and old.get("input_hash") == input_hash(lm, build_groups(p, lm, max_groups)):
            out[code] = old
            continue
        out[code] = enrich_project(p, lm, max_groups, namer)
    generated = (now or dt.datetime.now().astimezone()).isoformat(timespec="seconds")
    return {"meta": {"report_month": snap["meta"]["report_month"], "month": lm, "model": model,
                     "prompt_version": PROMPT_VERSION, "max_groups": max_groups, "generated": generated},
            "projects": out}


def write_ai(doc: dict, path: Path, pii_check=find_pii) -> Path:
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    hits = pii_check(text)
    if hits:
        raise PiiInOutput(f"{len(hits)} PII-shaped fragment(s)")
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/eis_mcp/test_ai_enrich.py -q`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/eis_mcp/ai/enrich.py tests/eis_mcp/test_ai_enrich.py
git commit -m "feat(ai): build a month's AI work summary with grounding, caching and failure isolation"
```

---

### Task 6: CLI 與設定（`python -m src.eis_mcp.ai`）

**Files:**
- Create: `src/eis_mcp/ai/__main__.py`
- Modify: `config/thresholds.yaml`（`portfolio:` 底下加兩個鍵）
- Test: `tests/eis_mcp/test_ai_cli.py`

**Interfaces:**
- Consumes: `CambrianClient`、`CambrianConfig`（Task 4）；`enrich_month`、`write_ai`、`PiiInOutput`（Task 5）；`Store`（既有）
- Produces: `main(argv: list[str] | None = None, env: dict | None = None, namer_factory=None) -> int`
  - exit 0：寫入成功（至少一案 ok，或沒有任何專案符合門檻）
  - exit 1：沒有可讀快照
  - exit 2：token 檔缺／空，或輸出命中 PII（不寫檔）
  - exit 3：選到的專案全部失敗（仍寫檔）
- `namer_factory(model: str)` 只給測試用，回傳替身 namer

- [ ] **Step 1: 寫失敗的測試**

`tests/eis_mcp/test_ai_cli.py`：

```python
import json
from src.eis_mcp.ai.__main__ import main
from src.eis_mcp.ai.cambrian import CambrianError

CODE = "BR0000015346"


def add_tasks(app, n=3):
    store = app.state.eis.store
    f = store.snapshot_dir("202609") / "portfolio.json"
    snap = json.loads(f.read_text(encoding="utf-8"))
    lm = snap["meta"]["latest_month"]
    snap["projects"][0]["tasks"] = [{"month": lm, "side": "BU", "function": "ME", "dept": "x", "fte": 1.0,
                                     "description": f"DVT-1 build issue {i}"} for i in range(n)]
    f.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8"); store.invalidate()
    return store


class Namer:
    def __init__(self, fail=False):
        self.fail = fail

    def name_group(self, system, user):
        if self.fail:
            raise CambrianError("status 503")
        return {"theme": "Build issues", "summary": "Handling DVT-1 build issues."}


def test_missing_token_file_exits_2(ingested):
    store = ingested.state.eis.store
    assert main(["--data", str(store.root), "--month", "202609"], env={}) == 2
    assert not (store.snapshot_dir("202609") / "ai.json").exists()


def test_empty_token_file_exits_2(ingested, tmp_path):
    store = ingested.state.eis.store
    (tmp_path / "tok").write_text("  \n", encoding="utf-8")
    assert main(["--data", str(store.root), "--month", "202609"], env={"EIS_CAMBRIAN_TOKEN_FILE": str(tmp_path / "tok")}) == 2


def test_unknown_month_exits_1(ingested):
    store = ingested.state.eis.store
    assert main(["--data", str(store.root), "--month", "209901"], env={}, namer_factory=lambda m: Namer()) == 1
    assert main(["--data", str(store.root), "--month", "2026-09"], env={}, namer_factory=lambda m: Namer()) == 1


def test_writes_ai_json_for_selected_project(ingested):
    store = add_tasks(ingested)
    rc = main(["--data", str(store.root), "--month", "202609", "--code", CODE, "--model", "Qwen 2.5"],
              env={}, namer_factory=lambda m: Namer())
    assert rc == 0
    doc = json.loads((store.snapshot_dir("202609") / "ai.json").read_text(encoding="utf-8"))
    assert doc["meta"]["model"] == "Qwen 2.5" and doc["projects"][CODE]["status"] == "ok"
    assert doc["projects"][CODE]["groups"][0]["fte"] == 3.0


def test_all_failed_exits_3_but_still_writes(ingested):
    store = add_tasks(ingested)
    rc = main(["--data", str(store.root), "--month", "202609", "--code", CODE], env={}, namer_factory=lambda m: Namer(fail=True))
    assert rc == 3
    doc = json.loads((store.snapshot_dir("202609") / "ai.json").read_text(encoding="utf-8"))
    assert doc["projects"][CODE]["status"] == "failed"


def test_thresholds_have_ai_keys():
    from src.portfolio.config import load_config
    th = load_config().thresholds
    assert th["ai_min_task_rows"] == 100 and th["ai_max_groups"] == 5
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/eis_mcp/test_ai_cli.py -q`
Expected: FAIL（`ModuleNotFoundError: src.eis_mcp.ai.__main__`）

- [ ] **Step 3: 實作**

`config/thresholds.yaml`，在 `portfolio:` 區塊最後（`upcoming_weeks` 之後的同層）加：

```yaml
  ai_min_task_rows: 100       # 最新月 task 筆數達此值的專案才產生 AI 工作重點（202609 符合 6 案）
  ai_max_groups: 5            # 每案最多幾個 side+function 群送 LLM；其餘併成 Other，不送
```

`src/eis_mcp/ai/__main__.py`：

```python
"""python -m src.eis_mcp.ai --data DIR --month YYYYMM [--code CODE ...] [--model NAME]

環境變數：EIS_CAMBRIAN_TOKEN_FILE（必填）、EIS_CAMBRIAN_URL、EIS_CAMBRIAN_MODEL、EIS_CAMBRIAN_VERIFY_SSL=1。
exit：0 成功｜1 沒有可讀快照｜2 token 缺或輸出命中 PII｜3 選到的專案全部失敗。"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from ...portfolio.config import load_config
from ..store import SnapshotBroken, Store, UnknownMonth
from .cambrian import CambrianClient, CambrianConfig
from .enrich import PiiInOutput, enrich_month, write_ai

DEFAULT_URL = "https://api.cambrian.pegatroncorp.com"
DEFAULT_MODEL = "LLAMA 3.3 70B"


def read_token(env: dict) -> str | None:
    f = env.get("EIS_CAMBRIAN_TOKEN_FILE", "")
    if not f or not Path(f).is_file():
        return None
    return Path(f).read_text(encoding="utf-8").strip() or None


def main(argv: list[str] | None = None, env: dict | None = None, namer_factory=None) -> int:
    env = dict(os.environ) if env is None else env
    ap = argparse.ArgumentParser(prog="python -m src.eis_mcp.ai")
    ap.add_argument("--data", required=True)
    ap.add_argument("--month", required=True)
    ap.add_argument("--code", action="append", default=[], help="額外納入的專案代碼（可重複）")
    ap.add_argument("--model", default=env.get("EIS_CAMBRIAN_MODEL") or DEFAULT_MODEL)
    a = ap.parse_args(argv)
    store = Store(Path(a.data))
    try:
        snap = store.load_snapshot(a.month)
    except (UnknownMonth, SnapshotBroken):
        print(f"no readable snapshot for {a.month}", file=sys.stderr)
        return 1
    if namer_factory is not None:
        namer = namer_factory(a.model)
    else:
        token = read_token(env)
        if not token:
            print("set EIS_CAMBRIAN_TOKEN_FILE to a file holding the Cambrian token", file=sys.stderr)
            return 2
        namer = CambrianClient(CambrianConfig(env.get("EIS_CAMBRIAN_URL") or DEFAULT_URL, token, a.model,
                                              verify_ssl=env.get("EIS_CAMBRIAN_VERIFY_SSL") == "1"))
    th = load_config().thresholds
    path = store.snapshot_dir(a.month) / "ai.json"
    previous = None
    if path.exists():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = None
    doc = enrich_month(snap, namer, model=a.model, max_groups=int(th.get("ai_max_groups", 5)),
                       min_rows=int(th.get("ai_min_task_rows", 100)), extra_codes=a.code, previous=previous)
    try:
        write_ai(doc, path)
    except PiiInOutput as ex:
        print(f"ai.json not written: {ex}", file=sys.stderr)
        return 2
    st = [v["status"] for v in doc["projects"].values()]
    print(f"wrote {path}: {len(st)} project(s), {st.count('ok')} ok, {st.count('failed')} failed")
    return 3 if st and st.count("ok") == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/eis_mcp/test_ai_cli.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/eis_mcp/ai/__main__.py config/thresholds.yaml tests/eis_mcp/test_ai_cli.py
git commit -m "feat(ai): CLI to build snapshots/<month>/ai.json with Cambrian"
```

---

### Task 7: 讀 `ai.json` 並顯示在單案頁

**Files:**
- Modify: `src/eis_mcp/store.py`（`Store.ai_summary`）
- Create: `src/eis_mcp/web/pages_ai.py`
- Modify: `src/eis_mcp/web/routes.py`（單案頁組 `ai_html`）
- Modify: `src/eis_mcp/web/shell.py`（`WEB_CSS` 加 `.ai-note`）
- Test: `tests/eis_mcp/test_web.py`

**Interfaces:**
- Consumes: `build_groups`、`input_hash`（Task 2）；`project_body(..., ai_html=...)`（Task 1）
- Produces: `Store.ai_summary(month: str) -> dict | None`：沒有檔案回 `None`；壞 JSON 回 `{"unreadable": True}`
- Produces: `pages_ai.ai_section(month: str, p: dict, lm: int, doc: dict | None) -> str`

- [ ] **Step 1: 寫失敗的測試**

`tests/eis_mcp/test_web.py` 檔尾加（`set_project_fields` 已在 Task 1 定義）：

```python
# ---- AI 工作重點（2026-10-01）----
def ai_setup(app, groups_override=None, status="ok", model="LLAMA 3.3 70B"):
    """在快照第一個專案放 3 筆最新月 task，並寫一份與之相符的 ai.json。回傳 ai.json 路徑。"""
    from src.eis_mcp.ai.groups import build_groups, input_hash
    store = app.state.eis.store
    snap = store.load_snapshot("202609"); lm = snap["meta"]["latest_month"]
    tasks = [{"month": lm, "side": "BU", "function": "ME", "dept": "x", "fte": 1.0, "description": f"DVT-1 build issue {i}"} for i in range(3)]
    set_project_fields(app, tasks=tasks)
    p = store.load_snapshot("202609")["projects"][0]
    h = input_hash(lm, build_groups(p, lm, 5))
    groups = groups_override if groups_override is not None else [
        {"side": "BU", "function": "ME", "fte": 3.0, "n_tasks": 3, "theme": "DVT-1 build", "summary": "Handling <DVT-1> build issues.",
         "grounded": True, "note": ""}]
    doc = {"meta": {"report_month": "202609", "month": lm, "model": model, "prompt_version": "1", "max_groups": 5, "generated": "x"},
           "projects": {CODE: {"status": status, "reason": "status 500" if status == "failed" else "", "input_hash": h, "groups": groups}}}
    f = store.snapshot_dir("202609") / "ai.json"
    f.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return f


def test_ai_section_shows_groups_with_program_numbers(ingested):
    ai_setup(ingested)
    t = html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
    assert "Work this month (AI)" in t and "本月工作重點（AI）" in t
    assert "DVT-1 build" in t and "Handling &lt;DVT-1&gt; build issues." in t
    assert ">3.0<" in t and ">3<" in t and "LLAMA 3.3 70B" in t
    assert t.index("Work this month (AI)") < t.index("Milestones, plan vs actual, tasks")


def test_ai_section_out_of_date(ingested):
    ai_setup(ingested)
    snap = ingested.state.eis.store.load_snapshot("202609")
    tasks = snap["projects"][0]["tasks"]; tasks[0] = dict(tasks[0], description="changed after enrichment")
    set_project_fields(ingested, tasks=tasks)
    t = html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
    assert "out of date" in t and "Handling" not in t


def test_ai_section_failed_and_ungrounded(ingested):
    ai_setup(ingested, status="failed", groups_override=[])
    t = html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
    assert "could not be generated" in t and "status 500" in t
    ai_setup(ingested, groups_override=[{"side": "BU", "function": "ME", "fte": 3.0, "n_tasks": 3, "theme": "", "summary": "",
                                         "grounded": False, "note": "ungrounded"}])
    t = html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
    assert "did not pass the check" in t.lower()


def test_ai_section_absent_without_file_or_entry(ingested):
    t = html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
    assert "Work this month (AI)" not in t
    f = ai_setup(ingested)
    doc = json.loads(f.read_text(encoding="utf-8")); doc["projects"] = {}
    f.write_text(json.dumps(doc), encoding="utf-8")
    assert "Work this month (AI)" not in html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")


def test_ai_section_unreadable_file(ingested):
    f = ai_setup(ingested)
    f.write_text("{broken", encoding="utf-8")
    t = html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
    assert "unreadable" in t


def test_store_ai_summary(ingested):
    store = ingested.state.eis.store
    assert store.ai_summary("202609") is None
    f = ai_setup(ingested)
    assert store.ai_summary("202609")["projects"][CODE]["status"] == "ok"
    f.write_text("{broken", encoding="utf-8")
    assert store.ai_summary("202609") == {"unreadable": True}
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/eis_mcp/test_web.py -k "ai_section or store_ai_summary" -q`
Expected: FAIL（`Store` 沒有 `ai_summary`；頁面沒有 AI 區塊）

- [ ] **Step 3: 實作**

`src/eis_mcp/store.py`，在 `def report_html(` 之前加：

```python
    def ai_summary(self, month: str) -> dict | None:
        """選用的 AI 工作重點（snapshots/<月>/ai.json）。沒有檔案回 None；讀不出來回 {"unreadable": True}，網頁照常顯示並註明。"""
        f = self.snapshot_dir(month) / "ai.json"
        if not f.exists():
            return None
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"unreadable": True}
```

`src/eis_mcp/web/pages_ai.py`：

```python
"""單案頁的「本月工作重點（AI）」。數字（FTE、筆數）來自 ai.json 裡程式算好的值；LLM 只提供 theme 與 summary。
顯示前重算輸入雜湊：快照在摘要產生後被重新 ingest 過，就只說「已過期」，不顯示舊內容。"""
from __future__ import annotations
from html import escape as e
from ..ai.groups import build_groups, input_hash

ZH = "zh-Hant"
NOTE_TEXT = {
    "other": "Other functions, not summarized",
    "no_text": "No usable task descriptions",
    "ungrounded": "Did not pass the check; read the tasks below",
}


def _head(extra: str = "") -> str:
    return f'<section><h2>Work this month (AI) <span class="zh-inline" lang="{ZH}">本月工作重點（AI）</span></h2>{extra}'


def ai_section(month: str, p: dict, lm: int, doc: dict | None) -> str:
    if doc is None:
        return ""
    if doc.get("unreadable"):
        return _head('<p class="ai-note">The AI summary file is unreadable; ask the server owner to re-run it.</p>') + "</section>"
    meta = doc.get("meta", {})
    entry = doc.get("projects", {}).get(p["code"])
    if not entry or meta.get("report_month") != month:
        return ""
    if entry.get("status") != "ok":
        return _head(f'<p class="ai-note">The AI summary could not be generated: {e(entry.get("reason", ""))}.</p>') + "</section>"
    current = input_hash(lm, build_groups(p, lm, int(meta.get("max_groups", 5))))
    if current != entry.get("input_hash"):
        return _head(f'<p class="ai-note">This summary is out of date; re-run the AI summary for {e(month)}.</p>') + "</section>"
    rows = []
    for g in entry.get("groups", []):
        if g.get("note"):
            theme = f'<span class="dim">{e(NOTE_TEXT.get(g["note"], g["note"]))}</span>'
            summary = ""
        else:
            theme, summary = f'<b>{e(g.get("theme", ""))}</b>', e(g.get("summary", ""))
        rows.append(f'<tr><td>{theme}</td><td>{summary}</td><td>{e(g.get("side", ""))} · {e(g.get("function", ""))}</td>'
                    f'<td class="num">{float(g.get("fte", 0)):.1f}</td><td class="num">{int(g.get("n_tasks", 0))}</td></tr>')
    table = (f'<div class="wide"><table><thead><tr><th>Theme</th><th>Summary</th><th>Side · Function</th><th class="num">FTE</th>'
             f'<th class="num">Tasks</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
    note = (f'<p class="ai-note">AI summary by {e(meta.get("model", ""))}. FTE and task counts are computed from the Control List; '
            f'the model only names each group. Read the tasks below to check.'
            f'<span class="zh" lang="{ZH}">由 {e(meta.get("model", ""))} 產生。FTE 與筆數由程式從 Control List 計算，模型只替每群命名；請對照下方 task 原文。</span></p>')
    return _head() + table + note + "</section>"
```

`src/eis_mcp/web/routes.py`：檔頭 import 改成：

```python
from . import pages_ai, pages_home, pages_load, pages_mcp, pages_overview, pages_project
```

單案頁 handler（Task 1 改過的那行）改成：

```python
            ai_html = pages_ai.ai_section(month, p, snap["meta"]["latest_month"], state.store.ai_summary(month))
            body = pages_project.project_body(month, p, today, snap["meta"]["latest_month"], prev,
                                              snap_date=snap["meta"]["snap_date"], ai_html=ai_html)
```

`src/eis_mcp/web/shell.py`，在 Task 1 加的 `.status-text{...}` 那行之後加：

```css
.ai-note{color:var(--ink-2);font-size:12px;margin:6px 0 0;max-width:100ch}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/eis_mcp/store.py src/eis_mcp/web/pages_ai.py src/eis_mcp/web/routes.py src/eis_mcp/web/shell.py tests/eis_mcp/test_web.py
git commit -m "feat(web): show the AI work summary on the project page, with out-of-date detection"
```

---

### Task 8: 文件與部署說明

**Files:**
- Modify: `docs/eis-mcp-client-setup.md:11`
- Modify: `docs/eis-mcp-install.md:12`，並在檔尾新增一節
- Modify: `README.md`（§7.8 之後新增 7.9）
- Modify: `AGENTS.md`（「MCP server」段落）
- Modify: `deploy/env.example`（註解說明，不設值）
- Modify: `docs/superpowers/specs/2026-10-01-eis-llm-enrichment-design.md`（狀態改為已實作）
- Test: `tests/eis_mcp/test_web.py`（文件一致性）

**Interfaces:**
- Consumes: CLI 與 exit code（Task 6）

- [ ] **Step 1: 寫失敗的測試**

`tests/eis_mcp/test_web.py` 檔尾加：

```python
def test_docs_describe_the_optional_ai_step():
    from pathlib import Path
    setup = Path("docs/eis-mcp-client-setup.md").read_text(encoding="utf-8")
    install = Path("docs/eis-mcp-install.md").read_text(encoding="utf-8")
    assert "server 端不含任何 LLM" not in setup and "portfolio.json" in setup
    assert "python -m src.eis_mcp.ai" in install and "EIS_CAMBRIAN_TOKEN_FILE" in install
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/eis_mcp/test_web.py::test_docs_describe_the_optional_ai_step -q`
Expected: FAIL

- [ ] **Step 3: 修改文件**

`docs/eis-mcp-client-setup.md` 第 11 行 `server 端不含任何 LLM；模型在 client 端。` 改成：

```markdown
回答問題的模型在 client 端。server 的核心資料（`portfolio.json`）與所有 tool 回傳都不含 LLM 產出；單案網頁上選用的「本月工作重點（AI）」另存 `ai.json`，由管理者另外產生。
```

`docs/eis-mcp-install.md` 第 12 行改成：

```markdown
- **server 端執行查詢不需要任何 LLM、API key 或 AI 帳號**，只是一個 Python 服務；模型在使用者的 client 端。選用的 AI 工作重點需要 Cambrian token，見文末「AI 工作重點（選用）」。
```

`docs/eis-mcp-install.md` 檔尾新增：

````markdown
## AI 工作重點（選用，Cambrian）

單案頁的「本月工作重點（AI）」由獨立指令產生，**不影響 ingest**。不做這一步，網頁就不顯示這個區塊。

1. 先確認 VM 連得到 Cambrian：

   ```bash
   curl -sk -m 5 -o /dev/null -w "%{http_code}\n" https://api.cambrian.pegatroncorp.com/health   # 期待 200
   ```

2. 放 token（只有 eis 群組可讀）：

   ```bash
   sudo install -m 640 -o root -g eis /dev/null /etc/eis-mcp/cambrian_token
   sudo sh -c 'printf "%s" "<CAMBRIAN TOKEN>" > /etc/eis-mcp/cambrian_token'
   ```

3. 每月 ingest 之後執行（以 eis 身分）：

   ```bash
   sudo -u eis env EIS_CAMBRIAN_TOKEN_FILE=/etc/eis-mcp/cambrian_token \
     /opt/eis-mcp/.venv/bin/python -m src.eis_mcp.ai --data /var/lib/eis-mcp --month 202609
   ```

   可加 `--code BR0000xxxxxx`（額外納入的專案，可重複）、`--model "Qwen 2.5"`；`EIS_CAMBRIAN_VERIFY_SSL=1` 才驗證憑證。

| exit | 意義 |
|---|---|
| 0 | 寫入 `snapshots/<月>/ai.json` |
| 1 | 該月沒有可讀快照，先 ingest |
| 2 | token 檔缺或空；或輸出命中 PII（不寫檔） |
| 3 | 選到的專案全部呼叫失敗（仍寫檔，網頁顯示失敗原因） |

選案門檻在 `config/thresholds.yaml` 的 `portfolio.ai_min_task_rows`（預設最新月 task ≥100 筆）。重新 ingest 該月後要再跑一次，否則網頁會顯示「摘要已過期」。內容沒變的專案會沿用上次結果，不會重打 Cambrian。
````

`README.md`，在「### 7.8 網頁查詢（免登入、唯讀）」整節之後、「## 8. 已知限制」之前加：

```markdown
### 7.9 AI 工作重點（選用）

單案頁可顯示 Cambrian 產生的「本月工作重點」：程式依 side＋function 分群並計算 FTE，LLM 只替每群命名，含原文沒有的數字就丟掉。與 ingest 分開執行，結果存 `snapshots/<月>/ai.json`；`portfolio.json` 不含 LLM 產出。設定與指令見 `docs/eis-mcp-install.md` 的「AI 工作重點（選用）」。設計：`docs/superpowers/specs/2026-10-01-eis-llm-enrichment-design.md`。
```

`AGENTS.md`，「## MCP server（src/eis_mcp，2026-09-19 起）」段落最後加一行：

```markdown
- AI（2026-10-01）：`src/eis_mcp/ai/` 用 Cambrian 替大專案每月 task 分群命名，另存 `ai.json`。**LLM 不輸出數字**（FTE、筆數由程式算），含原文沒有的數字詞就清空；`portfolio.json`、`ingest_month`、所有 MCP tool 回傳都不含 LLM 產出。Briefing 狀態說明原文（含人名）直接顯示在單案頁，需求方 2026-10-01 裁定內網可顯示人名。
```

`deploy/env.example` 檔尾加：

```bash
# 選用：AI 工作重點（python -m src.eis_mcp.ai）讀這些變數；systemd 服務本身不需要。
# EIS_CAMBRIAN_TOKEN_FILE=/etc/eis-mcp/cambrian_token
# EIS_CAMBRIAN_URL=https://api.cambrian.pegatroncorp.com
# EIS_CAMBRIAN_MODEL=LLAMA 3.3 70B
# EIS_CAMBRIAN_VERIFY_SSL=0
```

`docs/superpowers/specs/2026-10-01-eis-llm-enrichment-design.md` 第 4 行狀態改成：

```markdown
狀態：已實作（計畫 docs/superpowers/plans/2026-10-01-eis-llm-enrichment.md）
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add docs/eis-mcp-client-setup.md docs/eis-mcp-install.md README.md AGENTS.md deploy/env.example docs/superpowers/specs/2026-10-01-eis-llm-enrichment-design.md tests/eis_mcp/test_web.py
git commit -m "docs: optional Cambrian AI work summary — setup, run command, exit codes"
```

---

### Task 9: 真資料端到端驗證（不 commit 程式）

**Files:** 無程式變更；輸出在 scratchpad。

- [ ] **Step 1: 用新版 Briefing 重建 202609 快照到暫存目錄**

```bash
S=$(mktemp -d); mkdir -p $S/in $S/data/snapshots
cp input-08/* $S/in/ && rm $S/in/BU10_Project_Briefing_20260907.xlsx && cp input-08-2/BU10_Project_Briefing_2026_v2.xlsx $S/in/
.venv/bin/python -m src.portfolio.cli --input $S/in --report-month 202609 --today 2026-09-29 --snapshots $S/data/snapshots --out $S/out
```

Expected: `wrote ... 62 projects`

- [ ] **Step 2: 確認狀態說明進了快照**

```bash
.venv/bin/python -c "import json,sys;s=json.load(open('$S/data/snapshots/202609/portfolio.json'));p=[x for x in s['projects'] if x['name'].upper()=='THORPE'][0];print(len(p['status_text']))"
```

Expected: `1737`

- [ ] **Step 3: 有 Cambrian token 時，對 6 案產生 AI 結果**

```bash
EIS_CAMBRIAN_TOKEN_FILE=~/.secrets/cambrian_token .venv/bin/python -m src.eis_mcp.ai --data $S/data --month 202609
```

Expected: `wrote .../ai.json: 6 project(s), 6 ok, 0 failed`。沒有 token 時跳過這步，並在回報中寫明「未以真 Cambrian 驗證」。

- [ ] **Step 4: 起 server 目視檢查單案頁（THORPE、Foxtrot14）**

```bash
chmod -R go-rwx $S/data
.venv/bin/python -m src.eis_mcp --data $S/data --host 127.0.0.1 --port 8795 &
open http://127.0.0.1:8795/ui/202609/projects/BR0000015346
```

Expected：THORPE 顯示「PM status」原文（含 9/30、9/22、9/7 三段與 Renee）；Foxtrot14 顯示「Work this month (AI)」表格（Step 3 有跑時）。桌面 1440px 與手機 375px 皆無橫向溢出。

---

## Self-Review 紀錄

- **Spec 覆蓋：** §1-1 狀態說明 → Task 1；§1-2 分群命名 → Task 2、5；§3 原則 1（LLM 不輸出數字）→ Task 4 只取 theme/summary、Task 5 數字來自 `Group`；原則 2 grounding → Task 3、5；原則 3 與 ingest 分離 → Task 6 獨立 CLI；原則 4 過期偵測 → Task 7；原則 5 快取 → Task 5；原則 6 標示 → Task 7 `ai-note`；§4.3 環境變數 → Task 6；§4.4 格式與 note → Task 5；§4.5 網頁 → Task 1、7；§5 錯誤處理每列 → Task 4（逾時/非 JSON/缺欄位）、Task 5（失敗隔離、ungrounded、PII）、Task 6（token、無快照、全部失敗）、Task 7（壞檔）；§7 文件修訂 → Task 8；§8 測試清單 → 各 Task Step 1。
- **Placeholder 掃描：** 無 TBD/TODO；每個程式步驟都有完整程式碼。`<CAMBRIAN TOKEN>` 是給操作者填的值，不是計畫缺漏。
- **型別一致：** `build_groups(project, month, max_groups)`、`input_hash(month, groups)` 在 Task 2、5、7 用法一致；`project_body(..., snap_date=, ai_html=)` 在 Task 1 定義、Task 7 使用；`Store.ai_summary` 回 `dict | None`，`{"unreadable": True}` 在 Task 7 測試與 `pages_ai` 一致；`meta.max_groups` 在 Task 5 寫入、Task 7 讀取。
- **Review Focus：** 五項各有對應測試（過期 → Task 7；失敗隔離與 exit 3 → Task 5、6；捏造數字 → Task 3、5、7；HTML 跳脫 → Task 1；舊快照與壞檔 → Task 1、7）。
