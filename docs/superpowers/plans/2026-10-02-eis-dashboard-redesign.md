# EIS Dashboard Redesign（v2 風格＋ECharts）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `/ui/` 網頁與月報單頁 HTML 改成 v2 儀表板風格（左側導覽、KPI 卡、ECharts 圖表），圖上每個數字仍指得回快照。

**Architecture:** 新套件 `src/portfolio/render/viz/`：`options.py` 把快照算成 `Chart`（ECharts option＋同一份數字的資料表），`embed.py` 把 `Chart` 嵌成 `<div data-chart>`＋`<script type="application/json">`＋`<details>` 表格，`dash.py` 提供 KPI 卡／卡片／狀態標籤／側欄等 HTML 積木。月報內嵌 ECharts，`/ui/` 以 `/ui/static/echarts.min.js` 提供同一份檔案。數字只在 Python 算；JS 只 `setOption`。

**Tech Stack:** Python 3.12+、Apache ECharts 5.6.0（vendor 進 repo，Apache-2.0）、Starlette（既有 `/ui/`）、pytest、Playwright（只用於 Task 9 的版面檢查腳本，已裝在 `.venv`）。

**Spec:** `docs/superpowers/specs/2026-10-02-eis-dashboard-redesign-design.md`

## Global Constraints

- 分支 `feat/dashboard-redesign`（從 `main` 開，已建立）；不 merge、不 push。
- ECharts 版本固定 **5.6.0**（npm `echarts@5.6.0`；npm `latest` 已是 6.x，spec 指定 5.x），`echarts.min.js` sha256 = `bf4a223524e40b77c304bec67e1222cf551f14880cf42c69dc046558e11c07b1`，1,034,102 bytes；不用 CDN。
- 月報：`echarts_tag("inline")` 內嵌整份 min.js；`/ui/`：`<script src="/ui/static/echarts.min.js">`，回應帶 `Cache-Control: public, max-age=86400`。
- 圖上的數字一律由 Python 算好放進 option JSON；option 裡的函式以 `{"$fn": "名稱"}` 表示，只能用 `INIT_JS` 內建的 `FN` 表。
- 資料缺口不得補 0：不在 Briefing 的專案、空白客戶、無人填報的月份、沒有 budget 的專案，都要獨立類別或註明。
- At Risk KPI 不新增規則：`exceptions[title=milestones_passed].codes` ∪ `rules.mp_slipped(…, th["mp_slip_days"])`。
- 新 UI 字串一律加在 `src/portfolio/render/strings.py`，key 以 `v_` 開頭（避免與既有 key 撞名），en 與 zh 同 key；en 字串不得含 `·`、`→`。
- 所有 HTML 輸出照舊整頁過 `find_pii`（網頁在 `respond()`，月報在 `pipeline.build_month`）。
- 測試指令：`.venv/bin/python -m pytest tests -q`；基線 243 passed；每個 Task 結尾全綠。
- 每個 Task 結尾 commit 一次，訊息結尾附兩行：
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` 與 `Claude-Session: https://claude.ai/code/session_012zEsMSfatMgvu1sX2iqCuY`。

## Review Focus

1. **部署漏檔**：`deploy/install.sh` 的 rsync 只放行 `src/ config/ scripts/ docs/`，`vendor/` 會被排除，server 因找不到 ECharts 拒絕啟動 → Task 6 `test_install_copies_vendor`。
2. **名稱字串跳出 script**：客戶或專案名含 `</script>` 或 `<!--`，嵌進 JSON 後提早關閉 `<script>` → Task 1 `test_to_json_cannot_close_script`、Task 7 `test_customer_name_cannot_break_the_page`。
3. **附錄的圖一開始是隱藏的**：`display:none` 時 ECharts 初始化寬度為 0，切換專案後是一條線 → `INIT_JS` 跳過不可見的圖、選單切換時呼叫 `eisCharts.init(...)`；Task 7 `test_appendix_picker_initialises_charts_when_shown`、Task 9 瀏覽器檢查。
4. **舊快照缺欄位**（例如沒有 `capacity`）：該圖顯示「Not in this snapshot.」，整頁仍 200 → Task 5 `test_safe_chart_card_reports_missing_data`、Task 7 `test_report_survives_snapshot_without_capacity`、Task 8 `test_overview_survives_snapshot_without_capacity`。
5. **沒有 JS 的讀者**（Outlook 預覽、列印）：每張圖都有同一份數字的資料表 → Task 7 `test_every_chart_has_a_data_table`。

---

### Task 1: Vendor ECharts、UI 字串、嵌入層（`embed.py`）

**Files:**
- Create: `vendor/echarts/echarts.min.js`、`vendor/echarts/LICENSE`、`vendor/echarts/NOTICE`、`vendor/echarts/VERSION`
- Create: `src/portfolio/render/viz/__init__.py`
- Create: `src/portfolio/render/viz/embed.py`
- Modify: `src/portfolio/render/strings.py`（en、zh 各加一段 `v_` 字串）
- Test: `tests/portfolio/test_viz_embed.py`

**Interfaces:**
- Produces: `Chart(id: str, title: str, option: dict, headers: tuple[str, ...], rows: tuple[tuple, ...], height: int = 280, variants: dict = {}, note: str = "")`（frozen dataclass）
- Produces: `ECHARTS_JS: Path`、`STATIC_URL = "/ui/static/echarts.min.js"`、`echarts_source() -> str`、`echarts_tag(mode: str) -> str`（`"inline"`｜`"static"`）、`scripts(mode: str) -> str`、`INIT_JS: str`
- Produces: `to_json(obj) -> str`、`chart_html(ch: Chart, lang: str) -> str`

- [ ] **Step 1: 放 ECharts 檔案**

```bash
SP=$(mktemp -d) && curl -sS -m 120 -o $SP/e.tgz https://registry.npmjs.org/echarts/-/echarts-5.6.0.tgz \
  && tar xzf $SP/e.tgz -C $SP package/dist/echarts.min.js package/LICENSE package/NOTICE \
  && mkdir -p vendor/echarts && cp $SP/package/dist/echarts.min.js $SP/package/LICENSE $SP/package/NOTICE vendor/echarts/ \
  && printf '5.6.0\n' > vendor/echarts/VERSION \
  && shasum -a 256 vendor/echarts/echarts.min.js && wc -c vendor/echarts/echarts.min.js
```

Expected：`bf4a2235…07b1  vendor/echarts/echarts.min.js` 與 `1034102`。sha256 不符就停下來，不要用別的版本。

- [ ] **Step 2: 加 UI 字串**

`src/portfolio/render/strings.py`：en 區塊中 `"foot_3": ...` 那一行之後加：

```python
        "v_menu": "Menu", "v_nav_overview": "Overview", "v_nav_decisions": "Decisions", "v_nav_health": "Data health", "v_nav_appendix": "Project appendix",
        "v_total": "Total", "v_kpi_total": "Total projects", "v_kpi_total_sub": "{briefed} in Briefing, {inactive} terminated or suspended",
        "v_kpi_rfq": "RFQ / RFI", "v_kpi_poc": "POC", "v_kpi_exec": "Execution", "v_kpi_mp": "MP + Sustain", "v_kpi_mp_sub": "{mp} MP, {sustain} sustain / EOP",
        "v_kpi_risk": "At risk", "v_kpi_risk_sub": "Milestone passed, or MP slipped over {days} days",
        "v_c_stage": "Projects by stage", "v_c_customer": "Projects by customer", "v_c_gantt": "Timeline, next {months} months",
        "v_c_heat": "Resource load by function", "v_c_heat_dept": "Resource load by department", "v_c_forecast": "Forecast vs capacity",
        "v_c_milestones": "Milestones, next {weeks} weeks",
        "v_cat_not_in_briefing": "Not in Briefing", "v_cat_blank": "(blank)", "v_cat_others": "Others", "v_no_data": "no data",
        "v_heat_note": "Load = allocated FTE / people who keyed in, not headcount. Grey cells: nobody keyed in.",
        "v_gantt_note": "Red marks a milestone that passed without a stage change. Terminated and suspended projects are not listed.",
        "v_today": "Today", "v_lg_cap": "Keyed-in BU headcount", "v_lg_cap_carried": "Headcount carried from {mon}",
        "v_lg_actual": "Actual, BU RD + PM", "v_lg_plan": "Budget plan, BU RD + PM", "v_lg_fu": "Actual, FU RD",
        "v_lg_pva_actual": "Actual", "v_lg_pva_plan": "Plan", "v_pva_no_plan": "No budget plan for this group.",
        "v_st_passed": "Passed", "v_st_due": "Due soon", "v_st_ok": "On track",
        "v_col_projects": "Projects", "v_col_month": "Month", "v_col_days": "Days left", "v_col_status": "Status",
        "v_data_table": "Data table", "v_need_js": "This chart needs JavaScript; the data table below has the same numbers.",
        "v_filter_customer": "Customer", "v_filter_all": "All", "v_not_in_snapshot": "Not in this snapshot.",
```

zh 區塊中 `"foot_3": ...` 那一行之後加：

```python
        "v_menu": "選單", "v_nav_overview": "總覽", "v_nav_decisions": "本月決策", "v_nav_health": "資料健康度", "v_nav_appendix": "各案附錄",
        "v_total": "合計", "v_kpi_total": "專案總數", "v_kpi_total_sub": "Briefing 內 {briefed} 案，結案或暫停 {inactive} 案",
        "v_kpi_rfq": "RFQ / RFI", "v_kpi_poc": "POC", "v_kpi_exec": "Execution", "v_kpi_mp": "MP + Sustain", "v_kpi_mp_sub": "MP {mp} 案，Sustain / EOP {sustain} 案",
        "v_kpi_risk": "風險", "v_kpi_risk_sub": "里程碑已過未轉階段，或 MP 延後超過 {days} 天",
        "v_c_stage": "各階段專案數", "v_c_customer": "各客戶專案數", "v_c_gantt": "未來 {months} 個月時程",
        "v_c_heat": "各 Function 負載", "v_c_heat_dept": "各部門負載", "v_c_forecast": "人力預估與產能",
        "v_c_milestones": "未來 {weeks} 週里程碑",
        "v_cat_not_in_briefing": "不在 Briefing", "v_cat_blank": "（空白）", "v_cat_others": "其他", "v_no_data": "無資料",
        "v_heat_note": "負載 = 分配 FTE ÷ 有填報的人數（不是編制）。灰格：無人填報。",
        "v_gantt_note": "紅色＝里程碑已過但階段未前進。結案與暫停的專案不列。",
        "v_today": "今天", "v_lg_cap": "BU 填報人數", "v_lg_cap_carried": "{mon} 之後沿用該月人數",
        "v_lg_actual": "實際，BU RD + PM", "v_lg_plan": "Budget，BU RD + PM", "v_lg_fu": "實際，FU RD",
        "v_lg_pva_actual": "實際", "v_lg_pva_plan": "計畫", "v_pva_no_plan": "這一組沒有 budget。",
        "v_st_passed": "已過", "v_st_due": "將到期", "v_st_ok": "正常",
        "v_col_projects": "專案數", "v_col_month": "月份", "v_col_days": "剩餘天數", "v_col_status": "狀態",
        "v_data_table": "資料表", "v_need_js": "圖表需要 JavaScript；下方資料表有相同數字。",
        "v_filter_customer": "客戶", "v_filter_all": "全部", "v_not_in_snapshot": "這份快照沒有這項資料。",
```

- [ ] **Step 3: 寫失敗的測試**

`tests/portfolio/test_viz_embed.py`：

```python
import json
import math
import re
import pytest
from src.portfolio.render.strings import STRINGS
from src.portfolio.render.viz.embed import ECHARTS_JS, INIT_JS, STATIC_URL, Chart, chart_html, echarts_source, echarts_tag, scripts, to_json


def ch(**kw):
    base = dict(id="stage", title="Projects by stage", option={"series": [{"type": "pie", "data": [{"name": "MP", "value": 3}]}]},
                headers=("Stage", "Projects"), rows=(("MP", 3), ("POC", None)))
    base.update(kw)
    return Chart(**base)


def test_vendored_echarts_is_the_pinned_build():
    assert ECHARTS_JS.is_file() and (ECHARTS_JS.parent / "VERSION").read_text().strip() == "5.6.0"
    src = echarts_source()
    assert "Apache Software Foundation" in src[:400] and "</script" not in src


def test_to_json_cannot_close_script_and_nan_is_null():
    s = to_json({"name": "</script><!--x", "v": math.nan, "w": [math.inf, 1.5]})
    assert "</" not in s and "<!--" not in s
    assert json.loads(s) == {"name": "</script><!--x", "v": None, "w": [None, 1.5]}


def test_chart_html_has_div_payload_noscript_and_table():
    h = chart_html(ch(note="Budget covers 1 / 2"), "en")
    assert '<div class="chart" id="c-stage" data-chart style="height:280px" role="img" aria-label="Projects by stage">' in h
    payload = re.search(r'<script type="application/json" id="c-stage-data">(.*?)</script>', h).group(1)
    assert json.loads(payload)["option"]["series"][0]["data"][0]["value"] == 3
    assert "<noscript>" in h and "needs JavaScript" in h and "Budget covers 1 / 2" in h
    table = h[h.index('<details class="data">'):]
    assert "<td>MP</td><td>3</td>" in table and "<td>POC</td><td>–</td>" in table
    assert "data-variant-for" not in h


def test_variants_render_a_customer_filter():
    h = chart_html(ch(id="gantt", variants={"Dell": {"series": []}, "Trimble": {"series": []}}), "en")
    assert '<select data-variant-for="c-gantt">' in h and '<option value="Dell">Dell</option>' in h and '<option value="">All</option>' in h


def test_echarts_tags_and_init_script():
    assert echarts_tag("static") == f'<script src="{STATIC_URL}"></script>'
    assert echarts_tag("inline").startswith("<script>") and len(echarts_tag("inline")) > 1_000_000   # min.js 第一個字元是換行
    with pytest.raises(ValueError):
        echarts_tag("cdn")
    assert "window.eisCharts" in INIT_JS and "offsetParent" in INIT_JS and "$fn" in INIT_JS
    assert scripts("static").endswith(f"<script>{INIT_JS}</script>")


def test_new_strings_exist_in_both_languages():
    v_en = {k for k in STRINGS["en"] if k.startswith("v_")}
    assert v_en and v_en == {k for k in STRINGS["zh"] if k.startswith("v_")}
```

- [ ] **Step 4: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/portfolio/test_viz_embed.py -q`
Expected: FAIL（`ModuleNotFoundError: src.portfolio.render.viz`）

- [ ] **Step 5: 實作**

`src/portfolio/render/viz/__init__.py`：

```python
"""v2 儀表板：快照 → ECharts option（options.py）→ 嵌入 HTML（embed.py）→ 版面積木（dash.py）。數字只在 Python 算。"""
```

`src/portfolio/render/viz/embed.py`：

```python
"""ECharts 嵌入。圖的數字在 Python 算好，以 JSON 放進頁面，JS 只負責畫；沒有 JS 時同一份數字在 <details> 表格裡。"""
from __future__ import annotations
import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from html import escape as e
from pathlib import Path
from ..strings import t

ECHARTS_DIR = Path(__file__).resolve().parents[4] / "vendor" / "echarts"
ECHARTS_JS = ECHARTS_DIR / "echarts.min.js"
STATIC_URL = "/ui/static/echarts.min.js"


@dataclass(frozen=True)
class Chart:
    id: str                                   # 頁內唯一，只用 [a-z0-9-]
    title: str
    option: dict                              # ECharts option；函式寫成 {"$fn": 名稱}，由 INIT_JS 換成 FN 表裡的函式
    headers: tuple[str, ...]                  # 資料表欄名
    rows: tuple[tuple, ...]                   # 資料表內容，與 option 同一份計算結果
    height: int = 280
    variants: dict = field(default_factory=dict)   # {篩選標籤: option}；空 = 不提供篩選
    note: str = ""                            # 圖下方一行口徑／缺口說明


INIT_JS = """(function(){
if(typeof echarts==='undefined')return;
var FN={ganttBar:function(params,api){var s=api.coord([api.value(1),api.value(0)]),f=api.coord([api.value(2),api.value(0)]),h=api.size([0,1])[1]*0.3;
return{type:'rect',shape:{x:s[0],y:s[1]-h/2,width:Math.max(f[0]-s[0],2),height:h},style:{fill:api.visual('color'),opacity:0.3}};}};
function revive(o){if(Array.isArray(o))return o.map(revive);if(o&&typeof o==='object'){if(typeof o.$fn==='string')return FN[o.$fn];var r={};for(var k in o)r[k]=revive(o[k]);return r;}return o;}
var live=[];
function init(root){(root||document).querySelectorAll('[data-chart]').forEach(function(el){
if(el._ec||el.offsetParent===null)return;
var d=JSON.parse(document.getElementById(el.id+'-data').textContent);
el._d=d;el._ec=echarts.init(el,null,{renderer:'svg'});el._ec.setOption(revive(d.option));live.push(el._ec);});}
document.addEventListener('change',function(ev){var s=ev.target;if(!s||!s.getAttribute||!s.getAttribute('data-variant-for'))return;
var el=document.getElementById(s.getAttribute('data-variant-for'));if(!el||!el._ec)return;
el._ec.setOption(revive((s.value&&el._d.variants[s.value])||el._d.option),true);});
window.addEventListener('resize',function(){live.forEach(function(c){c.resize();});});
window.eisCharts={init:init};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',function(){init();});else init();
})();"""


@lru_cache(maxsize=1)
def echarts_source() -> str:
    if not ECHARTS_JS.is_file():
        raise FileNotFoundError(f"ECharts bundle missing: {ECHARTS_JS}")
    return ECHARTS_JS.read_text(encoding="utf-8")


def echarts_tag(mode: str) -> str:
    if mode == "inline":
        return f"<script>{echarts_source()}</script>"
    if mode == "static":
        return f'<script src="{STATIC_URL}"></script>'
    raise ValueError(f"unknown echarts mode: {mode}")


def scripts(mode: str) -> str:
    return echarts_tag(mode) + f"<script>{INIT_JS}</script>"


def _clean(v):
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    return v


def to_json(obj) -> str:
    """嵌進 <script type="application/json"> 的 JSON：NaN/inf 轉 null；「</」與「<!--」跳脫，資料無法提前關閉 script。"""
    s = json.dumps(_clean(obj), ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return s.replace("</", "<\\/").replace("<!--", "\\u003c!--")


def _cell(v) -> str:
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return e(str(v))


def chart_html(ch: Chart, lang: str) -> str:
    pick = ""
    if ch.variants:
        opts = "".join(f'<option value="{e(k)}">{e(k)}</option>' for k in ch.variants)
        pick = (f'<label class="pick">{e(t(lang, "v_filter_customer"))} <select data-variant-for="c-{ch.id}">'
                f'<option value="">{e(t(lang, "v_filter_all"))}</option>{opts}</select></label>')
    note = f'<p class="note">{e(ch.note)}</p>' if ch.note else ""
    head = "".join(f"<th>{e(h)}</th>" for h in ch.headers)
    body = "".join("<tr>" + "".join(f"<td>{_cell(v)}</td>" for v in r) + "</tr>" for r in ch.rows)
    return (f'{pick}<div class="chart" id="c-{ch.id}" data-chart style="height:{ch.height}px" role="img" aria-label="{e(ch.title)}"></div>'
            f'<script type="application/json" id="c-{ch.id}-data">{to_json({"option": ch.option, "variants": ch.variants})}</script>'
            f'<noscript><p class="note">{e(t(lang, "v_need_js"))}</p></noscript>{note}'
            f'<details class="data"><summary data-expand="{e(t(lang, "expand"))}" data-collapse="{e(t(lang, "collapse"))}"><span>{e(t(lang, "v_data_table"))}</span></summary>'
            f'<div class="wide"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></details>')
```

- [ ] **Step 6: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/portfolio/test_viz_embed.py tests/portfolio/test_strings.py -q`
Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
git add vendor/echarts src/portfolio/render/viz/__init__.py src/portfolio/render/viz/embed.py src/portfolio/render/strings.py tests/portfolio/test_viz_embed.py
git commit -m "feat(viz): vendor ECharts 5.6.0 and the chart embedding layer"
```

---

### Task 2: 設計 token 與分布圖（KPI、Stage、Customer）

**Files:**
- Create: `src/portfolio/render/viz/tokens.py`
- Create: `src/portfolio/render/viz/options.py`
- Test: `tests/portfolio/test_viz_options.py`

**Interfaces:**
- Consumes: `Chart`（Task 1）；`rules.mp_slipped`、`entities.INACTIVE/MONTHS`（既有）
- Produces: `tokens`：`BG, CARD, INK, INK2, INK3, RULE, SIDE, ACCENT, SIGNAL, BAD, WARN, OK, NODATA, PLAN, FU, HEAT_LOW, HEAT_MID, HEAT_HI, HEAT_HIGH, NOT_IN_BRIEFING, STAGE_COLORS`
- Produces: `late_codes(snap) -> set[str]`、`at_risk_codes(snap, mp_slip_days: int) -> list[str]`、`kpis(snap, lang, th) -> list[dict]`（每項 `{key, label, value, sub, tone}`，risk 另有 `codes`）、`stage_donut(snap, lang) -> Chart`、`customer_bars(snap, lang, top: int = 8) -> Chart`

- [ ] **Step 1: 寫失敗的測試**

`tests/portfolio/test_viz_options.py`：

```python
from src.portfolio.entities import Exception_, PlanVsActual, Project
from src.portfolio.model.load import DeptLoad
from src.portfolio.model.snapshot import build_snapshot
from src.portfolio.render.viz import options as O

TH = {"mp_slip_days": 60, "spare_capacity_pct": 85, "upcoming_weeks": 8, "timeline_months": 6}
TODAY = "2026-09-12"


def snap():
    a = Project(code="BR1", name="THORPE", stage="PVT", stage_cat="Execution", customer="Trimble", in_briefing=True, in_control_list=True, has_plan=True)
    a.dates.update({"kickoff": "2024-04-02", "pvt": "2026-09-08", "mp": "2026-10-20", "mp_orig": "2026-06-01"})
    a.pva = {"BU RD": PlanVsActual("BU RD", plan=[10] * 12, actual=[9] * 8 + [0] * 4), "PM": PlanVsActual("PM", plan=[1] * 12, actual=[1] * 8 + [0] * 4),
             "FU RD": PlanVsActual("FU RD", actual=[2] * 8 + [0] * 4)}
    b = Project(code="BR2", name="TOMY", stage="RFQ", stage_cat="RFQ / RFI", customer="Trimble", in_briefing=True)
    c = Project(code="BR3", name="Q11", stage="suspended", stage_cat="Suspended", customer="TBD", in_briefing=True)
    c.dates.update({"evt": "2026-09-20"})
    d = Project(code="BR4", name="AX200", stage="MP", stage_cat="MP", customer="Axelera", in_briefing=True)
    d.dates.update({"pvt": "2026-09-08", "mp": "2026-10-30"})
    e = Project(code="BR5", name="KOS", stage="Terminate", stage_cat="Terminated", customer="NA", in_briefing=True)
    f = Project(code="TR_KOS", name="TR_BU10_IPC_KOS", in_control_list=True)
    f.pva = {"BU RD": PlanVsActual("BU RD", actual=[3] * 8 + [0] * 4)}
    g = Project(code="BR6", name="N1X", stage="EVT", stage_cat="Execution", customer="Dell", in_briefing=True)
    g.dates.update({"pvt": "2026-09-02"})
    ex = [Exception_(1, "milestones_passed", "N1X PVT 2026-09-02 (+10d, stage EVT)", "milestones_passed", "briefing", ["BR6"], count=1)]
    loads = [DeptLoad("D1", "研發一課", "ME", keyed_in=[4] * 8 + [0] * 4, allocated=[4.0] * 8 + [0.0] * 4),
             DeptLoad("D2", "研發二課", "ME", keyed_in=[6] * 8 + [0] * 4, allocated=[3.0] * 8 + [0.0] * 4),
             DeptLoad("D3", "測試課", "QTC")]
    return build_snapshot("202609", 8, "20260907", TODAY, [a, b, c, d, e, f, g], loads, [10] * 8 + [0] * 4, ex, [], [])


def test_kpis_and_at_risk_reuse_existing_rules():
    k = {x["key"]: x for x in O.kpis(snap(), "en", TH)}
    assert k["total"]["value"] == 7 and k["total"]["sub"] == "6 in Briefing, 2 terminated or suspended"
    assert (k["rfq"]["value"], k["poc"]["value"], k["exec"]["value"], k["mp"]["value"]) == (1, 0, 2, 1)
    assert k["mp"]["sub"] == "1 MP, 0 sustain / EOP"
    assert k["risk"]["codes"] == ["BR6", "BR1"] and k["risk"]["value"] == 2 and k["risk"]["tone"] == "bad"   # passed ∪ mp slipped 141d
    assert O.late_codes(snap()) == {"BR6"}


def test_stage_donut_keeps_not_in_briefing_as_its_own_slice():
    ch = O.stage_donut(snap(), "en")
    data = ch.option["series"][0]["data"]
    assert [d["name"] for d in data] == ["RFQ / RFI  1", "Execution  2", "MP  1", "Terminated  1", "Suspended  1", "Not in Briefing  1"]
    assert sum(d["value"] for d in data) == 7 and ch.option["title"]["text"] == "7"
    assert ch.rows[-1] == ("Not in Briefing", 1, "14%")


def test_customer_bars_keep_blank_and_na_separate_and_fold_the_tail():
    ch = O.customer_bars(snap(), "en")
    assert dict(ch.rows) == {"Trimble": 2, "(blank)": 1, "Axelera": 1, "Dell": 1, "NA": 1, "TBD": 1}
    assert ch.option["yAxis"]["data"][-1] == "Trimble"                      # 最大的在最上面
    top3 = O.customer_bars(snap(), "en", top=3)
    assert top3.rows == (("Trimble", 2), ("(blank)", 1), ("Axelera", 1), ("Others", 3))
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/portfolio/test_viz_options.py -q`
Expected: FAIL（`ImportError: cannot import name 'options'`）

- [ ] **Step 3: 實作**

`src/portfolio/render/viz/tokens.py`：

```python
"""設計 token：CSS 與 ECharts option 共用同一份顏色，兩邊不會漂移。"""
BG, CARD, INK, INK2, INK3, RULE = "#F3F5F8", "#FFFFFF", "#1F2937", "#5B6475", "#9AA3AF", "#E3E7EE"
SIDE, ACCENT, SIGNAL = "#1E2735", "#2563EB", "#E8590C"
BAD, WARN, OK, NODATA = "#DC2626", "#F59E0B", "#16A34A", "#E5E7EB"
PLAN, FU = "#93C5FD", "#0D9488"
HEAT_LOW, HEAT_MID, HEAT_HI = "#BBF7D0", "#FDE68A", "#FCA5A5"
HEAT_HIGH = 95          # 熱度表紅色門檻（顯示用色階，不是規則；低門檻沿用 thresholds 的 spare_capacity_pct）
NOT_IN_BRIEFING = "Not in Briefing"
STAGE_COLORS = {"RFQ / RFI": "#F59E0B", "POC": "#0EA5E9", "Execution": "#2563EB", "MP": "#16A34A", "Sustain / EOP": "#64748B",
                "Terminated": "#9CA3AF", "Suspended": "#7C3AED", "Other": "#A8A29E", NOT_IN_BRIEFING: "#D1D5DB"}
```

`src/portfolio/render/viz/options.py`：

```python
"""快照 → 圖（Chart）。只讀 snapshot dict；數字全部在這裡算好，圖與資料表共用同一份結果。"""
from __future__ import annotations
from types import SimpleNamespace
from ...entities import INACTIVE
from ...model.rules import mp_slipped
from ..strings import t
from . import tokens as T
from .embed import Chart

STAGE_ORDER = ("RFQ / RFI", "POC", "Execution", "MP", "Sustain / EOP", "Terminated", "Suspended", "Other")


def late_codes(snap: dict) -> set[str]:
    return {c for x in snap.get("exceptions", []) if x["title"] == "milestones_passed" for c in x["codes"]}


def at_risk_codes(snap: dict, mp_slip_days: int) -> list[str]:
    """不是新規則：Decisions 的 milestones_passed ∪ 健康度的 mp_slipped（同一個 rules 函式）。"""
    passed = [c for x in snap.get("exceptions", []) if x["title"] == "milestones_passed" for c in x["codes"]]
    slipped = [p.code for p, _ in mp_slipped([SimpleNamespace(**p) for p in snap["projects"]], mp_slip_days)]
    return list(dict.fromkeys(passed + slipped))


def kpis(snap: dict, lang: str, th: dict) -> list[dict]:
    ps = snap["projects"]
    cat = lambda c: sum(1 for p in ps if p["stage_cat"] == c)  # noqa: E731
    risk = at_risk_codes(snap, th["mp_slip_days"])
    k = lambda key, label, value, sub="", tone="": {"key": key, "label": label, "value": value, "sub": sub, "tone": tone}  # noqa: E731
    return [k("total", t(lang, "v_kpi_total"), len(ps), t(lang, "v_kpi_total_sub", briefed=sum(1 for p in ps if p["in_briefing"]),
                                                          inactive=sum(1 for p in ps if p["stage_cat"] in INACTIVE))),
            k("rfq", t(lang, "v_kpi_rfq"), cat("RFQ / RFI")), k("poc", t(lang, "v_kpi_poc"), cat("POC")),
            k("exec", t(lang, "v_kpi_exec"), cat("Execution")),
            k("mp", t(lang, "v_kpi_mp"), cat("MP") + cat("Sustain / EOP"), t(lang, "v_kpi_mp_sub", mp=cat("MP"), sustain=cat("Sustain / EOP"))),
            {**k("risk", t(lang, "v_kpi_risk"), len(risk), t(lang, "v_kpi_risk_sub", days=th["mp_slip_days"]), "bad" if risk else ""), "codes": risk}]


def _stage_key(p: dict) -> str:
    if not p["in_briefing"]:
        return T.NOT_IN_BRIEFING
    return p["stage_cat"] or "Other"


def stage_donut(snap: dict, lang: str) -> Chart:
    counts: dict[str, int] = {}
    for p in snap["projects"]:
        key = _stage_key(p)
        counts[key] = counts.get(key, 0) + 1
    known = (*STAGE_ORDER, T.NOT_IN_BRIEFING)
    order = [k for k in known if counts.get(k)] + sorted(k for k in counts if k not in known)
    label = lambda k: t(lang, "v_cat_not_in_briefing") if k == T.NOT_IN_BRIEFING else k  # noqa: E731
    total = len(snap["projects"])
    data = [{"name": f"{label(k)}  {counts[k]}", "value": counts[k], "itemStyle": {"color": T.STAGE_COLORS.get(k, T.INK3)}} for k in order]
    option = {"tooltip": {"trigger": "item", "formatter": "{b} ({d}%)"},
              "legend": {"orient": "vertical", "right": 0, "top": "middle", "itemWidth": 10, "itemHeight": 10, "textStyle": {"color": T.INK2}},
              "title": {"text": str(total), "subtext": t(lang, "v_total"), "left": "29%", "top": "36%", "textAlign": "center",
                        "textStyle": {"fontSize": 26, "fontWeight": 700, "color": T.INK}, "subtextStyle": {"color": T.INK2}},
              "series": [{"type": "pie", "radius": ["52%", "74%"], "center": ["30%", "50%"], "label": {"show": False}, "data": data}]}
    rows = tuple((label(k), counts[k], f"{counts[k] / max(total, 1) * 100:.0f}%") for k in order)
    return Chart("stage", t(lang, "v_c_stage"), option, (t(lang, "col_stage"), t(lang, "v_col_projects"), "%"), rows, height=240)


def customer_bars(snap: dict, lang: str, top: int = 8) -> Chart:
    counts: dict[str, int] = {}
    for p in snap["projects"]:
        c = (p.get("customer") or "").strip() or t(lang, "v_cat_blank")
        counts[c] = counts.get(c, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].casefold()))
    head = list(ranked[:top])
    if ranked[top:]:
        head.append((t(lang, "v_cat_others"), sum(n for _, n in ranked[top:])))
    option = {"grid": {"left": 8, "right": 36, "top": 4, "bottom": 4, "containLabel": True}, "tooltip": {"trigger": "item"},
              "xAxis": {"type": "value", "show": False},
              "yAxis": {"type": "category", "data": [k for k, _ in head][::-1], "axisTick": {"show": False}, "axisLine": {"show": False},
                        "axisLabel": {"color": T.INK}},
              "series": [{"type": "bar", "data": [n for _, n in head][::-1], "barWidth": 12, "itemStyle": {"color": T.ACCENT, "borderRadius": [0, 3, 3, 0]},
                          "label": {"show": True, "position": "right", "color": T.INK}}]}
    return Chart("customer", t(lang, "v_c_customer"), option, (t(lang, "col_customer"), t(lang, "v_col_projects")), tuple(head),
                 height=max(160, 26 * len(head) + 20))
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/portfolio/test_viz_options.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/render/viz/tokens.py src/portfolio/render/viz/options.py tests/portfolio/test_viz_options.py
git commit -m "feat(viz): KPI counts, stage donut and customer bars from the snapshot"
```

---

### Task 3: 六個月 Gantt（`gantt`）

**Files:**
- Modify: `src/portfolio/render/viz/options.py`
- Test: `tests/portfolio/test_viz_options.py`

**Interfaces:**
- Consumes: `snap()`、`TODAY`（Task 2 測試檔）；`charts._add_months`（既有）
- Produces: `gantt(snap, lang, today: str, months: int) -> Chart`（id `gantt`；`variants` 以客戶為鍵；列順序同舊 `timeline_svg`）

- [ ] **Step 1: 寫失敗的測試**

`tests/portfolio/test_viz_options.py` 檔尾加：

```python
def test_gantt_rows_markers_and_customer_variants():
    ch = O.gantt(snap(), "en", TODAY, 6)
    assert ch.option["yAxis"]["data"] == ["TOMY", "AX200", "THORPE", "N1X"]      # 依里程碑先後；第一列在最上面
    assert [r[0] for r in ch.rows] == ["N1X", "THORPE", "AX200", "TOMY"]         # Q11（暫停）、KOS（結案）、不在 Briefing 的都不列
    marks = ch.option["series"][1]["data"]
    n1x = next(m for m in marks if m["label"]["formatter"] == "PVT 09/02")
    assert n1x["itemStyle"]["color"] == "#DC2626"                                 # 已過且階段未前進 → 紅
    thorpe = next(m for m in marks if m["label"]["formatter"] == "PVT 09/08")
    assert thorpe["itemStyle"]["color"] == "#2563EB"                              # 已過但不在 milestones_passed → 不標紅
    assert any(m["label"]["formatter"] == "RFQ, no dates yet" for m in marks)
    assert ch.option["series"][0]["renderItem"] == {"$fn": "ganttBar"}
    assert set(ch.variants) == {"Axelera", "Dell", "Trimble"}
    assert ch.variants["Trimble"]["yAxis"]["data"] == ["TOMY", "THORPE"]
    assert ch.note.startswith("Red marks a milestone")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/portfolio/test_viz_options.py::test_gantt_rows_markers_and_customer_variants -q`
Expected: FAIL（`AttributeError: module ... has no attribute 'gantt'`）

- [ ] **Step 3: 實作**

`src/portfolio/render/viz/options.py`：import 區改成：

```python
from __future__ import annotations
import datetime as dt
from types import SimpleNamespace
from ...entities import INACTIVE
from ...model.rules import mp_slipped
from ..charts import _add_months
from ..strings import t
from . import tokens as T
from .embed import Chart
```

檔尾加：

```python
MS = ("evt", "dvt", "pvt", "mp")
SYMBOL = {"evt": "emptyRect", "dvt": "rect", "pvt": "triangle", "mp": "circle"}


def _ms(iso: str) -> int:
    """日期 → UTC 午夜毫秒（ECharts time 軸）。"""
    return int(dt.datetime.fromisoformat(iso[:10]).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def _gantt_rows(snap: dict, today: str, months: int) -> tuple[dt.date, dt.date, list[dict]]:
    """與舊 timeline_svg 同一個選列條件：在 Briefing、非結案／暫停，且視窗內有里程碑，或是還沒有 MP 日期的 RFQ / RFI。"""
    t0 = dt.date.fromisoformat(today[:7] + "-01")
    t1 = _add_months(t0, months)
    in_win = lambda s: bool(s) and t0 <= dt.date.fromisoformat(s) < t1  # noqa: E731
    rows = [p for p in snap["projects"] if p["in_briefing"] and p["stage_cat"] not in INACTIVE
            and (any(in_win(p["dates"].get(k)) for k in MS) or (p["stage_cat"] == "RFQ / RFI" and not p["dates"].get("mp")))]
    rows.sort(key=lambda p: (p["dates"].get("mp") or p["dates"].get("pvt") or p["dates"].get("dvt") or p["dates"].get("evt") or "9", p["name"].casefold()))
    return t0, t1, rows


def _gantt_option(rows: list[dict], t0: dt.date, t1: dt.date, today: str, late: set[str], lang: str) -> dict:
    n = len(rows)
    bars, marks = [], []
    for i, p in enumerate(rows):
        y = n - 1 - i
        ds = [p["dates"][k] for k in ("kickoff", *MS) if p["dates"].get(k)]
        if len(ds) >= 2:
            bars.append([y, _ms(min(ds)), _ms(max(ds))])
        for k in MS:
            d = p["dates"].get(k)
            if not d or not t0 <= dt.date.fromisoformat(d) < t1:
                continue
            c = T.BAD if p["code"] in late and d < today else T.ACCENT
            marks.append({"value": [_ms(d), y], "symbol": SYMBOL[k], "symbolSize": 10, "itemStyle": {"color": c, "borderColor": c},
                          "label": {"show": True, "position": "right", "formatter": f"{k.upper()} {d[5:7]}/{d[8:10]}", "color": c, "fontSize": 11}})
        if not ds:
            marks.append({"value": [_ms(today), y], "symbol": "none",
                          "label": {"show": True, "position": "right", "formatter": t(lang, "no_dates", stage=p["stage"]), "color": T.INK3, "fontSize": 11}})
    return {"grid": {"left": 8, "right": 90, "top": 28, "bottom": 8, "containLabel": True}, "tooltip": {"trigger": "item"},
            "xAxis": {"type": "time", "position": "top", "min": _ms(t0.isoformat()), "max": _ms(t1.isoformat()),
                      "splitLine": {"show": True, "lineStyle": {"color": T.RULE}}, "axisLabel": {"color": T.INK2}},
            "yAxis": {"type": "category", "data": [p["name"] for p in rows][::-1], "axisTick": {"show": False},
                      "axisLabel": {"color": T.INK, "fontWeight": 600}},
            "series": [{"type": "custom", "renderItem": {"$fn": "ganttBar"}, "encode": {"x": [1, 2], "y": 0}, "data": bars,
                        "itemStyle": {"color": T.ACCENT}, "clip": True, "silent": True},
                       {"type": "scatter", "data": marks, "clip": True, "z": 3,
                        "markLine": {"silent": True, "symbol": "none", "lineStyle": {"color": T.INK, "type": "dashed"},
                                     "label": {"formatter": t(lang, "v_today"), "color": T.INK2}, "data": [{"xAxis": _ms(today)}]}}]}


def gantt(snap: dict, lang: str, today: str, months: int) -> Chart:
    t0, t1, rows = _gantt_rows(snap, today, months)
    late = late_codes(snap)
    customers = sorted({p["customer"] for p in rows if p["customer"]}, key=str.casefold)
    variants = {c: _gantt_option([p for p in rows if p["customer"] == c], t0, t1, today, late, lang) for c in customers}
    table = tuple((p["name"], p["customer"], p["stage"], *(p["dates"].get(k) or "" for k in MS)) for p in rows)
    return Chart("gantt", t(lang, "v_c_gantt", months=months), _gantt_option(rows, t0, t1, today, late, lang),
                 (t(lang, "col_project"), t(lang, "col_customer"), t(lang, "col_stage"), "EVT", "DVT", "PVT", "MP"), table,
                 height=max(160, 30 * len(rows) + 50), variants=variants, note=t(lang, "v_gantt_note"))
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/portfolio/test_viz_options.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/render/viz/options.py tests/portfolio/test_viz_options.py
git commit -m "feat(viz): six-month gantt with late markers and a customer filter"
```

---

### Task 4: 熱度表、Forecast vs Capacity、單案 PVA

**Files:**
- Modify: `src/portfolio/render/viz/options.py`
- Test: `tests/portfolio/test_viz_options.py`

**Interfaces:**
- Consumes: `charts._sum`、`charts.carry_forward`（既有）
- Produces: `load_heatmap(snap, lang, spare_pct: float, by: str = "function") -> Chart`（id `heat-function`｜`heat-dept`；`series[0]` 有資料的格、`series[1]` 無人填報的格）
- Produces: `forecast_capacity(snap, lang) -> Chart`（id `forecast`）
- Produces: `pva(p: dict, role: str, latest_month: int, lang: str, idx: int) -> Chart`（id `pva-{idx}-{role 去空白小寫}`，例如 `pva-0-burd`）

- [ ] **Step 1: 寫失敗的測試**

`tests/portfolio/test_viz_options.py` 檔尾加：

```python
def test_heatmap_by_function_never_shows_missing_months_as_zero():
    ch = O.load_heatmap(snap(), "en", 85)
    assert ch.id == "heat-function" and ch.option["yAxis"]["data"] == ["QTC", "ME"]
    cells, nodata = ch.option["series"][0]["data"], ch.option["series"][1]["data"]
    assert cells == [[m, 1, 70] for m in range(8)]                       # (4+3)/(4+6) = 70%
    assert len(nodata) == 16 and [9, 1, 0] in nodata and all(c[1] == 0 or c[0] >= 8 for c in nodata)
    assert ch.rows[0] == ("ME", *([70] * 8), None, None, None, None) and ch.rows[1] == ("QTC", *([None] * 12))
    pieces = ch.option["visualMap"]["pieces"]
    assert pieces[0]["lt"] == 85 and pieces[2]["gte"] == 95
    assert "not headcount" in ch.note


def test_heatmap_by_department_has_one_row_per_department():
    ch = O.load_heatmap(snap(), "en", 85, by="dept")
    assert ch.id == "heat-dept" and ch.option["yAxis"]["data"] == ["QTC  測試課", "ME  研發二課", "ME  研發一課"]


def test_forecast_capacity_series_and_budget_coverage():
    ch = O.forecast_capacity(snap(), "en")
    s = {x["name"]: x["data"] for x in ch.option["series"]}
    assert s["Keyed-in BU headcount"] == [10] * 8 + [None] * 4
    assert s["Headcount carried from Aug"] == [None] * 7 + [10] * 5
    assert s["Actual, BU RD + PM"] == [13.0] * 8 + [None] * 4         # THORPE 9+1、TR_KOS 3
    assert s["Budget plan, BU RD + PM"] == [11.0] * 12                 # 只有 has_plan 的 THORPE
    assert s["Actual, FU RD"] == [2.0] * 8 + [None] * 4
    assert ch.note == "Budget covers 1 / 2 projects, BU RD + PM only"
    assert ch.rows[8] == ("Sep", None, None, 11.0, None)


def test_pva_without_plan_draws_actual_only_and_says_so():
    ps = {p["code"]: p for p in snap()["projects"]}
    with_plan = O.pva(ps["BR1"], "BU RD", 8, "en", 0)
    assert with_plan.id == "pva-0-burd" and len(with_plan.option["series"]) == 2 and with_plan.note == ""
    no_plan = O.pva(ps["TR_KOS"], "BU RD", 8, "en", 5)
    assert no_plan.id == "pva-5-burd" and len(no_plan.option["series"]) == 1 and no_plan.note == "No budget plan for this group."
    assert no_plan.option["series"][0]["data"] == [3.0] * 8 + [None] * 4
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/portfolio/test_viz_options.py -q`
Expected: FAIL（`load_heatmap`／`forecast_capacity`／`pva` 不存在）

- [ ] **Step 3: 實作**

`src/portfolio/render/viz/options.py`：import 區把 `from ...entities import INACTIVE` 改成 `from ...entities import INACTIVE, MONTHS`，把 `from ..charts import _add_months` 改成 `from ..charts import _add_months, _sum, carry_forward`。檔尾加：

```python
def load_heatmap(snap: dict, lang: str, spare_pct: float, by: str = "function") -> Chart:
    """負載 = Σallocated ÷ Σkeyed_in。無人填報（Σkeyed_in = 0）的格放在第二個 series，灰底、不寫 0%。"""
    loads = snap["loads"]
    if by == "function":
        groups: dict[str, list[dict]] = {}
        for r in loads:
            groups.setdefault((r.get("function") or "").strip() or "(none)", []).append(r)
        keys = sorted(groups, key=str.casefold)
        names = {k: k for k in keys}
        cid, title, first = "heat-function", t(lang, "v_c_heat"), t(lang, "col_function")
    else:
        ordered = sorted(loads, key=lambda r: ((r.get("function") or "").casefold(), r["dept_code"]))
        groups = {r["dept_code"]: [r] for r in ordered}
        keys = list(groups)
        names = {r["dept_code"]: f'{r.get("function") or "–"}  {r["dept_name"]}' for r in ordered}
        cid, title, first = "heat-dept", t(lang, "v_c_heat_dept"), t(lang, "col_dept")
    ypos = {k: len(keys) - 1 - i for i, k in enumerate(keys)}          # 第一個在最上面
    cells, nodata, table = [], [], []
    for k in keys:
        pcts = []
        for m in range(12):
            kin = sum(r["keyed_in"][m] or 0 for r in groups[k])
            alloc = sum(r["allocated"][m] or 0 for r in groups[k])
            if kin <= 0:
                nodata.append([m, ypos[k], 0]); pcts.append(None)
            else:
                v = round(alloc / kin * 100); cells.append([m, ypos[k], v]); pcts.append(v)
        table.append((names[k], *pcts))
    option = {"grid": {"left": 8, "right": 8, "top": 8, "bottom": 46, "containLabel": True}, "tooltip": {"position": "top"},
              "xAxis": {"type": "category", "data": list(MONTHS), "axisTick": {"show": False}, "axisLabel": {"color": T.INK2}},
              "yAxis": {"type": "category", "data": [names[k] for k in reversed(keys)], "axisTick": {"show": False}, "axisLabel": {"color": T.INK}},
              "visualMap": {"type": "piecewise", "seriesIndex": 0, "orient": "horizontal", "left": "center", "bottom": 0,
                            "itemWidth": 12, "itemHeight": 12, "textStyle": {"color": T.INK2},
                            "pieces": [{"lt": spare_pct, "label": f"<{spare_pct:g}%", "color": T.HEAT_LOW},
                                       {"gte": spare_pct, "lt": T.HEAT_HIGH, "label": f"{spare_pct:g}-{T.HEAT_HIGH - 1}%", "color": T.HEAT_MID},
                                       {"gte": T.HEAT_HIGH, "label": f">={T.HEAT_HIGH}%", "color": T.HEAT_HI}]},
              "series": [{"type": "heatmap", "data": cells, "label": {"show": True, "formatter": "{@[2]}%", "fontSize": 10, "color": T.INK},
                          "itemStyle": {"borderColor": "#fff", "borderWidth": 2}},
                         {"type": "heatmap", "name": t(lang, "v_no_data"), "data": nodata, "label": {"show": False},
                          "itemStyle": {"color": T.NODATA, "borderColor": "#fff", "borderWidth": 2}, "tooltip": {"formatter": t(lang, "v_no_data")}}]}
    return Chart(cid, title, option, (first, *MONTHS), tuple(table), height=24 * len(keys) + 80, note=t(lang, "v_heat_note"))


def forecast_capacity(snap: dict, lang: str) -> Chart:
    """與舊 capacity_svg 同口徑：actual／plan＝有 Control List 的專案 BU RD＋PM；plan 只算 has_plan 的專案；最新月之後的人數沿用最新月（虛線）。"""
    ps, lm = snap["projects"], snap["meta"]["latest_month"]
    raw = snap["capacity"]
    cap = carry_forward(raw, lm)
    cl = [p for p in ps if p.get("pva")]
    wp = [p for p in cl if p["has_plan"]]
    add = lambda a, b: [round(x + y, 2) for x, y in zip(a, b)]  # noqa: E731
    actual = add(_sum(cl, "BU RD", "actual", lm), _sum(cl, "PM", "actual", lm))
    plan = add(_sum(wp, "BU RD", "plan", only_plan=True), _sum(wp, "PM", "plan", only_plan=True))
    fu = [round(v, 2) for v in _sum(cl, "FU RD", "actual", lm)]
    pad = lambda xs: xs + [None] * (12 - len(xs))  # noqa: E731
    mon = MONTHS[lm - 1]
    series = [{"name": t(lang, "v_lg_cap"), "type": "line", "data": [v if i < lm else None for i, v in enumerate(cap)], "symbol": "none",
               "lineStyle": {"color": T.INK, "width": 2.5}, "itemStyle": {"color": T.INK}},
              {"name": t(lang, "v_lg_cap_carried", mon=mon), "type": "line", "data": [v if i >= lm - 1 else None for i, v in enumerate(cap)],
               "symbol": "none", "lineStyle": {"color": T.INK, "width": 2, "type": "dashed"}, "itemStyle": {"color": T.INK}},
              {"name": t(lang, "v_lg_actual"), "type": "bar", "data": pad(actual), "barWidth": "45%", "itemStyle": {"color": T.ACCENT}},
              {"name": t(lang, "v_lg_plan"), "type": "line", "data": plan, "symbol": "circle", "symbolSize": 5,
               "lineStyle": {"color": T.PLAN, "type": "dashed", "width": 2}, "itemStyle": {"color": T.PLAN}},
              {"name": t(lang, "v_lg_fu"), "type": "line", "data": pad(fu), "symbol": "none", "lineStyle": {"color": T.FU, "width": 2},
               "itemStyle": {"color": T.FU}}]
    option = {"grid": {"left": 8, "right": 12, "top": 16, "bottom": 64, "containLabel": True}, "tooltip": {"trigger": "axis"},
              "legend": {"bottom": 0, "itemWidth": 14, "itemHeight": 8, "textStyle": {"color": T.INK2, "fontSize": 11}},
              "xAxis": {"type": "category", "data": list(MONTHS), "axisTick": {"show": False}, "axisLabel": {"color": T.INK2}},
              "yAxis": {"type": "value", "splitLine": {"lineStyle": {"color": T.RULE}}, "axisLabel": {"color": T.INK3}}, "series": series}
    rows = tuple((m, raw[i] if i < lm else None, actual[i] if i < lm else None, plan[i] if wp else None, fu[i] if i < lm else None)
                 for i, m in enumerate(MONTHS))
    return Chart("forecast", t(lang, "v_c_forecast"), option,
                 (t(lang, "v_col_month"), t(lang, "v_lg_cap"), t(lang, "v_lg_actual"), t(lang, "v_lg_plan"), t(lang, "v_lg_fu")), rows,
                 height=300, note=t(lang, "cap_budget_note", covered=len(wp), total=len(cl)))


def pva(p: dict, role: str, latest_month: int, lang: str, idx: int) -> Chart:
    v = (p.get("pva") or {}).get(role) or {}
    plan = [round(x, 2) for x in v.get("plan", [0.0] * 12)]
    act = [round(x, 2) for x in v.get("actual", [0.0] * 12)]
    has_plan = any(plan)
    series = [{"name": t(lang, "v_lg_pva_actual"), "type": "bar", "data": [a if i < latest_month else None for i, a in enumerate(act)],
               "barWidth": "50%", "itemStyle": {"color": T.FU if role == "FU RD" else T.ACCENT}}]
    if has_plan:
        series.append({"name": t(lang, "v_lg_pva_plan"), "type": "line", "data": plan, "symbol": "circle", "symbolSize": 4,
                       "lineStyle": {"color": T.PLAN, "type": "dashed"}, "itemStyle": {"color": T.PLAN}})
    option = {"grid": {"left": 4, "right": 4, "top": 24, "bottom": 4, "containLabel": True}, "tooltip": {"trigger": "axis"},
              "legend": {"top": 0, "right": 0, "itemWidth": 10, "itemHeight": 6, "textStyle": {"fontSize": 10, "color": T.INK2}},
              "xAxis": {"type": "category", "data": list(MONTHS), "axisTick": {"show": False}, "axisLabel": {"fontSize": 10, "color": T.INK3, "interval": 1}},
              "yAxis": {"type": "value", "splitLine": {"lineStyle": {"color": T.RULE}}, "axisLabel": {"fontSize": 10, "color": T.INK3}}, "series": series}
    rows = tuple((m, act[i] if i < latest_month else None, plan[i] if has_plan else None) for i, m in enumerate(MONTHS))
    return Chart(f"pva-{idx}-{role.lower().replace(' ', '')}", role, option,
                 (t(lang, "v_col_month"), t(lang, "v_lg_pva_actual"), t(lang, "v_lg_pva_plan")), rows, height=150,
                 note="" if has_plan else t(lang, "v_pva_no_plan"))
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/portfolio/test_viz_options.py -q`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/render/viz/options.py tests/portfolio/test_viz_options.py
git commit -m "feat(viz): load heatmap, forecast vs capacity and per-project plan vs actual"
```

---

### Task 5: 新版 CSS 與版面積木（`dash.py`）

**Files:**
- Modify: `src/portfolio/render/css.py`（整個 `CSS` 換掉）
- Create: `src/portfolio/render/viz/dash.py`
- Modify: `tests/portfolio/test_strings.py`（`test_css_tokens_present` 改新色票）
- Test: `tests/portfolio/test_viz_dash.py`

**Interfaces:**
- Consumes: `Chart`、`chart_html`（Task 1）
- Produces: `side_nav(brand_html: str, inner_html: str, menu: str, label: str = "EIS") -> str`（`<nav class="side" aria-label=…>`）
- Produces: `kpi_cards(items: list[dict], href: dict | None = None, cls: str = "") -> str`
- Produces: `card(title: str, body: str, sub: str = "", cls: str = "") -> str`、`chart_card(ch: Chart, lang: str, sub: str = "", cls: str = "") -> str`
- Produces: `safe_chart_card(title: str, build: Callable[[], Chart], lang: str, cls: str = "") -> str`
- Produces: `milestone_status(days_left: int) -> str`（`passed`｜`due`｜`ok`，`DUE_DAYS = 14`）、`pill(status: str, lang: str, late: bool = True) -> str`
- Produces: `milestone_table(rows: list[dict], lang: str, link: Callable[[str], str] | None = None) -> str`（rows 每筆 `{date, name, code, customer, milestone, days_left, late}`）

- [ ] **Step 1: 寫失敗的測試**

`tests/portfolio/test_viz_dash.py`：

```python
from src.portfolio.render.viz.dash import card, chart_card, kpi_cards, milestone_status, milestone_table, pill, safe_chart_card, side_nav
from src.portfolio.render.viz.embed import Chart

CH = Chart("stage", "Projects by stage", {"series": []}, ("Stage", "Projects"), (("MP", 1),))


def test_kpi_cards_escape_link_and_tone():
    h = kpi_cards([{"key": "total", "label": "Total", "value": 7, "sub": "6 in Briefing", "tone": ""},
                   {"key": "risk", "label": "At risk", "value": "<2>", "sub": "", "tone": "bad"}], {"risk": "/ui/202609/decisions"})
    assert h.startswith('<div class="kpis">')
    assert '<div class="kpi"><span class="k-label">Total</span><b class="k-value">7</b><span class="k-sub">6 in Briefing</span></div>' in h
    assert '<a class="kpi bad" href="/ui/202609/decisions"><span class="k-label">At risk</span><b class="k-value">&lt;2&gt;</b></a>' in h
    assert kpi_cards([], cls="four").startswith('<div class="kpis four">')


def test_cards_and_side_nav():
    assert card("A & B", "<p>x</p>", sub="src") == '<div class="card"><div class="card-h"><h3>A &amp; B</h3><span class="card-sub">src</span></div><p>x</p></div>'
    assert chart_card(CH, "en").startswith('<div class="card"><div class="card-h"><h3>Projects by stage</h3></div><div class="chart" id="c-stage"')
    nav = side_nav('<a class="brand" href="/ui/">B</a>', '<a href="#x">X</a>', "Menu")
    assert nav.startswith('<nav class="side" aria-label="EIS"><a class="brand" href="/ui/">B</a><input type="checkbox" id="navt" class="navt">')
    assert '<label for="navt" class="navbtn">Menu</label><div class="links"><a href="#x">X</a></div></nav>' in nav


def test_safe_chart_card_reports_missing_data():
    def broken():
        raise KeyError("capacity")
    h = safe_chart_card("Forecast vs capacity", broken, "en")
    assert "<h3>Forecast vs capacity</h3>" in h and "Not in this snapshot." in h and "data-chart" not in h
    assert 'id="c-stage"' in safe_chart_card("x", lambda: CH, "en")


def test_milestone_status_pills_and_table():
    assert [milestone_status(d) for d in (-1, 0, 14, 15)] == ["passed", "due", "due", "ok"]
    assert pill("passed", "en") == '<span class="pill bad">Passed</span>'
    assert pill("passed", "en", late=False) == '<span class="pill mute">Passed</span>'
    rows = [{"date": "2026-09-08", "name": "N1X", "code": "BR6", "customer": "Dell", "milestone": "pvt", "days_left": -4, "late": True}]
    h = milestone_table(rows, "en", link=lambda c: f"/ui/202609/projects/{c}")
    assert h.startswith('<div class="wide"><table>')
    assert '<td>09/08</td><td><a href="/ui/202609/projects/BR6">N1X</a></td><td>Dell</td><td>PVT</td><td class="num">-4</td><td><span class="pill bad">Passed</span></td>' in h
    assert "<b>N1X</b>" in milestone_table(rows, "en")
```

`tests/portfolio/test_strings.py`：把 `test_css_tokens_present` 換成：

```python
def test_css_tokens_present():
    for tok in ("#F3F5F8", "#1F2937", "#2563EB", "#1E2735", "#E8590C"):
        assert tok.lower() in CSS.lower()
    assert ".kpis{" in CSS and ".navt:checked~.links" in CSS and "@media(max-width:900px)" in CSS
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/portfolio/test_viz_dash.py tests/portfolio/test_strings.py -q`
Expected: FAIL（`dash` 不存在；CSS 沒有新色票）

- [ ] **Step 3: 實作**

`src/portfolio/render/css.py` 整檔換成：

```python
CSS = """
:root{--bg:#F3F5F8;--paper:#F3F5F8;--card:#FFFFFF;--ink:#1F2937;--ink-2:#5B6475;--ink-3:#9AA3AF;--rule:#E3E7EE;--side:#1E2735;--accent:#2563EB;--slate:#2563EB;--slate-2:#93C5FD;--teal:#0D9488;--signal:#E8590C;--bad:#DC2626;--warn:#F59E0B;--ok:#16A34A}
*{box-sizing:border-box}html{background:var(--bg)}
body{margin:0;color:var(--ink);background:var(--bg);font:14px/1.55 -apple-system,"SF Pro Text","Segoe UI","Helvetica Neue","PingFang TC","Microsoft JhengHei","Noto Sans TC",sans-serif;font-variant-numeric:tabular-nums}
a{color:var(--accent)}
.app{display:grid;grid-template-columns:224px minmax(0,1fr);min-height:100vh}
.side{background:var(--side);color:#CBD5E1;padding:20px 14px;position:sticky;top:0;height:100vh;overflow-y:auto}
.side a{display:flex;justify-content:space-between;align-items:center;gap:8px;color:#CBD5E1;text-decoration:none;padding:8px 10px;border-radius:6px;font-size:13px}
.side a:hover,.side a:focus-visible{background:rgba(255,255,255,.08);color:#fff}.side a.on{background:var(--accent);color:#fff;font-weight:600}
.side a.brand{color:#fff;font-weight:700;font-size:15px;padding:4px 10px 16px;background:none}
.side .badge{background:var(--signal);color:#fff;border-radius:9px;font-size:11px;font-weight:700;padding:0 7px;line-height:18px}
.side form{display:flex;gap:6px;align-items:end;margin:0 0 10px;padding:0 4px}.side label{color:#94A3B8;font-size:11px;display:flex;flex-direction:column;gap:4px;flex:1;min-width:0}
.side select,.side input{width:100%;min-width:0;font:13px inherit;padding:5px 8px;border:1px solid #334155;border-radius:6px;background:#0F172A;color:#E2E8F0}
.side button{font:12px inherit;padding:5px 10px;border:0;border-radius:6px;background:#334155;color:#fff;cursor:pointer}
.navt{position:absolute;opacity:0;width:1px;height:1px}.navbtn{display:none}.navt:focus-visible+.navbtn{outline:2px solid #fff}
.main{padding:28px 32px 64px;min-width:0;max-width:1480px}
header{display:flex;justify-content:space-between;align-items:flex-start;gap:24px;padding:0 0 16px;margin:0 0 18px;border-bottom:1px solid var(--rule)}
h1{font-size:24px;font-weight:700;margin:0;line-height:1.25}header p{margin:6px 0 0;color:var(--ink-2);max-width:70ch}
.tb{background:var(--card);border:1px solid var(--rule);border-radius:8px;font-size:12px;min-width:270px;overflow:hidden}.tb div{display:grid;grid-template-columns:112px 1fr;border-top:1px solid var(--rule)}.tb div:first-child{border-top:0}
.tb span{padding:5px 10px}.tb span:first-child{color:var(--ink-2);border-right:1px solid var(--rule)}
section{padding:4px 0 18px}
h2{font-size:18px;font-weight:700;margin:12px 0 4px}.lead{margin:0 0 14px;color:var(--ink-2);max-width:80ch}
.kpis{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:14px;margin:0 0 14px}.kpis.four{grid-template-columns:repeat(4,minmax(0,1fr))}
.kpi{display:flex;flex-direction:column;gap:2px;min-width:0;background:var(--card);border:1px solid var(--rule);border-top:3px solid var(--accent);border-radius:10px;padding:12px 16px;color:var(--ink);text-decoration:none}
a.kpi:hover,a.kpi:focus-visible{box-shadow:0 4px 14px rgba(15,23,42,.10);outline:none}
.kpi.bad{border-top-color:var(--bad)}.kpi.bad .k-value{color:var(--bad)}
.k-label{font-size:12px;color:var(--ink-2)}.k-value{font-size:26px;font-weight:700;line-height:1.2;overflow-wrap:anywhere}.k-sub{font-size:11px;color:var(--ink-3)}
.grid-2,.grid-3{display:grid;gap:14px;margin:0 0 14px}.grid-2{grid-template-columns:repeat(2,minmax(0,1fr))}.grid-3{grid-template-columns:repeat(3,minmax(0,1fr))}
.card{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:14px 16px;min-width:0;margin:0 0 14px}.grid-2>.card,.grid-3>.card{margin:0}
.card-h{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin:0 0 8px}.card-h h3{font-size:14px;font-weight:700;margin:0}.card-sub{font-size:11px;color:var(--ink-3)}
.chart{width:100%}.note{font-size:12px;color:var(--ink-2);margin:6px 0 0}
label.pick{font-size:12px;color:var(--ink-2);display:inline-flex;gap:6px;align-items:center;margin:0 0 6px}
.pill{display:inline-block;font-size:11px;font-weight:600;padding:1px 8px;border-radius:9px;white-space:nowrap}
.pill.bad{background:#FEE2E2;color:#B91C1C}.pill.warn{background:#FEF3C7;color:#92400E}.pill.ok{background:#DCFCE7;color:#166534}.pill.mute{background:#EEF1F5;color:var(--ink-2)}
ol.ex{list-style:none;margin:0;padding:0}ol.ex li{display:grid;grid-template-columns:44px 1fr;gap:12px;padding:14px 0;border-top:1px solid var(--rule)}ol.ex li:first-child{border-top:0}
ol.ex .n{font-size:26px;font-weight:700;color:var(--signal);line-height:1}ol.ex b{font-weight:600;font-size:15px}
ol.ex .body{color:var(--ink-2);margin:4px 0 0;max-width:110ch}ol.ex .ask{margin-top:6px}ol.ex .ask em{font-style:normal;color:var(--signal);font-weight:600}ol.ex .src{color:var(--ink-3);font-size:12px;margin-top:2px}
.two{display:grid;grid-template-columns:320px 1fr;gap:36px}
table{border-collapse:collapse;width:100%}th{text-align:left;font-weight:600;font-size:12px;color:var(--ink-2);padding:6px 8px 6px 0;border-bottom:1px solid var(--rule)}
td{padding:7px 8px 7px 0;border-bottom:1px solid var(--rule);vertical-align:top}td.num,th.num{text-align:right}
.sig{color:var(--signal);font-weight:600}.dim{color:var(--ink-3)}
.stages{display:flex;gap:28px;margin:0 0 22px;flex-wrap:wrap}.stages div b{display:block;font-size:24px;font-weight:600;line-height:1.1}.stages div span{font-size:12px;color:var(--ink-2)}
.legend{display:flex;gap:18px;font-size:12px;color:var(--ink-2);margin-top:10px;flex-wrap:wrap}.legend i{display:inline-block;width:10px;height:10px;margin-right:6px;vertical-align:-1px;background:var(--slate)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:8px;vertical-align:1px}.dot.d{background:var(--signal)}.dot.t{background:var(--slate)}.dot.o{background:var(--ink-3)}
select{font:14px inherit;padding:6px 10px;border:1px solid var(--rule);background:#fff;border-radius:6px}select:focus{outline:2px solid var(--accent);outline-offset:2px}
.ms{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:12px 0 18px}.ms div{background:var(--bg);border-radius:8px;padding:10px 12px;min-width:0}
.ms b{display:block;font-size:18px;font-weight:700}.ms small{color:var(--ink-2)}
details{border-top:1px solid var(--rule)}details summary{cursor:pointer;padding:10px 0;list-style:none;display:flex;justify-content:space-between}
details summary::-webkit-details-marker{display:none}details summary:focus-visible{outline:2px solid var(--accent)}
details summary::after{content:attr(data-expand);color:var(--accent);font-size:12px}details[open] summary::after{content:attr(data-collapse)}
details.data{margin-top:8px}details.data summary{padding:6px 0;font-size:12px;color:var(--ink-2)}
details td.desc{white-space:pre-line;max-width:70ch;color:var(--ink-2);font-size:13px}
.proj{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:14px 16px;margin-top:12px}
.pva{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.pva>div{min-width:0}.pva h4{margin:0 0 4px;font-size:13px;font-weight:700}.pva .s{font-size:12px;color:var(--ink-2)}
.wide{overflow-x:auto}
footer{color:var(--ink-3);font-size:12px;margin-top:24px;max-width:80ch}footer p{margin:4px 0}
svg text{font-family:inherit}
@media(max-width:1200px){.kpis{grid-template-columns:repeat(3,minmax(0,1fr))}.grid-3{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:900px){.app{grid-template-columns:minmax(0,1fr)}.side{position:static;height:auto;padding:12px 14px}.side a.brand{display:inline-flex;padding:4px 6px}
.navbtn{display:inline-block;float:right;color:#fff;font-size:13px;padding:4px 10px;border:1px solid #475569;border-radius:6px;cursor:pointer}.side .links{display:none;padding-top:10px}.navt:checked~.links{display:block}
.main{padding:18px 16px 48px}header{flex-direction:column}.tb{min-width:0;width:100%}.grid-2,.grid-3{grid-template-columns:minmax(0,1fr)}.pva{grid-template-columns:minmax(0,1fr)}.ms{grid-template-columns:repeat(2,minmax(0,1fr))}.two{grid-template-columns:1fr}}
@media(max-width:640px){.kpis,.kpis.four{grid-template-columns:repeat(2,minmax(0,1fr))}.k-value{font-size:22px}}
@media (prefers-reduced-motion: reduce){*{transition:none!important}}
"""
```

`src/portfolio/render/viz/dash.py`：

```python
"""v2 版型的 HTML 積木（月報與 /ui/ 共用）。所有文字在這裡跳脫。卡片是單一圓角底卡＋上緣色條，不疊兩個圓角矩形。"""
from __future__ import annotations
from collections.abc import Callable
from html import escape as e
from ..strings import t
from .embed import Chart, chart_html

DUE_DAYS = 14


def side_nav(brand_html: str, inner_html: str, menu: str, label: str = "EIS") -> str:
    """左側深色導覽。窄螢幕時 .links 收起，以無 JS 的 checkbox 開關。brand_html 與 inner_html 由呼叫端組好（已跳脫）。"""
    return (f'<nav class="side" aria-label="{e(label)}">{brand_html}'
            f'<input type="checkbox" id="navt" class="navt"><label for="navt" class="navbtn">{e(menu)}</label>'
            f'<div class="links">{inner_html}</div></nav>')


def kpi_cards(items: list[dict], href: dict | None = None, cls: str = "") -> str:
    href = href or {}
    out = []
    for k in items:
        inner = (f'<span class="k-label">{e(k["label"])}</span><b class="k-value">{e(str(k["value"]))}</b>'
                 + (f'<span class="k-sub">{e(k["sub"])}</span>' if k.get("sub") else ""))
        c = f'kpi {k.get("tone", "")}'.strip()
        link = href.get(k["key"])
        out.append(f'<a class="{c}" href="{e(link)}">{inner}</a>' if link else f'<div class="{c}">{inner}</div>')
    return f'<div class="{f"kpis {cls}".strip()}">{"".join(out)}</div>'


def card(title: str, body: str, sub: str = "", cls: str = "") -> str:
    s = f'<span class="card-sub">{e(sub)}</span>' if sub else ""
    return f'<div class="{f"card {cls}".strip()}"><div class="card-h"><h3>{e(title)}</h3>{s}</div>{body}</div>'


def chart_card(ch: Chart, lang: str, sub: str = "", cls: str = "") -> str:
    return card(ch.title, chart_html(ch, lang), sub, cls)


def safe_chart_card(title: str, build: Callable[[], Chart], lang: str, cls: str = "") -> str:
    """舊快照可能缺欄位（例如 capacity）：畫不出來就明說，不讓整頁 500。"""
    try:
        ch = build()
    except (KeyError, TypeError, ValueError, IndexError):
        return card(title, f'<p class="note">{e(t(lang, "v_not_in_snapshot"))}</p>', cls=cls)
    return chart_card(ch, lang, cls=cls)


def milestone_status(days_left: int) -> str:
    return "passed" if days_left < 0 else "due" if days_left <= DUE_DAYS else "ok"


def pill(status: str, lang: str, late: bool = True) -> str:
    """已過的里程碑：階段沒前進（late）才用紅色；已正常往下走的用灰色，與舊版 sig／dim 同一語意。"""
    tone = {"passed": "bad" if late else "mute", "due": "warn", "ok": "ok"}[status]
    return f'<span class="pill {tone}">{e(t(lang, "v_st_" + status))}</span>'


def milestone_table(rows: list[dict], lang: str, link: Callable[[str], str] | None = None) -> str:
    body = []
    for r in rows:
        name = f'<a href="{e(link(r["code"]))}">{e(r["name"])}</a>' if link else f'<b>{e(r["name"])}</b>'
        body.append(f'<tr><td>{e(r["date"][5:].replace("-", "/"))}</td><td>{name}</td><td>{e(r.get("customer") or "")}</td>'
                    f'<td>{e(r["milestone"].upper())}</td><td class="num">{r["days_left"]}</td>'
                    f'<td>{pill(milestone_status(r["days_left"]), lang, r.get("late", False))}</td></tr>')
    return (f'<div class="wide"><table><thead><tr><th>{e(t(lang, "col_date"))}</th><th>{e(t(lang, "col_project"))}</th>'
            f'<th>{e(t(lang, "col_customer"))}</th><th>{e(t(lang, "col_milestone"))}</th><th class="num">{e(t(lang, "v_col_days"))}</th>'
            f'<th>{e(t(lang, "v_col_status"))}</th></tr></thead><tbody>{"".join(body)}</tbody></table></div>')
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests -q`
Expected: 全部 PASS（CSS 只換外觀；既有頁面測試不檢查樣式值）

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/render/css.py src/portfolio/render/viz/dash.py tests/portfolio/test_viz_dash.py tests/portfolio/test_strings.py
git commit -m "feat(viz): v2 stylesheet and layout blocks (KPI cards, cards, pills, side nav)"
```

---

### Task 6: `/ui/` 外殼、靜態 ECharts、Decisions 與 Data health 分頁

**Files:**
- Modify: `src/eis_mcp/web/shell.py`（側欄外殼、`decisions` badge、載入 ECharts）
- Modify: `src/eis_mcp/web/routes.py`（static route、`/decisions`、`/health`、`/corrections` 轉址、所有頁傳 badge）
- Create: `src/eis_mcp/web/pages_decisions.py`（由 `pages_overview.py` 搬入 `_project_link`、`linked_exceptions`）
- Create: `src/eis_mcp/web/pages_health.py`（由 `pages_overview.py` 搬入 `_linked_health`、`health_section`；新增 `health_body`）
- Modify: `src/eis_mcp/web/pages_overview.py`（改 import 搬走的函式；內容不變，Task 8 再改）
- Modify: `src/eis_mcp/web/pages_home.py`（入口清單）
- Modify: `src/eis_mcp/__main__.py`（缺 ECharts 拒絕啟動）
- Modify: `deploy/install.sh`（rsync 放行 `vendor/`）
- Test: `tests/eis_mcp/test_web.py`、`tests/eis_mcp/test_main.py`

**Interfaces:**
- Consumes: `scripts`、`echarts_source`、`ECHARTS_JS`（Task 1）；`side_nav`（Task 5）
- Produces: `render_shell(..., decisions: int | None = None)`；`NAV` 新順序 overview／decisions／projects／loads／health／report
- Produces: `pages_decisions.decisions_body(snap: dict, th: dict) -> str`、`pages_decisions.linked_exceptions(snap, th) -> str`
- Produces: `pages_health.health_section(snap) -> str`、`pages_health.health_body(month: str, snap: dict, corrections: dict) -> str`
- Produces: routes `GET /ui/static/echarts.min.js`、`GET /ui/{month}/decisions`、`GET /ui/{month}/health`；`GET /ui/{month}/corrections` → 301 `/ui/{month}/health`

- [ ] **Step 1: 寫失敗的測試**

`tests/eis_mcp/test_web.py` 檔尾加：

```python
# ---- v2 外殼（2026-10-02）----
def test_static_echarts_is_served_with_cache_header(ingested):
    r = get(ingested, "/ui/static/echarts.min.js")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/javascript")
    assert r.headers["cache-control"] == "public, max-age=86400" and len(r.content) == 1034102


def test_shell_is_a_sidebar_that_loads_charts():
    t = render_shell(title="x", body="", months=["202609"], month="202609", decisions=3)
    assert '<nav class="side" aria-label="EIS">' in t and '<main class="main">' in t
    assert '<script src="/ui/static/echarts.min.js"></script>' in t and "window.eisCharts" in t
    nav = t[t.index("<nav"):t.index("</nav>")]
    assert [x for x in ("/decisions", "/projects", "/loads", "/health", "/report.html") if f'href="/ui/202609{x}"' in nav] == \
           ["/decisions", "/projects", "/loads", "/health", "/report.html"]
    assert '>Decisions<span class="badge">3</span></a>' in nav


def test_decisions_page_and_badge_count(ingested):
    snap = ingested.state.eis.store.load_snapshot("202609")
    t = html(ingested, f"/ui/202609/decisions?today={TODAY}")
    assert "Decisions this month" in t and '<ol class="ex">' in t
    assert f'>Decisions<span class="badge">{len(snap["exceptions"])}</span>' in t
    ex = t[t.index('<ol class="ex">'):t.index("</ol>")]
    assert f'href="/ui/202609/projects/{CODE}"' in ex


def test_health_page_merges_corrections_and_old_url_redirects(ingested):
    t = html(ingested, "/ui/202609/health")
    assert "<h2>Data health" in t and "repeat items on the Decisions page" in t and "No corrections" in t
    r = get(ingested, "/ui/202609/corrections")
    assert r.status_code == 301 and r.headers["location"] == "/ui/202609/health"
```

`tests/eis_mcp/test_web.py` 既有測試修改：

`test_corrections_page`：兩處 `html(ingested, "/ui/202609/corrections")` 改成 `html(ingested, "/ui/202609/health")`。

`test_exceptions_and_health_link_to_projects` 整個換成：

```python
def test_exceptions_and_health_link_to_projects(ingested):
    t = html(ingested, f"/ui/202609/decisions?today={TODAY}")
    ex = t[t.index('<ol class="ex">'):t.index("</ol>")]
    assert f'href="/ui/202609/projects/{CODE}"' in ex
    health = html(ingested, "/ui/202609/health")
    health = health[health.index("<h2>Data health"):]
    assert "<details" in health and "repeat items on the Decisions page" in health   # decide 級與 Decisions 重複，收合
```

`test_open_links_can_wrap`：`html(ingested, f"/ui/202609/?today={TODAY}")` 改成 `html(ingested, f"/ui/202609/decisions?today={TODAY}")`。

`test_home_summarises_latest_month_and_links_entry_points`：href 清單改成

```python
    for href in ('href="/ui/202609/"', 'href="/ui/202609/decisions"', 'href="/ui/202609/projects"', 'href="/ui/202609/loads"',
                 'href="/ui/202609/health"', 'href="/ui/202609/report.html"'):
```

`tests/eis_mcp/test_main.py` 檔尾加：

```python
def test_main_refuses_without_echarts_bundle(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("src.eis_mcp.__main__.ECHARTS_JS", tmp_path / "missing.js")
    assert main(["--data", str(tmp_path / "d")]) == 1
    assert "missing.js" in capsys.readouterr().err


def test_install_copies_vendor():
    from pathlib import Path
    sh = Path("deploy/install.sh").read_text(encoding="utf-8")
    assert "--include='vendor/' --include='vendor/**'" in sh
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/eis_mcp/test_web.py tests/eis_mcp/test_main.py -q`
Expected: FAIL（static route 404、nav 不是側欄、`/decisions` 與 `/health` 404、`ECHARTS_JS` 不在 `__main__`、install.sh 沒有 vendor）

- [ ] **Step 3: 搬移 Decisions／Health 函式**

`src/eis_mcp/web/pages_decisions.py`：

```python
"""本月決策頁。例外清單與月報同一份（render/page.py 的 exceptions_html），每條補一行連到單案頁。"""
from __future__ import annotations
from html import escape as e
from ...portfolio.render.page import exceptions_html


def _project_link(month: str, code: str, label: str) -> str:
    return f'<a href="/ui/{e(month)}/projects/{e(code)}">{e(label)}</a>'
```

接著把 `src/eis_mcp/web/pages_overview.py` 裡的 `def linked_exceptions(snap: dict, th: dict) -> str:` 整個函式（含 docstring，到 `return "</li>".join(items)` 為止）**原樣剪下**，貼到 `pages_decisions.py` 檔尾，再於其後加：

```python


def decisions_body(snap: dict, th: dict) -> str:
    return (f'<section><h2>Decisions this month</h2><p class="lead">Exceptions the rules found, ranked; each names the decision asked for.</p>'
            f'<div class="card">{linked_exceptions(snap, th)}</div></section>')
```

`src/eis_mcp/web/pages_health.py`：

```python
"""資料健康度頁：健康度表（名稱連到單案頁）＋跨月修正（原 Corrections 頁）。"""
from __future__ import annotations
from html import escape as e
from ...portfolio.render.page import health_html
from .pages_decisions import _project_link
from .pages_load import corrections_body
```

把 `pages_overview.py` 的 `def _linked_health(` 與 `def health_section(` 兩個函式**原樣剪下**貼到 `pages_health.py` 檔尾，然後把 `health_section` 裡的字串 `repeat the Decisions above` 改成 `repeat items on the Decisions page`，再於檔尾加：

```python


def health_body(month: str, snap: dict, corrections: dict) -> str:
    return (f'<section><h2>Data health</h2><p class="lead">What the source files could not answer.</p>'
            f'<div class="card">{health_section(snap)}</div></section>{corrections_body(month, corrections)}')
```

`src/eis_mcp/web/pages_overview.py`：刪除已搬走的 `_project_link`（原本就在此檔）、`linked_exceptions`、`_linked_health`、`health_section`，import 區改成：

```python
from __future__ import annotations
from html import escape as e
from ...portfolio.render.page import stage_strip_html
from .. import queries
from .pages_decisions import linked_exceptions
from .pages_health import health_section
from .shell import fmt_month
```

- [ ] **Step 4: 外殼改成側欄**

`src/eis_mcp/web/shell.py`：

1. import 區加 `from ...portfolio.render.viz.dash import side_nav` 與 `from ...portfolio.render.viz.embed import scripts`；模組 docstring 第一行改為 `"""頁面外殼：<head>、左側導覽、footer、錯誤頁。CSS = 月報的 CSS + 這裡的 WEB_CSS；圖表用 /ui/static/echarts.min.js。`
2. `WEB_CSS` 刪掉所有以 `nav.top` 開頭的規則（第 9、10、11、25 行），`.metaline{...}nav.top+header{margin-top:20px}` 改成 `.metaline{color:var(--ink-2);font-size:12px;margin:6px 0 0;max-width:none}`；`input[...]` 與 `button` 兩行改成：

```python
input[type=text],input[type=search],input[type=number]{font:inherit;padding:6px 10px;border:1px solid var(--rule);background:#fff;border-radius:6px;min-width:0}
button{font:inherit;padding:6px 14px;border:1px solid var(--accent);background:var(--accent);color:#fff;cursor:pointer;border-radius:6px}
```

   最後一行 `@media(max-width:640px){...}` 換成：

```python
@media(max-width:640px){.kv{grid-template-columns:96px minmax(0,1fr)}.kv code{overflow-wrap:anywhere}ol.ex li{grid-template-columns:32px minmax(0,1fr)}}
```

3. `NAV` 換成：

```python
NAV = (("overview", "Overview", ""), ("decisions", "Decisions", "decisions"), ("projects", "Projects", "projects"),
       ("loads", "Loads", "loads"), ("health", "Data health", "health"), ("report", "Report", "report.html"))
```

4. `_nav` 整個換成：

```python
def _nav(months: list[str], month: str | None, suffix: str, active: str, decisions: int | None = None) -> str:
    brand = f'<a href="/ui/" class="brand{" on" if active == "home" else ""}">{SITE}</a>'
    if not month:
        return side_nav(brand, "", "Menu")
    items = []
    for key, label, path in NAV:
        badge = f'<span class="badge">{decisions}</span>' if key == "decisions" and decisions else ""
        items.append(f'<a href="/ui/{e(month)}/{path}"{" class=\"on\"" if active == key else ""}>{label}{badge}</a>')
    opts = "".join(f'<option value="{e(m)}"{" selected" if m == month else ""}>{fmt_month(m)}</option>' for m in months)
    picker = (f'<form method="get" action="/ui/go"><label>Month <select name="month">{opts}</select></label>'
              f'<input type="hidden" name="page" value="{e(suffix)}"><button>Go</button></form>'
              f'<form method="get" action="/ui/{e(month)}/projects"><label>Find <input type="search" name="q" placeholder="code or name" aria-label="Search projects"></label><button>Find</button></form>')
    return side_nav(brand, picker + "".join(items), "Menu")
```

5. `render_shell` 換成：

```python
def render_shell(*, title: str, body: str, months: list[str], month: str | None = None, suffix: str = "",
                 meta: dict | None = None, active: str = "", title_zh: str = "", decisions: int | None = None) -> str:
    full = f"EIS · {title}" + (f" · {fmt_month(month)}" if month else "")
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(full)}</title><style>{CSS}{WEB_CSS}</style></head><body><div class="app">'
            f'{_nav(months, month, suffix, active, decisions)}<main class="main">'
            f'<header><div><h1>{e(title)}{f"<span class=\"zh\" lang=\"zh-Hant\">{e(title_zh)}</span>" if title_zh else ""}</h1>{meta_line(meta)}</div></header>'
            f'{body}'
            f'<footer><p>Values come straight from the monthly EIS snapshot; nothing is inferred or filled in.</p>'
            f'<p>Same data as the MCP tools. Report month is the month the snapshot was built for (report_month in the tools); keyed in through is the last month with reported manpower (latest_month).</p></footer>'
            f'</main></div>{scripts("static")}</body></html>')
```

- [ ] **Step 5: routes**

`src/eis_mcp/web/routes.py`：

1. import 區：`from . import pages_home, pages_load, pages_mcp, pages_overview, pages_project` 改成
   `from . import pages_decisions, pages_health, pages_home, pages_load, pages_mcp, pages_overview, pages_project`，並加
   `from ...portfolio.render.viz.embed import echarts_source`。
2. 在 `def safe_page(` 之前加：

```python
def nav_count(snap: dict) -> int:
    """側欄 Decisions 的件數 badge：與月報例外清單同一份。"""
    return len(snap.get("exceptions") or [])
```

3. 讓每個月份頁的側欄都帶 badge（所有 `meta=snap["meta"], ` 的呼叫都在有 `snap` 的範圍內）：

```bash
.venv/bin/python - <<'EOF'
from pathlib import Path
p = Path("src/eis_mcp/web/routes.py"); s = p.read_text(encoding="utf-8")
n = s.count('meta=snap["meta"], ')
s = s.replace('meta=snap["meta"], ', 'meta=snap["meta"], decisions=nav_count(snap), ')
p.write_text(s, encoding="utf-8"); print("replaced", n)
EOF
```

Expected: `replaced 7`

4. 把 `/ui/{month}/corrections` 整個 handler 換成以下四個 route（static 放最前面）：

```python
    @mcp.custom_route("/ui/static/echarts.min.js", methods=["GET"])
    async def echarts_js(request: Request) -> Response:
        # vendor 靜態檔、不含資料：不過 PII 檢查也不寫 audit（每頁都會載一次，只是噪音）
        return Response(echarts_source(), media_type="application/javascript; charset=utf-8",
                        headers={"Cache-Control": "public, max-age=86400"})

    @mcp.custom_route("/ui/{month}/decisions", methods=["GET"])
    async def decisions(request: Request) -> Response:
        month = request.path_params["month"]

        def build(ok):
            snap = load_snap(state, month)
            return render_shell(title="Decisions", body=pages_decisions.decisions_body(snap, state.cfg.thresholds), months=ok, month=month,
                                suffix="decisions", meta=snap["meta"], decisions=nav_count(snap), active="decisions")
        return await respond(state, request, build)

    @mcp.custom_route("/ui/{month}/health", methods=["GET"])
    async def health(request: Request) -> Response:
        month = request.path_params["month"]

        def build(ok):
            snap = load_snap(state, month)
            return render_shell(title="Data health", body=pages_health.health_body(month, snap, queries.corrections(snap)), months=ok,
                                month=month, suffix="health", meta=snap["meta"], decisions=nav_count(snap), active="health")
        return await respond(state, request, build)

    @mcp.custom_route("/ui/{month}/corrections", methods=["GET"])
    async def corrections(request: Request) -> Response:
        month = request.path_params["month"]

        def build(ok):
            load_snap(state, month)                       # 月份不存在照樣 404
            return RedirectResponse(f"/ui/{month}/health", status_code=301)   # 2026-10-02 併入 Data health
        return await respond(state, request, build)
```

- [ ] **Step 6: 首頁入口、啟動檢查、部署**

`src/eis_mcp/web/pages_home.py`：`ENTRIES` 換成：

```python
ENTRIES = (
    ("", "Overview", "總覽", "KPIs, charts and the six-month timeline.", "KPI、圖表與六個月時程。"),
    ("decisions", "Decisions", "本月要決定的事", "What needs a decision this month, with evidence.", "本月要決定的事，附證據。"),
    ("projects", "Projects", "專案", "Every project; filter by stage, type, category, group or customer.",
     "全部專案，可依階段、類型、類別、產品群或客戶篩選。"),
    ("loads", "Loads", "部門負載", "Department load by month: where spare capacity is left.", "各部門每月負載：哪裡還有餘裕。"),
    ("health", "Data health", "資料健康度", "What the source files could not answer, and past-month numbers that changed.",
     "來源檔答不出來的事，以及被改過的過去月份數字。"),
    ("report.html", "Monthly report", "月報", "The single-page report, ready to forward.", "可直接轉寄的單頁月報。"),
)
```

`src/eis_mcp/__main__.py`：import 區加 `from ..portfolio.render.viz.embed import ECHARTS_JS`；`a = ap.parse_args(argv)` 之後加：

```python
    if not ECHARTS_JS.is_file():
        print(f"refusing to start: {ECHARTS_JS} is missing (vendor/echarts ships with the repo; re-copy the checkout or re-run deploy/install.sh)",
              file=sys.stderr)
        return 1
```

`deploy/install.sh`：`--include='scripts/' --include='scripts/**' \` 那一行之後加一行：

```bash
  --include='vendor/' --include='vendor/**' \
```

- [ ] **Step 7: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 8: Commit**

```bash
git add src/eis_mcp/web/shell.py src/eis_mcp/web/routes.py src/eis_mcp/web/pages_decisions.py src/eis_mcp/web/pages_health.py src/eis_mcp/web/pages_overview.py src/eis_mcp/web/pages_home.py src/eis_mcp/__main__.py deploy/install.sh tests/eis_mcp/test_web.py tests/eis_mcp/test_main.py
git commit -m "feat(web): sidebar shell with ECharts, Decisions and Data health pages"
```

---

### Task 7: 月報改為 v2 版型；移除舊 SVG 圖

**Files:**
- Modify: `src/portfolio/render/page.py`（`render_page`、`_appendix_one`；新增 `_upcoming_rows`；刪除 `_upcoming`、`_passed_mark`）
- Modify: `src/portfolio/render/charts.py`（只留 `_add_months`、`_sum`、`carry_forward`）
- Modify: `src/eis_mcp/web/pages_load.py`（容量圖改用 `forecast_capacity`）
- Modify: `tests/portfolio/test_page.py`、`tests/portfolio/test_charts.py`、`tests/eis_mcp/test_web.py`

**Interfaces:**
- Consumes: Task 1–5 全部
- Produces: `render_page(snap, lang, today, th, echarts: str = "inline") -> str`（簽章向後相容）

- [ ] **Step 1: 寫失敗的測試**

`tests/portfolio/test_page.py`：

1. `test_page_sections_and_strings` 的前段（從函式開頭到 `assert '<span class="sig">passed</span>' in html` 為止）換成：

```python
def test_page_sections_and_strings():
    html = render_page(snap(), "en", "2026-09-12", TH)
    for s in ("BU10 Portfolio Review", "Decisions this month", "1 milestones passed", "Decision needed:", "Milestones, next 8 weeks",
              "Timeline, next 6 months", "Forecast vs capacity", "Data health", "Project appendix", "Aug: 1 BU tasks, 1 FU tasks, 3.7 FTE",
              "Headcount carried from Aug"):
        assert s in html, s
    assert "TOMY" in html and "no dates yet" in html
    assert html.count("<details><summary") == 1 and "<details open" not in html
    assert "·" not in html.replace(re.search(r"<script>\s*/\*.*?</script>", html, re.S).group(0), "") and "→" not in html
    assert 'lang="en"' in html
    gantt = re.search(r'id="c-gantt-data">(.*?)</script>', html).group(1)
    assert "Q11" not in gantt and "KOS" not in gantt                     # inactive projects are kept out of the timeline
    assert '<span class="pill bad">Passed</span>' in html                 # THORPE DVT 09/08, in milestones_passed
    assert '<span class="pill mute">Passed</span>' in html                # AX200 PVT 09/08, stage moved on
```

（其後原有的 exceptions／appendix 斷言保持不變。）

2. `test_stage_strip_shows_terminated_and_suspended_separately` 整個換成：

```python
def test_kpis_count_stages_and_at_risk():
    html = render_page(snap(), "en", "2026-09-12", TH)
    kp = html[html.index('<div class="kpis">'):html.index('<div class="grid-2">')]
    assert '<span class="k-label">Total projects</span><b class="k-value">6</b><span class="k-sub">5 in Briefing, 2 terminated or suspended</span>' in kp
    assert '<a class="kpi bad" href="#decisions"><span class="k-label">At risk</span><b class="k-value">1</b>' in kp    # BR1：passed 且 MP 延後 291 天
```

3. 檔尾加：

```python
def test_report_is_v2_layout_with_inline_echarts():
    html = render_page(snap(), "en", "2026-09-12", TH)
    assert '<nav class="side" aria-label="BU10 Portfolio Review">' in html and 'href="#decisions"' in html
    assert html.index('id="overview"') < html.index('id="decisions"') < html.index('id="health"') < html.index('id="appendix"')
    assert "<script src=" not in html and "Apache Software Foundation" in html     # 內嵌，零外部腳本
    for cid in ("stage", "customer", "gantt", "heat-function", "forecast", "pva-0-burd"):
        assert f'id="c-{cid}"' in html, cid


def test_every_chart_has_a_data_table():
    html = render_page(snap(), "en", "2026-09-12", TH)
    assert html.count('class="chart"') == html.count('<details class="data">') > 5
    stage_table = html[html.index('id="c-stage-data"'):].split('<details class="data">', 1)[1].split("</details>", 1)[0]
    assert "<td>Execution</td><td>1</td>" in stage_table and "<td>Not in Briefing</td><td>1</td>" in stage_table


def test_appendix_picker_initialises_charts_when_shown():
    html = render_page(snap(), "en", "2026-09-12", TH)
    picker = html[html.rindex("<script>(function(){var s=document.getElementById('pick')"):]
    assert "window.eisCharts.init(document.getElementById('projects'))" in picker


def test_customer_name_cannot_break_the_page():
    sn = snap()
    sn["projects"][0]["customer"] = "</script><script>alert(1)</script>"
    html = render_page(sn, "en", "2026-09-12", TH)
    assert "<script>alert(1)" not in html
    assert find_pii(html) == []


def test_report_survives_snapshot_without_capacity():
    sn = snap()
    del sn["capacity"]
    html = render_page(sn, "en", "2026-09-12", TH)
    assert "Not in this snapshot." in html and 'id="c-stage"' in html
```

`tests/portfolio/test_charts.py` 整檔換成：

```python
import datetime as dt
from dataclasses import asdict
from src.portfolio.entities import PlanVsActual, Project
from src.portfolio.render.charts import _add_months, _sum, carry_forward


def test_add_months_rolls_the_year():
    assert _add_months(dt.date(2026, 11, 15), 3) == dt.date(2027, 2, 1)


def test_carry_forward_only_changes_months_after_latest():
    capacity = [12] * 8 + [0] * 4
    assert carry_forward(capacity, 8) == [12] * 12
    assert capacity == [12] * 8 + [0] * 4                                    # 不動呼叫端的 snapshot 值


def test_sum_respects_only_plan():
    a = Project(code="A", name="A", in_control_list=True, has_plan=True); a.pva = {"BU RD": PlanVsActual("BU RD", plan=[1] * 12)}
    b = Project(code="B", name="B", in_control_list=True); b.pva = {"BU RD": PlanVsActual("BU RD", plan=[5] * 12)}
    ps = [asdict(a), asdict(b)]
    assert _sum(ps, "BU RD", "plan", only_plan=True)[0] == 1 and _sum(ps, "BU RD", "plan")[0] == 6
```

`tests/eis_mcp/test_web.py`：

- `test_project_page_candidates_and_not_found` 的 `"<svg" in t` 改成 `'id="c-pva-0-burd"' in t`。
- `test_loads_page_filters_and_capacity_chart` 的 `"<svg" in t` 改成 `'id="c-forecast"' in t`。

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/portfolio/test_page.py tests/portfolio/test_charts.py tests/eis_mcp/test_web.py -q`
Expected: FAIL（月報仍是舊版面；`test_charts` 的舊函式還在但新測試的斷言不符；web 頁沒有 `c-pva-0-burd`／`c-forecast`）

- [ ] **Step 3: 實作 `charts.py`**

`src/portfolio/render/charts.py` 整檔換成：

```python
"""月份序列的小工具。圖本身由 viz/options.py 產生 ECharts option；2026-10-02 起不再手畫 SVG。"""
from __future__ import annotations
import datetime as dt


def _add_months(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.month - 1 + n, 12)
    return d.replace(year=d.year + y, month=m + 1, day=1)


def _sum(projects: list[dict], role: str, field: str, n: int = 12, only_plan: bool = False) -> list[float]:
    ps = [p for p in projects if p.get("pva") and (p["has_plan"] or not only_plan)]
    return [sum((p["pva"].get(role) or {}).get(field, [0] * 12)[i] for p in ps) for i in range(n)]


def carry_forward(capacity: list[int], latest_month: int) -> list[int]:
    """latest_month 之後還沒有填報人數，畫成 0 會讓天花板看起來消失。沿用最後一個非零月的值。
    只改畫出來的序列，snapshot 的 capacity 保持原始值（0 代表「還沒填報」）。"""
    out = list(capacity)
    cut = max(0, min(latest_month, len(out)))
    last = next((v for v in reversed(out[:cut]) if v), 0)
    return out[:cut] + [last] * (len(out) - cut)
```

- [ ] **Step 4: 實作 `page.py`**

1. import 區：刪除 `from .charts import timeline_svg, capacity_svg, pva_svg`，加：

```python
from .viz.dash import card, kpi_cards, milestone_table, safe_chart_card, side_nav
from .viz.embed import chart_html, scripts
from .viz.options import customer_bars, forecast_capacity, gantt, kpis, late_codes, load_heatmap, pva, stage_donut
```

2. 刪除 `_passed_mark` 與 `_upcoming` 兩個函式，在原位置加：

```python
def _upcoming_rows(snap: dict, today: str, weeks: int, late: set[str]) -> list[dict]:
    """與舊版同一個視窗：過去 7 天到未來 weeks 週；只看 Briefing 內、非結案／暫停的專案。"""
    rows = []
    for p in snap["projects"]:
        if not p["in_briefing"] or p["stage_cat"] in INACTIVE:
            continue
        for k in ("evt", "dvt", "pvt", "mp"):
            d = p["dates"][k]
            if d and -7 <= _days(d, today) <= weeks * 7:
                rows.append({"date": d, "name": p["name"], "code": p["code"], "customer": p["customer"], "milestone": k,
                             "days_left": _days(d, today), "late": p["code"] in late})
    return sorted(rows, key=lambda r: (r["date"], r["name"]))
```

3. `_appendix_one` 裡這一行：

```python
            cards.append(f'<div><h4>{role}</h4><div class="s">{e(t(lang, "pva_line", plan=f"{plan:.1f}", missing="" if plan else t(lang, "pva_missing"), mon=MONTHS[latest_month - 1], actual=f"{act:.1f}"))}</div>{pva_svg(p["pva"], role, latest_month)}</div>')
```

改成：

```python
            cards.append(f'<div><h4>{role}</h4><div class="s">{e(t(lang, "pva_line", plan=f"{plan:.1f}", missing="" if plan else t(lang, "pva_missing"), mon=MONTHS[latest_month - 1], actual=f"{act:.1f}"))}</div>{chart_html(pva(p, role, latest_month, lang, i), lang)}</div>')
```

4. `render_page` 整個換成：

```python
def _overview(snap: dict, lang: str, today: str, th: dict, late: set[str]) -> str:
    weeks, months = th["upcoming_weeks"], th["timeline_months"]
    rows = _upcoming_rows(snap, today, weeks, late)
    ms = milestone_table(rows, lang) if rows else f'<p class="note">{e(t(lang, "none"))}</p>'
    return (kpi_cards(kpis(snap, lang, th), {"risk": "#decisions"})
            + f'<div class="grid-2">{safe_chart_card(t(lang, "v_c_stage"), lambda: stage_donut(snap, lang), lang)}'
            + f'{safe_chart_card(t(lang, "v_c_customer"), lambda: customer_bars(snap, lang), lang)}</div>'
            + safe_chart_card(t(lang, "v_c_gantt", months=months), lambda: gantt(snap, lang, today, months), lang)
            + f'<div class="grid-3">{safe_chart_card(t(lang, "v_c_heat"), lambda: load_heatmap(snap, lang, th["spare_capacity_pct"]), lang)}'
            + f'{safe_chart_card(t(lang, "v_c_forecast"), lambda: forecast_capacity(snap, lang), lang)}'
            + f'{card(t(lang, "v_c_milestones", weeks=weeks), ms)}</div>')


def render_page(snap: dict, lang: str, today: str, th: dict, echarts: str = "inline") -> str:
    m = snap["meta"]; lm = m["latest_month"]
    if lm < 1:
        raise ValueError("no manpower month in snapshot")   # 整頁都以「最新月」定位，沒有它不該畫出半張報表
    ps = snap["projects"]; cl = [p for p in ps if p["in_control_list"]]
    late = late_codes(snap)
    order = sorted(range(len(ps)), key=lambda i: ps[i]["name"].casefold())   # 附錄依專案名稱字母排序（需求方 2026-09-30）
    options = "".join(f'<option value="{i}">{e(ps[i]["name"])}{", " + e(ps[i]["stage"]) if ps[i]["stage"] else ""}</option>' for i in order)
    appendix = "".join(_appendix_one(ps[i], lang, today, lm, i) for i in order)
    ym = f"{m['report_month'][:4]}-{m['report_month'][4:]}"
    links = "".join(f'<a href="#{a}">{e(t(lang, k))}</a>' for a, k in (("overview", "v_nav_overview"), ("decisions", "v_nav_decisions"),
                                                                          ("health", "v_nav_health"), ("appendix", "v_nav_appendix")))
    side = side_nav(f'<a class="brand" href="#overview">{e(t(lang, "h1"))}</a>', links, t(lang, "v_menu"), label=t(lang, "h1"))
    return f"""<!DOCTYPE html><html lang="{t(lang, "html_lang")}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(t(lang, "doc_title", ym=ym))}</title><style>{CSS}</style></head><body><div class="app">{side}<main class="main">
<header><div><h1>{e(t(lang, "h1"))}</h1><p>{e(t(lang, "intro"))}</p></div>{_title_block(m, lang, len(cl), lm)}</header>
<section id="overview">{_overview(snap, lang, today, th, late)}</section>
<section id="decisions"><h2>{e(t(lang, "s_decisions"))}</h2><p class="lead">{e(t(lang, "s_decisions_lead"))}</p><div class="card">{_exceptions(snap, lang, th)}</div></section>
<section id="health"><h2>{e(t(lang, "s_health"))}</h2><p class="lead">{e(t(lang, "s_health_lead"))}</p><div class="card"><div class="wide">{_health(snap, lang)}</div></div></section>
<section id="appendix"><h2>{e(t(lang, "s_appendix"))}</h2><p class="lead">{e(t(lang, "s_appendix_lead"))}</p><select id="pick">{options}</select><div id="projects">{appendix}</div></section>
<footer><p>{e(t(lang, "foot_1"))}</p><p>{e(t(lang, "foot_2"))}</p><p>{e(t(lang, "foot_3"))}</p></footer>
</main></div>{scripts(echarts)}
<script>(function(){{var s=document.getElementById('pick'),ps=document.querySelectorAll('#projects .proj');function show(i){{ps.forEach(function(p){{p.style.display=p.dataset.idx===String(i)?'':'none';}});if(window.eisCharts)window.eisCharts.init(document.getElementById('projects'));}}s.addEventListener('change',function(){{show(s.value);}});show(s.value);}})();</script>
</body></html>"""
```

（`_stage_strip` 與檔尾的別名列保持不變：`pages_home` 仍用 `stage_strip_html`。）

- [ ] **Step 5: `pages_load.py` 改用新圖**

`src/eis_mcp/web/pages_load.py`：`from ...portfolio.render.charts import capacity_svg` 換成

```python
from ...portfolio.render.viz.dash import chart_card
from ...portfolio.render.viz.options import forecast_capacity
```

並把 `f'{capacity_svg(snap["projects"], snap["capacity"], lm, "en")}</section>'` 換成 `f'{chart_card(forecast_capacity(snap, "en"), "en")}</section>'`。

- [ ] **Step 6: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
git add src/portfolio/render/page.py src/portfolio/render/charts.py src/eis_mcp/web/pages_load.py tests/portfolio/test_page.py tests/portfolio/test_charts.py tests/eis_mcp/test_web.py
git commit -m "feat(report): v2 dashboard layout with inline ECharts; drop hand-drawn SVG charts"
```

---

### Task 8: `/ui/` Overview、Loads、單案頁

**Files:**
- Modify: `src/eis_mcp/web/pages_overview.py`（`overview_body` 改 KPI＋圖表；刪除 `_milestones` 與不再用的 import）
- Modify: `src/eis_mcp/web/pages_load.py`（部門熱度表）
- Modify: `src/eis_mcp/web/pages_project.py`（頂部小卡）
- Modify: `tests/eis_mcp/test_web.py`

**Interfaces:**
- Consumes: `kpis`、`stage_donut`、`customer_bars`、`gantt`、`load_heatmap`、`forecast_capacity`、`late_codes`（Task 2–4）；`kpi_cards`、`card`、`safe_chart_card`、`chart_card`、`milestone_table`（Task 5）；`queries.upcoming`（既有）
- Produces: `overview_body(snap, th, today, weeks) -> str`（簽章不變）

- [ ] **Step 1: 寫失敗的測試**

`tests/eis_mcp/test_web.py`：

`test_overview_shows_decisions_health_and_milestones` 整個換成：

```python
def test_overview_shows_kpis_charts_and_milestones(ingested):
    t = html(ingested, f"/ui/202609/?today={TODAY}")
    assert '<div class="kpis">' in t and "Total projects" in t and 'href="/ui/202609/decisions"' in t and "Report month 2026-09" in t
    for cid in ("stage", "customer", "gantt", "heat-function", "forecast"):
        assert f'id="c-{cid}"' in t and f'id="c-{cid}-data"' in t, cid
    assert '<ol class="ex">' not in t and "<h2>Data health" not in t                 # 已移到各自的分頁
    assert "Milestones within 8 weeks" in t and "THORPE" in t and '<td class="num">-43</td>' in t
    t2 = html(ingested, f"/ui/202609/?today={TODAY}&weeks=2")
    assert "Milestones within 2 weeks" in t2 and '<td class="num">-43</td>' not in t2
    assert get(ingested, "/ui/202609/?weeks=0").status_code == 400
    assert get(ingested, "/ui/202609/?today=13/09/2026").status_code == 400


def test_overview_survives_snapshot_without_capacity(ingested):
    store = ingested.state.eis.store
    f = store.snapshot_dir("202609") / "portfolio.json"
    snap = json.loads(f.read_text(encoding="utf-8"))
    del snap["capacity"]
    f.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8"); store.invalidate()
    t = html(ingested, f"/ui/202609/?today={TODAY}")
    assert "Not in this snapshot." in t and 'id="c-stage"' in t


def test_loads_page_has_department_heatmap(ingested):
    t = html(ingested, "/ui/202609/loads")
    assert 'id="c-heat-dept"' in t and "Grey cells: nobody keyed in." in t


def test_project_page_top_cards(ingested):
    t = html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
    top = t[t.index('<div class="kpis four">'):t.index("</div></section>")]
    assert '<span class="k-label">Stage</span>' in top and '<span class="k-label">FTE, Aug</span><b class="k-value">12.0</b>' in top
```

`test_tables_scroll_on_narrow_screens` 的前三行換成：

```python
    t = html(ingested, f"/ui/202609/?today={TODAY}")
    ms = t[t.index("<h3>Milestones"):]
    assert '<div class="wide"><table>' in ms
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/eis_mcp/test_web.py -q`
Expected: FAIL（Overview 仍是舊內容；Loads 沒有 `c-heat-dept`；單案頁沒有小卡）

- [ ] **Step 3: 實作 Overview**

`src/eis_mcp/web/pages_overview.py`：

1. import 區換成：

```python
from __future__ import annotations
from html import escape as e
from ...portfolio.render.viz.dash import card, kpi_cards, milestone_table, safe_chart_card
from ...portfolio.render.viz.options import customer_bars, forecast_capacity, gantt, kpis, late_codes, load_heatmap, stage_donut
from .. import queries
from .shell import fmt_month
```

2. 刪除 `_milestones` 函式；`overview_body` 換成：

```python
def _milestone_card(month: str, snap: dict, today: str, weeks: int) -> str:
    up = queries.upcoming(snap, today, weeks)
    late = late_codes(snap)
    by_code = {p["code"]: p for p in snap["projects"]}
    rows = [{**r, "customer": by_code[r["code"]]["customer"], "late": r["code"] in late} for r in up["milestones"]]
    form = (f'<form method="get" class="filters"><label>Weeks <input type="number" name="weeks" value="{weeks}" min="1" max="52"></label>'
            f'<label>Today <input type="text" name="today" value="{e(today)}" size="10"></label><button>Apply</button></form>')
    table = (milestone_table(rows, "en", link=lambda c: f"/ui/{month}/projects/{c}") if rows
             else f'<p class="empty">No EVT/DVT/PVT/MP within ±{weeks} weeks of {e(today)}.</p>')
    return card(f"Milestones within {weeks} weeks", form + table +
                '<p class="dim">Negative days left = already passed. Active projects only (in briefing, not terminated or suspended).</p>')


def overview_body(snap: dict, th: dict, today: str, weeks: int) -> str:
    month = snap["meta"]["report_month"]
    months = int(th.get("timeline_months", 6)); spare = float(th.get("spare_capacity_pct", 85))
    return (f'<section>{kpi_cards(kpis(snap, "en", th), {"risk": f"/ui/{month}/decisions"})}'
            f'<div class="grid-2">{safe_chart_card("Projects by stage", lambda: stage_donut(snap, "en"), "en")}'
            f'{safe_chart_card("Projects by customer", lambda: customer_bars(snap, "en"), "en")}</div>'
            f'{safe_chart_card(f"Timeline, next {months} months", lambda: gantt(snap, "en", today, months), "en")}'
            f'<div class="grid-3">{safe_chart_card("Resource load by function", lambda: load_heatmap(snap, "en", spare), "en")}'
            f'{safe_chart_card("Forecast vs capacity", lambda: forecast_capacity(snap, "en"), "en")}'
            f'{_milestone_card(month, snap, today, weeks)}</div></section>')
```

（`months_body` 保持不變：首頁仍使用。）

- [ ] **Step 4: Loads 部門熱度表**

`src/eis_mcp/web/pages_load.py`：import 區 `from ...portfolio.render.viz.options import forecast_capacity` 改成 `from ...portfolio.render.viz.options import forecast_capacity, load_heatmap`；`loads_body` 的 return 中，`f'<section><h2>{res["count"]} department...` 那一段之前插入：

```python
            f'<section><h2>Load by department</h2><p class="lead">Every department, every month. Pick a cell in the table below for the numbers.</p>'
            f'{chart_card(load_heatmap(snap, "en", spare_pct, by="dept"), "en")}</section>'
```

- [ ] **Step 5: 單案頁頂部小卡**

`src/eis_mcp/web/pages_project.py`：import 區加 `import datetime as dt` 與 `from ...portfolio.render.viz.dash import kpi_cards`；在 `def project_body(` 之前加：

```python
def _top_cards(p: dict, lm: int, today: str) -> str:
    nxt = next(((k, p["dates"][k]) for k in ("evt", "dvt", "pvt", "mp") if p["dates"].get(k) and p["dates"][k] >= today), None)
    days = (dt.date.fromisoformat(nxt[1]) - dt.date.fromisoformat(today)).days if nxt else None
    items = [{"key": "stage", "label": "Stage", "value": p["stage"] or "–", "sub": p["stage_cat"] or "not in briefing"},
             {"key": "customer", "label": "Customer", "value": p["customer"] or "–", "sub": p.get("biz_type", "")},
             {"key": "next", "label": "Next milestone", "value": f"{nxt[0].upper()} {nxt[1]}" if nxt else "–",
              "sub": f"in {days} days" if nxt else "none ahead in the briefing"},
             {"key": "fte", "label": f"FTE, {MONTHS[lm - 1]}", "value": f'{p["fte"][lm - 1]:.1f}', "sub": "Resource Summary"}]
    return kpi_cards(items, cls="four")
```

並把 `project_body` 的 `return (f'<section>{kv}{cmp_}</section>'` 改成 `return (f'<section>{_top_cards(p, lm, today)}{kv}{cmp_}</section>'`。

- [ ] **Step 6: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
git add src/eis_mcp/web/pages_overview.py src/eis_mcp/web/pages_load.py src/eis_mcp/web/pages_project.py tests/eis_mcp/test_web.py
git commit -m "feat(web): overview KPIs and charts, department heatmap, project top cards"
```

---

### Task 9: 瀏覽器實測與文件

**Files:**
- Create: `scripts/check_layout.py`（Playwright：寬度溢出、圖表是否真的畫出、console 錯誤、截圖）
- Modify: `README.md`（§7.8 補一段 v2 版面說明）
- Modify: `AGENTS.md`（MCP server 段落補一行）
- Modify: `docs/superpowers/specs/2026-10-02-eis-dashboard-redesign-design.md`（狀態改為已實作）

**Interfaces:**
- Consumes: 整個分支
- Produces: `python scripts/check_layout.py --base URL --report FILE --out DIR`：exit 0 全過；exit 1 列出失敗項

- [ ] **Step 1: 寫檢查腳本**

`scripts/check_layout.py`：

```python
"""版面實測：每頁在 1440 與 375 寬度下無橫向溢出、每個 [data-chart] 都畫出 <svg>、沒有 console error，並截圖。
python scripts/check_layout.py --base http://127.0.0.1:8796 --month 202609 --code BR0000015346 --report out/report.html --out /tmp/shots"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

WIDTHS = (1440, 375)


def check(page, url: str, name: str, out: Path) -> list[str]:
    errs: list[str] = []
    page.on("console", lambda m: errs.append(f"{name}: console {m.type}: {m.text}") if m.type == "error" else None)
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(600)
    fails = []
    for w in WIDTHS:
        page.set_viewport_size({"width": w, "height": 900})
        page.wait_for_timeout(400)
        sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        if sw > iw:
            fails.append(f"{name} @{w}: horizontal overflow {sw} > {iw}")
        empty = page.evaluate("""[...document.querySelectorAll('[data-chart]')].filter(el => el.offsetParent !== null && !el.querySelector('svg')).map(el => el.id)""")
        if empty:
            fails.append(f"{name} @{w}: charts not drawn {empty}")
        page.screenshot(path=str(out / f"{name}_{w}.png"), full_page=True)
    return fails + errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--month", required=True); ap.add_argument("--code", required=True)
    ap.add_argument("--report", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    pages = {"overview": f"{a.base}/ui/{a.month}/", "decisions": f"{a.base}/ui/{a.month}/decisions", "loads": f"{a.base}/ui/{a.month}/loads",
             "health": f"{a.base}/ui/{a.month}/health", "project": f"{a.base}/ui/{a.month}/projects/{a.code}",
             "report": Path(a.report).resolve().as_uri()}
    fails: list[str] = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, url in pages.items():
            fails += check(b.new_page(), url, name, out)
        page = b.new_page(); page.goto(pages["report"], wait_until="networkidle")    # 附錄切換後 PVA 圖要畫出來
        page.select_option("#pick", index=1); page.wait_for_timeout(500)
        if page.evaluate("[...document.querySelectorAll('#projects .proj')].filter(p => p.style.display !== 'none').some(p => [...p.querySelectorAll('[data-chart]')].some(c => !c.querySelector('svg')))"):
            fails.append("report: appendix charts not drawn after switching project")
        b.close()
    print("\n".join(fails) or f"all checks passed; screenshots in {out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 用真資料起 server 並執行**

```bash
W=$(mktemp -d); mkdir -p $W/in $W/data/snapshots
cp input-08/* $W/in/ && rm $W/in/BU10_Project_Briefing_20260907.xlsx && cp input-08-2/BU10_Project_Briefing_2026_v2.xlsx $W/in/
.venv/bin/python -m src.portfolio.cli --input $W/in --report-month 202609 --today 2026-09-29 --snapshots $W/data/snapshots --out $W/out
printf 'tokens:\n  - token: %s\n    name: check\n    role: viewer\n' "$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')" > $W/data/tokens.yaml
chmod -R go-rwx $W/data
.venv/bin/python -m src.eis_mcp --data $W/data --host 127.0.0.1 --port 8796 > $W/server.log 2>&1 &
sleep 3
.venv/bin/python scripts/check_layout.py --base http://127.0.0.1:8796 --month 202609 --code BR0000015346 --report $W/out/portfolio_202609_en.html --out $W/shots
```

Expected: `all checks passed; screenshots in …`。有失敗項：照 superpowers:systematic-debugging 找原因、修程式（含會失敗的測試）再重跑。最後打開 `$W/shots/overview_1440.png`、`overview_375.png`、`report_1440.png` 目視：KPI 卡上緣色條與底卡交界放大看無凹口、圖表有數字、Gantt 有今日線。結束後 `kill %1`。

- [ ] **Step 3: 文件**

`README.md`：§7.8 末尾加一段：

```markdown
**版面（2026-10-02 起）**：左側導覽 Overview／Decisions／Projects／Loads／Data health／Report。Overview 是 KPI 卡＋Stage／Customer 分布、六個月 Gantt、Function 負載熱度表、Forecast vs Capacity、未來里程碑；Decisions 是本月例外清單；Data health 併入原 Corrections（舊網址 301 轉址）。圖表用 vendor 進 repo 的 ECharts 5.6.0（`vendor/echarts/`），月報內嵌、網頁走 `/ui/static/echarts.min.js`；每張圖下方的「Data table」是同一份數字。版面實測：`python scripts/check_layout.py --help`。
```

`AGENTS.md`：「## MCP server（src/eis_mcp，2026-09-19 起）」段落最後加：

```markdown
- 版面（2026-10-02）：v2 儀表板（`src/portfolio/render/viz/`）。**圖上的數字只在 Python 算**（`options.py` 產生 ECharts option 與同一份資料表），JS 只畫；缺資料用獨立類別或灰格，不補 0。At Risk = 既有 `milestones_passed` ∪ `mp_slipped`，不是新規則。`vendor/echarts/` 必須跟著部署（`deploy/install.sh` 已放行），缺檔 server 拒絕啟動。
```

`docs/superpowers/specs/2026-10-02-eis-dashboard-redesign-design.md` 第 4 行改成：

```markdown
狀態：已實作（計畫 docs/superpowers/plans/2026-10-02-eis-dashboard-redesign.md）
```

- [ ] **Step 4: 跑測試**

Run: `.venv/bin/python -m pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/check_layout.py README.md AGENTS.md docs/superpowers/specs/2026-10-02-eis-dashboard-redesign-design.md
git commit -m "docs: v2 dashboard layout notes and a browser layout check script"
```

---

## Self-Review 紀錄

- **Spec 覆蓋**：§3 原則 1（數字在 server）→ Task 1 `Chart`/`to_json`、Task 2–4；原則 2 缺口明示 → Task 2（Not in Briefing、(blank)/NA）、Task 4（no-data 格、no budget plan、carried 虛線、覆蓋率）；原則 3 At Risk → Task 2 `at_risk_codes`；原則 4 無 JS → Task 1 `<details>`＋`<noscript>`、Task 7 測試；原則 5 PII → Task 7 `find_pii` 測試（`respond()` 不變）；原則 6 零外網 → Task 1 vendor、Task 7 無 `<script src`。§4.1 交付 → Task 1、6。§5.1 外框與導覽、轉址 → Task 5、6；§5.2 Overview 與月報 → Task 7、8；§5.3 其他頁 → Task 6（Decisions、Health）、8（Loads、單案頁）。§6 各圖口徑 → Task 2–4 測試逐一對照。§7 錯誤處理：舊快照 → `safe_chart_card`；JS 被擋 → `<noscript>`＋表格；缺 echarts 檔 → Task 6 啟動檢查；NaN → Task 1。§9 測試 → 各 Task Step 1；版面 → Task 9。
- **與 spec 的細部差異（刻意）**：
  1. spec §4 列了 `tables.py`；資料表與嵌入同時產生，併在 `embed.chart_html`，少一個檔案、不會兩邊不同步。
  2. spec §6 Forecast 覆蓋率字串寫「Plan covers {n_plan}/{n_projects}」；沿用既有已核准字串 `cap_budget_note`（「Budget covers {covered} / {total} projects, BU RD + PM only」），母數是有 Control List 的專案，與舊圖同口徑。
  3. spec §6 熱度表無資料格寫「`null`」；ECharts 熱度表遇到 null 不畫格子，所以改放在第二個 series（灰格、不顯示數字），資料表中仍為 `None`（顯示「–」）。測試斷言 series[0] 不含這些格。
  4. 里程碑狀態「Passed」依舊版語意分兩色：階段未前進（在 `milestones_passed`）為紅，已正常往下走為灰。
- **Placeholder 掃描**：無 TBD/TODO；每個程式步驟附完整程式碼。「原樣剪下」的兩處（`linked_exceptions`、`_linked_health`/`health_section`）是搬移既有函式，內容不變，故不重抄。
- **型別一致**：`Chart` 欄位順序（id, title, option, headers, rows, height, variants, note）在 Task 1 定義，Task 2–4 一律用位置參數前 5 個＋關鍵字其餘；`pva(p, role, latest_month, lang, idx)` 在 Task 4 定義、Task 7 呼叫；`kpi_cards(items, href, cls)`、`safe_chart_card(title, build, lang)` 在 Task 5 定義、Task 7–8 呼叫；`render_shell(..., decisions=)` 在 Task 6 定義、routes 全部帶上。
- **Review Focus**：五項各有對應測試（部署 vendor → Task 6；script 跳脫 → Task 1、7；附錄隱藏圖 → Task 7、9；舊快照 → Task 5、7、8；無 JS 資料表 → Task 7）。
