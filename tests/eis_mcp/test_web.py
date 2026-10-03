"""/ui/* 網頁：免 token、唯讀、每頁出口過 PII 檢查並寫 audit。用 ASGI transport 直接打，不啟 MCP lifespan。"""
import json
import httpx
from src.eis_mcp.web.shell import render_shell
from src.portfolio.model.snapshot import write_snapshot
from tests.eis_mcp.conftest import TODAY, _run, post_raw

CODE = "BR0000015346"


def get(app, path):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            return await c.get(path)
    return _run(go())


def html(app, path, status=200):
    r = get(app, path)
    assert r.status_code == status, (r.status_code, r.text[:300])
    assert r.headers["content-type"].startswith("text/html")
    return r.text


def clone_month(app, month, **changes):
    """把 202609 快照複製成另一個月份，第一個專案套上 changes。"""
    store = app.state.eis.store
    snap = json.loads((store.snapshot_dir("202609") / "portfolio.json").read_text(encoding="utf-8"))
    snap["meta"]["report_month"] = month
    snap["projects"][0].update(changes)
    write_snapshot(snap, store.snapshots_root); store.invalidate()


def last_audit(app):
    return app.state.eis.audit.rows()[-1]


# ---- 認證邊界 ----
def test_ui_is_public_but_mcp_and_upload_still_need_token(app):
    assert get(app, "/ui/").status_code == 200
    assert get(app, "/ui").status_code == 307 and get(app, "/ui").headers["location"] == "/ui/"
    assert post_raw(app, None, "/mcp", json={}).status_code == 401
    assert post_raw(app, None, "/upload/202609").status_code == 401
    assert get(app, "/uiX/").status_code == 401
    row = last_audit(app)
    assert row["kind"] == "web" and row["action"] == "/ui" and row["status"] == "ok"


# ---- 月份清單與 latest ----
def test_months_page_empty(app):
    t = html(app, "/ui/")
    assert "nothing ingested yet" in t.lower()
    assert get(app, "/ui/latest/").status_code == 404


def test_months_page_listed(ingested):
    t = html(ingested, "/ui/")
    assert "202609" in t and "latest" in t and 'href="/ui/202609/"' in t and "Alice" not in t
    assert "Some One" not in t                                   # 上傳檔名（含 PM 姓名）不出現
    assert " KB" in t
    r = get(ingested, "/ui/latest/")
    assert r.status_code == 307 and r.headers["location"] == "/ui/202609/"


def test_report_html_is_served_verbatim(ingested):
    t = html(ingested, "/ui/202609/report.html")
    assert t == ingested.state.eis.store.report_html("202609")
    assert "Decisions this month" in t


# ---- 錯誤頁 ----
def test_unknown_and_bad_month_are_404_with_month_links(ingested):
    t = html(ingested, "/ui/202501/report.html", 404)
    assert "No data for 202501" in t and 'href="/ui/202609/"' in t
    t = html(ingested, "/ui/2026-09/report.html", 404)
    assert "No data for 2026-09" in t
    assert last_audit(ingested)["kind"] == "web" and last_audit(ingested)["status"] == "error"


def test_broken_snapshot_is_503(ingested):
    store = ingested.state.eis.store
    (store.snapshot_dir("202609") / "portfolio.json").write_text("{not json", encoding="utf-8"); store.invalidate()
    t = html(ingested, "/ui/202609/", 503)
    assert "unreadable" in t and "ingest_month('202609')" in t


# ---- PII 與 audit ----
def test_pii_hit_withholds_page_and_audits(ingested, monkeypatch):
    monkeypatch.setattr("src.eis_mcp.web.routes.find_pii", lambda text, *a, **kw: ["LA0000001"])
    t = html(ingested, "/ui/202609/report.html", 503)
    assert "withheld" in t and "LA0000001" not in t
    row = last_audit(ingested)
    assert row["kind"] == "web" and row["status"] == "rejected_pii" and row["name"] is None


def test_every_ok_page_writes_audit_row(ingested):
    html(ingested, "/ui/")
    row = last_audit(ingested)
    assert row["kind"] == "web" and row["action"] == "/ui/" and row["status"] == "ok" and row["role"] is None


def test_unexpected_exception_is_500_and_audited(ingested, monkeypatch):
    monkeypatch.setattr("src.eis_mcp.web.routes.pages_overview.overview_body", lambda *a, **k: 1 / 0)
    t = html(ingested, "/ui/202609/", 500)
    assert "Server error" in t
    assert "Traceback" not in t
    assert "ZeroDivisionError" not in t
    row = last_audit(ingested)
    assert row["status"] == "error" and "ZeroDivisionError" in row["detail"]


def test_nav_month_is_not_over_escaped():
    t = render_shell(title="x", body="", months=["202609"], month="202609")
    assert 'href="/ui/202609/projects"' in t


def test_nav_forms_are_not_nested():
    """曾因巢狀 <form> 讓搜尋框在瀏覽器裡失效；現在 nav 有月份與搜尋兩個表單，必須並排、不可巢狀。"""
    t = render_shell(title="x", body="", months=["202609"], month="202609")
    nav = t[t.index("<nav"):t.index("</nav>")]
    assert nav.count("<form") == 2 and nav.count("</form>") == 2
    first_close = nav.index("</form>")
    assert nav.index("<form", nav.index("<form") + 1) > first_close
    assert 'action="/ui/202609/projects"' in nav
    assert 'name="q"' in nav
    assert "form=\"" not in nav


# ---- 總覽 ----
def test_overview_shows_kpis_charts_and_milestones(ingested):
    t = html(ingested, f"/ui/202609/?today={TODAY}")
    assert '<div class="kpis">' in t and "Total projects" in t and 'href="/ui/202609/decisions"' in t and "Report month 2026-09" in t
    assert '<table class="bars-t">' in t                                            # customer：HTML 長條（2026-10-03 選項 3）
    for cid in ("stage", "category", "gantt", "forecast", "fu"):
        assert f'id="c-{cid}"' in t and f'id="c-{cid}-data"' in t, cid
    assert '<ol class="ex">' not in t and "<h2>Data health" not in t                 # 已移到各自的分頁
    ms = lambda page: page[page.index("<h3>Milestones"):page.index("</table>", page.index("<h3>Milestones"))]  # noqa: E731
    assert "Milestones, next 8 weeks" in t and "THORPE" in ms(t)                    # MP 2026-07-31：距 2026-09-12 已過 43 天，仍在 ±8 週內
    t2 = html(ingested, f"/ui/202609/?today={TODAY}&weeks=2")
    assert "Milestones, next 2 weeks" in t2 and "THORPE" not in ms(t2)
    assert get(ingested, "/ui/202609/?weeks=0").status_code == 400
    assert get(ingested, "/ui/202609/?today=13/09/2026").status_code == 400


def test_overview_survives_snapshot_without_capacity(ingested):
    store = ingested.state.eis.store
    f = store.snapshot_dir("202609") / "portfolio.json"
    snap = json.loads(f.read_text(encoding="utf-8"))
    del snap["capacity"]
    f.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8"); store.invalidate()
    t = html(ingested, f"/ui/202609/?today={TODAY}")
    assert "Not in this month’s data." in t and 'id="c-stage"' in t


def test_loads_page_has_department_heatmap(ingested):
    t = html(ingested, "/ui/202609/loads")
    assert 'id="c-heat-dept"' in t and "Grey cells: nobody reported." in t


def test_project_page_top_cards(ingested):
    t = html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
    top = t[t.index('<div class="kpis four">'):]
    assert '<span class="k-label">Stage</span>' in top and '<span class="k-label">FTE, Aug</span><b class="k-value">12.0</b>' in top


# ---- 專案 ----
def add_twin(app):
    """快照裡多放一個 THORPE2，讓「多筆候選」有東西可測。"""
    store = app.state.eis.store
    f = store.snapshot_dir("202609") / "portfolio.json"
    snap = json.loads(f.read_text(encoding="utf-8"))
    twin = dict(snap["projects"][0]); twin["code"] = "BR0000099999"; twin["name"] = "THORPE2"; twin["stage_cat"] = "POC"; twin["customer"] = "Beta"
    snap["projects"].append(twin)
    f.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8"); store.invalidate()


def add_hostile(app):
    """快照裡多放一個帶 HTML/引號的敵意專案，用來驗證輸出全程轉義。"""
    store = app.state.eis.store
    f = store.snapshot_dir("202609") / "portfolio.json"
    snap = json.loads(f.read_text(encoding="utf-8"))
    hostile = dict(snap["projects"][0])
    hostile["code"] = "BR0000088888"; hostile["name"] = "A<b>&C"; hostile["customer"] = 'X"Y'
    snap["projects"].append(hostile)
    f.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8"); store.invalidate()


def test_project_text_is_escaped(ingested):
    add_hostile(ingested)
    t = html(ingested, "/ui/202609/projects")
    assert "A&lt;b&gt;&amp;C" in t
    assert "<b>&C" not in t
    assert 'X&quot;Y' in t
    t = html(ingested, "/ui/202609/projects/BR0000088888")
    assert "A&lt;b&gt;&amp;C" in t
    assert "<b>&C" not in t


def test_projects_table_filters_and_single_hit_redirect(ingested):
    add_twin(ingested)
    t = html(ingested, "/ui/202609/projects")
    assert t.count('class="row-link" href="/ui/202609/projects/BR0000') == 2 and "THORPE2" in t and "2 projects" in t
    assert 'href="/ui/202609/projects?stage_cat=POC"' in t and 'value="Beta"' in t     # Stage 是計數標籤，其餘篩選是下拉
    t = html(ingested, "/ui/202609/projects?stage_cat=POC")
    assert "THORPE2" in t and 'projects/BR0000015346"' not in t and 'aria-current="true" href="/ui/202609/projects?stage_cat=POC"' in t
    t = html(ingested, "/ui/202609/projects?customer=Beta&stage_cat=")
    assert "1 project" in t and "THORPE2" in t
    r = get(ingested, "/ui/202609/projects?q=THORPE2")
    assert r.status_code == 307 and r.headers["location"] == "/ui/202609/projects/BR0000099999"
    t = html(ingested, "/ui/202609/projects?q=zzz")
    assert "0 projects" in t


def test_project_page_candidates_and_not_found(ingested):
    t = html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
    assert "THORPE" in t and CODE in t and 'id="c-pva-0-burd"' in t and "PVT" in t and "Aug" in t and "12.0" in t
    assert "compare with previous month" not in t.lower()                     # 只有一個月份
    t = html(ingested, f"/ui/202609/projects/thorpe?today={TODAY}")           # 名稱也可以當 path 參數
    assert CODE in t
    add_twin(ingested)
    t = html(ingested, "/ui/202609/projects/THORP")
    assert "Several projects match" in t and 'href="/ui/202609/projects/BR0000099999"' in t
    t = html(ingested, "/ui/202609/projects/nope", 404)
    assert "no project in 202609 matches 'nope'" in t and 'href="/ui/202609/projects"' in t


def test_project_page_links_previous_month_when_present(ingested):
    clone_month(ingested, "202610", stage="MP")
    t = html(ingested, f"/ui/202610/projects/{CODE}")
    assert f'href="/ui/202610/projects/{CODE}/diff?to=202609"' in t


# ---- loads / corrections ----
def test_loads_page_filters_and_capacity_chart(ingested):
    t = html(ingested, "/ui/202609/loads")
    assert 'id="c-forecast"' in t and "Capacity" in t and "latest load" in t.lower() and "BA80700R01" in t
    assert 'class="num sig">100<' not in t                                     # 100% 不標橘；橘色只給低於 spare_capacity_pct 的
    assert 'class="num sig">62<' in t                                        # 低於 spare_capacity_pct(85) 的部門標橘
    n_rows = t.count("<tr><td>")
    t2 = html(ingested, "/ui/202609/loads?min_util=1000")
    assert "No department" in t2 and t2.count("<tr><td>") < n_rows
    assert get(ingested, "/ui/202609/loads?min_util=abc").status_code == 400


def test_corrections_page(ingested):
    t = html(ingested, "/ui/202609/health")
    assert "No corrections" in t
    store = ingested.state.eis.store
    f = store.snapshot_dir("202609") / "portfolio.json"
    snap = json.loads(f.read_text(encoding="utf-8"))
    snap["issues"].append({"level": "track", "check": "cross_month_correction", "detail": "THORPE Jul FTE 17.0 -> 12.0", "source": "snapshot", "code": CODE})
    f.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8"); store.invalidate()
    t = html(ingested, "/ui/202609/health")
    assert "17.0 -&gt; 12.0" in t and f'href="/ui/202609/projects/{CODE}"' in t


# ---- diff ----
def test_diff_page_changed_identical_and_errors(ingested):
    clone_month(ingested, "202610", stage="MP", fte=[12.0] * 8 + [5.0] + [0.0] * 3)
    t = html(ingested, f"/ui/202610/projects/{CODE}/diff?to=202609")
    assert "stage" in t and "MP" in t and "PVT" in t and "fte" in t and "5.0" in t and "202610" in t and "202609" in t
    clone_month(ingested, "202611")                                          # 內容與 202609 相同 → identical
    t = html(ingested, f"/ui/202611/projects/{CODE}/diff?to=202609")
    assert "identical" in t.lower()
    assert get(ingested, f"/ui/202609/projects/{CODE}/diff").status_code == 400
    assert get(ingested, f"/ui/202609/projects/{CODE}/diff?to=202501").status_code == 404
    assert get(ingested, "/ui/202609/projects/BR0000000000/diff?to=202610").status_code == 404


def test_diff_flatten():
    from src.eis_mcp.web.pages_project import flatten_changes
    ch = {"stage": {"a": "PVT", "b": "MP"}, "dates": {"mp": {"a": None, "b": "2026-01-01"}}, "tasks": {"a_count": 1, "b_count": 2},
          "pva": {"BU RD": {"plan": {"a": [1.0], "b": [2.0]}}}}
    assert flatten_changes(ch) == [("dates.mp", "–", "2026-01-01"), ("pva.BU RD.plan", "[1.0]", "[2.0]"), ("stage", "PVT", "MP"), ("tasks (count)", "1", "2")]
    added = {"pva": {"FU RD": {"a": None, "b": {"role": "FU RD", "plan": [1.0], "actual": [0.0]}}}}
    assert flatten_changes(added) == [("pva.FU RD", "–", "{role: FU RD, plan: [1.0], actual: [0.0]}")]


# ---- 2026-10-01 review 修正 ----
def snap_date_iso(app, month="202609"):
    sd = app.state.eis.store.load_snapshot(month)["meta"]["snap_date"]
    return f"{sd[:4]}-{sd[4:6]}-{sd[6:]}"


def test_search_by_code_or_exact_name_goes_to_project(ingested):
    add_twin(ingested)                                                        # THORPE 與 THORPE2：子字串比對會命中兩筆
    for q in (CODE, CODE.lower(), "THORPE", "thorpe"):
        r = get(ingested, f"/ui/202609/projects?q={q}")
        assert r.status_code == 307 and r.headers["location"] == f"/ui/202609/projects/{CODE}", q
    t = html(ingested, "/ui/202609/projects?q=THORP")                         # 不是完全相同 → 仍是列表
    assert "2 projects" in t


def test_exceptions_and_health_link_to_projects(ingested):
    t = html(ingested, f"/ui/202609/decisions?today={TODAY}")
    ex = t[t.index('<ol class="ex">'):t.index("</ol>")]
    assert f'href="/ui/202609/projects/{CODE}"' in ex
    health = html(ingested, "/ui/202609/health")
    health = health[health.index("<h1>Data health"):]
    assert "<details" in health and "already listed on the Decisions page" in health   # decide 級與 Decisions 重複，收合


def test_today_defaults_to_snapshot_date(ingested):
    iso = snap_date_iso(ingested)
    t = html(ingested, "/ui/202609/")
    ms = lambda page: page[page.index("<h3>Milestones"):page.index("</table>", page.index("<h3>Milestones"))]  # noqa: E731
    assert ms(t) == ms(html(ingested, f"/ui/202609/?today={iso}"))          # 預設 today＝快照日（表單拿掉後仍可用 ?today=）
    t = html(ingested, f"/ui/202609/projects/{CODE}")
    assert "THORPE" in t                                                      # 單案頁也以快照日期為準（不再用 server 當天）


def test_milestone_footnote_matches_inactive_rule(ingested):
    t = html(ingested, f"/ui/202609/?today={TODAY}")
    assert "Active projects only (in the Briefing, not terminated or suspended)." in t


def test_meta_line_is_readable(ingested):
    t = html(ingested, "/ui/202609/")
    assert "Report month 2026-09" in t and "manpower reported through" in t and f"Briefing {snap_date_iso(ingested)}" in t
    assert "latest_month" not in t[t.index("<header>"):t.index("</header>")]


def test_diff_against_same_month_is_400_and_picker_leaves_diff(ingested):
    assert get(ingested, f"/ui/202609/projects/{CODE}/diff?to=202609").status_code == 400
    clone_month(ingested, "202610", stage="MP")
    t = html(ingested, f"/ui/202610/projects/{CODE}/diff?to=202609")
    nav = t[t.index("<nav"):t.index("</nav>")]
    assert "diff" not in nav and f'value="projects/{CODE}"' in nav


def test_month_picker_works_without_js(ingested):
    t = html(ingested, "/ui/202609/projects")
    nav = t[t.index("<nav"):t.index("</nav>")]
    assert "onchange" not in t and 'action="/ui/go"' in nav and 'aria-label="Search projects"' in nav
    r = get(ingested, "/ui/go?month=202609&page=projects%3Fstage_cat%3DPOC")
    assert r.status_code == 307 and r.headers["location"] == "/ui/202609/projects?stage_cat=POC"
    r = get(ingested, "/ui/go?month=202609&page=")
    assert r.status_code == 307 and r.headers["location"] == "/ui/202609/"
    for bad in ("//evil.example", "/x", "..%2Fmcp", "http:x", "a%5Cb"):
        assert get(ingested, f"/ui/go?month=202609&page={bad}").status_code == 400, bad
    assert get(ingested, "/ui/go?month=2026-09&page=").status_code == 404


def test_latest_task_month_is_open(ingested):
    t = html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
    tasks = t[t.index('<h2>Tasks'):]
    assert tasks.count('<details class="month" open>') == 1
    assert '<details class="month">' not in tasks or tasks.index('<details class="month" open>') < tasks.index('<details class="month">')


def test_tables_scroll_on_narrow_screens(ingested):
    t = html(ingested, f"/ui/202609/?today={TODAY}")
    ms = t[t.index("<h3>Milestones"):]
    assert '<div class="wide"><table>' in ms
    assert "@media(max-width:640px)" in t
    add_twin(ingested)
    t = html(ingested, "/ui/202609/projects/THORP")
    assert '<div class="wide"><table>' in t


def test_open_links_can_wrap(ingested):
    """連結之間要有空白：沒有斷行點時整串變成一個長字，手機寬度下把例外清單撐到 1000px 以上（2026-10-01 實機看到）。"""
    t = html(ingested, f"/ui/202609/decisions?today={TODAY}")
    opens = [seg[:seg.index("</div>")] for seg in t.split('<div class="open">')[1:]]
    assert opens and all("</a><a" not in o for o in opens)


def test_project_page_dates_and_footnote_are_readable(ingested):
    t = html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
    assert "latest_month =" not in t and "Manpower reported through" in t
    hist = t[t.index('id="c-mp-drift"'):]
    assert "<td>2026-" in hist and "<td>2026090" not in hist


# ---- 首頁（2026-10-01：中英並列 landing page）----
def test_home_is_a_launchpad_without_long_explanations(ingested):
    """2026-10-03 需求方：首頁只要簡單的 landing page，不要過多文字。"""
    t = html(ingested, "/ui/")
    body = t[t.index("</nav>"):]
    assert "BU10 Portfolio Review" in t and "BU10 專案組合檢討" in t and "Report month 2026-09" in body
    for gone in ("Where to start", "Terms", "Read-only", "Use it from an AI agent", "Monthly review of BU10 projects"):
        assert gone not in body, gone
    assert 'action="/ui/202609/projects"' in body                                         # 搜尋是首頁的主要動作


def test_home_status_tiles_link_to_their_pages(ingested):
    from src.portfolio.render.viz.options import at_risk_codes
    snap = ingested.state.eis.store.load_snapshot("202609")
    risk = len(at_risk_codes(snap, ingested.state.eis.cfg.thresholds["mp_slip_days"]))
    t = html(ingested, "/ui/")
    tiles = t[t.index('<div class="kpis home-tiles">'):]
    tiles = tiles[:tiles.index("</div></section>") if "</div></section>" in tiles else len(tiles)]
    assert f'href="/ui/202609/decisions"><span class="k-label">At risk</span><b class="k-value">{risk}</b>' in tiles
    assert f'<span class="k-label">Decisions</span><b class="k-value">{len(snap["exceptions"])}</b>' in tiles
    assert f'href="/ui/202609/projects"><span class="k-label">Projects</span><b class="k-value">{len(snap["projects"])}</b>' in tiles
    assert 'href="/ui/202609/loads"><span class="k-label">FTE, Aug</span>' in tiles


def test_home_sidebar_carries_the_latest_month_navigation(ingested):
    t = html(ingested, "/ui/")
    nav = t[t.index("<nav"):t.index("</nav>")]
    assert 'href="/ui/202609/decisions"' in nav and 'href="/ui/202609/projects"' in nav and 'href="/ui/" class="brand on"' in nav
    body = t[t.index("</nav>"):]
    assert 'href="/ui/202609/report.html"' in body and 'href="/ui/mcp"' in body and "Data history" in body


def test_home_when_latest_snapshot_is_broken_still_explains(ingested):
    store = ingested.state.eis.store
    (store.snapshot_dir("202609") / "portfolio.json").write_text("{not json", encoding="utf-8"); store.invalidate()
    t = html(ingested, "/ui/")
    assert "BU10 Portfolio Review" in t and "could not be read" in t and "Data history" in t


def test_nav_brand_links_home_on_every_page(ingested):
    for path in ("/ui/", f"/ui/202609/?today={TODAY}", "/ui/202609/loads"):
        t = html(ingested, path)
        nav = t[t.index("<nav"):t.index("</nav>")]
        assert '<a href="/ui/" class="brand' in nav and "BU10 Portfolio Review" in nav, path


# ---- MCP 服務說明（2026-10-01：首頁可連到，agent 讀 /ui/mcp.md 照著安裝）----
def get_with_host(app, path, host):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            return await c.get(path, headers={"host": host})
    return _run(go())


def test_mcp_page_explains_endpoint_and_lists_real_tools(ingested):
    t = html(ingested, "/ui/mcp")
    assert "MCP" in t and "Bearer" in t
    assert "http://test/mcp" in t and 'href="/ui/mcp.md"' in t
    assert "Read http://test/ui/mcp.md" in t and "閱讀 http://test/ui/mcp.md" in t      # 可直接貼給 agent 的提示（中英）
    for tool in ("get_project", "search_projects", "get_exceptions", "list_months"):     # 從 server 註冊的 tools 產生
        assert tool in t, tool
    assert "tok-up" not in t and "tok-view" not in t and "Alice" not in t and "Bob" not in t


def test_mcp_markdown_is_the_setup_guide_with_host_filled_in(ingested):
    r = get(ingested, "/ui/mcp.md")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    md = r.text
    assert "http://test/mcp" in md and "<HOST>" not in md                     # 端點依使用者開網頁的位址填好
    assert "<TOKEN>" in md and "tok-up" not in md and "tok-view" not in md     # token 永遠由使用者提供
    assert "## Tools on this server" in md and "`get_project`" in md
    assert last_audit(ingested)["action"] == "/ui/mcp.md" and last_audit(ingested)["status"] == "ok"


def test_mcp_markdown_ignores_a_strange_host_header(ingested):
    r = get_with_host(ingested, "/ui/mcp.md", "evil.example/x<script>")
    assert r.status_code == 200 and "<HOST>" in r.text and "evil" not in r.text and "<script>" not in r.text


def test_mcp_markdown_is_pii_checked(ingested, monkeypatch):
    monkeypatch.setattr("src.eis_mcp.web.routes.find_pii", lambda text, *a, **kw: ["LA0000001"])
    r = get(ingested, "/ui/mcp.md")
    assert r.status_code == 503 and "LA0000001" not in r.text


def test_mcp_guide_missing_is_loud(ingested, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr("src.eis_mcp.web.pages_mcp.GUIDE", Path("/nonexistent/eis-mcp-client-setup.md"))
    assert get(ingested, "/ui/mcp.md").status_code == 503
    t = html(ingested, "/ui/mcp")                                            # 說明頁仍可用，只是少了完整文件
    assert "http://test/mcp" in t and "not installed on this server" in t


def test_home_links_to_mcp_page(ingested):
    t = html(ingested, "/ui/")
    assert 'href="/ui/mcp"' in t and "MCP setup" in t


def test_install_script_ships_the_setup_guide():
    from pathlib import Path
    s = Path("deploy/install.sh").read_text(encoding="utf-8")
    assert "docs/eis-mcp-client-setup.md" in s


def test_mcp_markdown_table_and_host_note_are_agent_friendly(ingested):
    md = get(ingested, "/ui/mcp.md").text
    tools = md[md.index("## Tools on this server"):]
    for line in tools.splitlines():
        if line.startswith("| `"):
            assert line.replace("\\|", "").count("|") == 3, line              # 說明裡的 | 要跳脫，表格才不會多出欄位
    head = md[:md.index("## 0.")]
    assert "server 位址已填好：`test`" in head and "只需要向使用者要 `<TOKEN>`" in head and "需要使用者提供兩個值" not in head and "這兩個值" not in head


def test_upcoming_milestones_tool_description_matches_inactive_rule(ingested):
    """tool 說明會顯示在 /ui/mcp，必須與實際規則一致：排除 Terminated 與 Suspended（INACTIVE）。"""
    t = html(ingested, "/ui/mcp")
    assert "(in briefing, not terminated or suspended)" in t and "not suspended)" not in t


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
    assert '>Decisions<span class="badge" title="3 decisions this month">3</span></a>' in nav


def test_decisions_page_and_badge_count(ingested):
    snap = ingested.state.eis.store.load_snapshot("202609")
    t = html(ingested, f"/ui/202609/decisions?today={TODAY}")
    assert "Decisions this month" in t and '<ol class="ex">' in t
    n = len(snap["exceptions"])
    assert f'>Decisions<span class="badge" title="{n} decision{"" if n == 1 else "s"} this month">{n}</span>' in t
    ex = t[t.index('<ol class="ex">'):t.index("</ol>")]
    assert f'href="/ui/202609/projects/{CODE}"' in ex


def test_health_page_merges_corrections_and_old_url_redirects(ingested):
    t = html(ingested, "/ui/202609/health")
    assert "<h1>Data health" in t and "<h2>Data health" not in t and "already listed on the Decisions page" in t and "No corrections" in t
    r = get(ingested, "/ui/202609/corrections")
    assert r.status_code == 301 and r.headers["location"] == "/ui/202609/health"


def test_decisions_page_lists_every_at_risk_project(ingested):
    from src.portfolio.render.viz.options import at_risk_codes
    snap = ingested.state.eis.store.load_snapshot("202609")
    codes = at_risk_codes(snap, ingested.state.eis.cfg.thresholds["mp_slip_days"])
    t = html(ingested, f"/ui/202609/decisions?today={TODAY}")
    head = t[t.index(f"At risk ({len(codes)})"):t.index('<ol class="ex">')]
    assert codes and all(f'href="/ui/202609/projects/{c}"' in head for c in codes)



# ---- 專業化 pass 1（2026-10-03）：外框、字級、單一標題 ----
def test_sidebar_month_picker_jumps_on_change_and_search_is_one_field():
    t = render_shell(title="x", body="", months=["202609", "202608"], month="202609")
    nav = t[t.index("<nav"):t.index("</nav>")]
    assert '<select name="month" data-autosubmit' in nav and "<noscript><button>Go</button></noscript>" in nav
    assert 'class="search" placeholder="Find project"' in nav and '<button class="sr">Find</button>' in nav
    assert "data-autosubmit" in t[t.index("</nav>"):]                                   # 頁尾腳本處理自動送出（不用 inline onchange）


def test_each_page_has_one_heading_for_its_subject(ingested):
    t = html(ingested, f"/ui/202609/decisions?today={TODAY}")
    assert "<h1>Decisions this month" in t and "<h2>Decisions this month" not in t


# ---- 專業化 pass 3（2026-10-03）：表格與清單 ----
def test_project_rows_link_on_the_name_and_show_the_code_quietly(ingested):
    t = html(ingested, "/ui/202609/projects")
    assert f'<td><a class="row-link" href="/ui/202609/projects/{CODE}">THORPE</a><small>' in t
    row = t[t.index(f'href="/ui/202609/projects/{CODE}">THORPE'):]
    assert row.index(f'<span class="code" title="{CODE}">{CODE}</span>') < row.index("</td>")          # code 收在名稱下方，不另佔一欄
    assert f'<a href="/ui/202609/projects/{CODE}">{CODE}</a>' not in t


def test_decision_project_links_are_chips(ingested):
    t = html(ingested, f"/ui/202609/decisions?today={TODAY}")
    opens = t[t.index('<div class="open">'):]
    assert f'<a class="chip plain" href="/ui/202609/projects/{CODE}">THORPE</a>' in opens
    head = t[t.index("At risk ("):t.index('<ol class="ex">')]
    assert f'<a class="plain" href="/ui/202609/projects/{CODE}">THORPE</a>' in head


def test_long_health_lists_collapse_after_six(ingested):
    from src.eis_mcp.web.pages_health import _linked_health
    snap = ingested.state.eis.store.load_snapshot("202609")
    row = {"level": "track", "check": "briefing_stale", "label": "briefing_stale", "count": 10, "names": [f"P{i} last updated 2026-01-0{i % 9 + 1}" for i in range(10)], "source": "briefing"}
    out = _linked_health(snap, [row])
    assert out.count("P0 last updated") == 1 and '<details class="more"><summary>+4 more</summary>' in out
    shown, hidden = out.split('<details class="more">')
    assert "P5 last updated" in shown and "P6 last updated" in hidden


def test_overview_web_follows_the_same_order(ingested):
    t = html(ingested, f"/ui/202609/?today={TODAY}")
    order = [t.index(x) for x in ('<div class="kpis">', 'id="c-stage"', 'id="c-gantt"', "<h3>Milestones, next 8 weeks", 'id="c-forecast"', 'id="c-fu"')]
    assert order == sorted(order) and 'class="status"' not in t and 'id="c-heat-function"' not in t
    assert 'href="/ui/202609/decisions"><span class="k-label">At risk</span>' in t


def test_whole_row_click_does_not_rely_on_a_positioned_table_row():
    """2026-10-03 使用者回報 Safari：點任一列都進最後一案、側欄搜尋框點不到。
    根因：a.row-link::after{inset:0} 以 tr{position:relative} 為範圍，部分 Safari 不把 tr 當定位容器，
    覆蓋層撐成整頁、最後一列蓋在最上面。改為不用覆蓋層，整列點擊由頁尾腳本轉到該列的 row-link。"""
    from src.portfolio.render.css import CSS
    assert "row-link::after" not in CSS and "tbody tr{position:relative}" not in CSS
    t = render_shell(title="x", body="", months=["202609"], month="202609")
    tail = t[t.index("</nav>"):]
    assert 'closest("tr")' in tail and 'querySelector("a.row-link")' in tail



# ---- 2026-10-03 review：專案列表與單案頁 ----
def test_project_list_groups_by_status_and_folds_the_inactive(ingested):
    store = ingested.state.eis.store
    f = store.snapshot_dir("202609") / "portfolio.json"
    snap = json.loads(f.read_text(encoding="utf-8"))
    base = snap["projects"][0]
    extra = [dict(base, code="BR0000000001", name="aDone", stage="Terminate", stage_cat="Terminated", fte=[0.0] * 12),
             dict(base, code="BR0000000002", name="Zmp", stage="MP", stage_cat="MP"),
             dict(base, code="POOL", name="BU10_RFQ_POOL", stage="", stage_cat="", in_briefing=False, customer="", biz_type="", category="", pva={})]
    snap["projects"] += extra
    f.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8"); store.invalidate()
    t = html(ingested, f"/ui/202609/projects?today={TODAY}")
    heads = [h for h in ("Active", "In production", "Closed or on hold", "Not in Briefing") if f">{h} (" in t]
    assert heads == ["Active", "In production", "Closed or on hold", "Not in Briefing"]
    assert t.index("THORPE") < t.index("Zmp") < t.index("aDone") < t.index("BU10_RFQ_POOL")
    assert "<h3>Active (" in t and "<h3>In production (" in t                               # 進行中與量產直接展開
    assert '<details class="group"><summary data-expand="expand" data-collapse="collapse"><span>Closed or on hold (' in t                 # 結案／暫停與不在 Briefing 收合
    assert '<details class="group"><summary data-expand="expand" data-collapse="collapse"><span>Not in Briefing (' in t
    pool = t[t.index("BU10_RFQ_POOL"):]
    assert "Not in Briefing" in pool[:pool.index("</tr>")]                                 # 空白格寫明原因，不留白
    assert "<th>Stage cat.</th>" not in t and 'type="text" name="q"' not in t[t.index('<form method="get" class="filters"'):]


def test_project_list_shows_risk_next_milestone_trend_and_plan(ingested):
    t = html(ingested, f"/ui/202609/projects?today={TODAY}")
    row = t[t.index('href="/ui/202609/projects/BR0000015346">THORPE'):]
    row = row[:row.index("</tr>")]
    assert 'class="chip"' in row and "At risk" in row                                    # THORPE MP 已過
    assert "MP 2026-07-31" in row and "overdue" in row
    assert '<svg class="spark"' in row
    assert "%" in row


def test_project_list_keeps_the_search_text_when_filtering(ingested):
    add_twin(ingested)
    t = html(ingested, "/ui/202609/projects?q=THORP")
    form = t[t.index('<form method="get" class="filters"'):]
    assert '<input type="hidden" name="q" value="THORP">' in form
    assert "Matches for" in t and "THORP" in t


def test_project_page_leads_with_status_and_why_it_is_at_risk(ingested):
    t = html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
    top = t[t.index('<div class="kpis four">'):]
    first = top[:top.index("</div>", top.index("k-sub"))]
    assert "At risk" in first and "MP 2026-07-31 passed" in t[t.index('<div class="kpis four">'):t.index('<div class="kpis four">') + 2000]
    from src.eis_mcp.web.pages_project import project_body
    snap = ingested.state.eis.store.load_snapshot("202609")
    b = project_body("202609", snap["projects"][0], TODAY, 8, "202608")
    assert "Compare with 2026-08" in b[:b.index('<div class="kpis four">')]                  # 比較連結在頁首
    assert "<span>In briefing</span>" not in t and "<span>Has plan</span>" not in t       # key-value 清單拿掉，只在缺資料時警示


def test_project_page_sections_in_reading_order(ingested):
    t = html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
    order = [t.index(x) for x in ('id="c-mp-drift"', "<h2>Plan vs actual", "<h2>Tasks", "<h2>FTE and NTD by month")]
    assert order == sorted(order)


def test_project_page_tasks_are_summarised_by_function(ingested):
    t = html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
    tasks = t[t.index("<h2>Tasks"):t.index("<h2>FTE and NTD by month")]
    assert '<table class="tg">' in tasks and "Show all" in tasks


def test_project_list_sections_share_column_widths_and_avoid_repeats():
    from src.eis_mcp.web.pages_projects import _next_cell, _row
    t_ = html  # noqa: F841
    p = {"code": "B1", "name": "X", "in_briefing": True, "stage": "MP", "stage_cat": "MP", "customer": "C", "group": "G", "biz_type": "", "category": "",
         "fte": [1.0] * 12, "pva": {}, "dates": {"evt": None, "dvt": None, "pvt": None, "mp": "2026-09-29"}}
    row = _row("202609", p, 8, "2026-09-29", {}, {})
    assert "<small>MP</small>" not in row                                                # 階段與分類同名不重複
    assert "on Briefing day" in _next_cell(p, "2026-09-29", {}) and "in 0 days" not in _next_cell(p, "2026-09-29", {})


def test_project_list_tables_use_one_column_layout(ingested):
    t = html(ingested, f"/ui/202609/projects?today={TODAY}")
    assert '<table class="plist"><colgroup>' in t and "<th>Risk</th>" not in t and "<th>Code</th>" not in t



def _plist_names(t: str) -> list[str]:
    import re
    return re.findall(r'class="row-link" href="[^"]+">([^<]+)</a>', t)


def _three(app):
    store = app.state.eis.store
    f = store.snapshot_dir("202609") / "portfolio.json"
    snap = json.loads(f.read_text(encoding="utf-8"))
    b = snap["projects"][0]
    lo = dict(b, code="BR0000000011", name="alpha", customer="Zed", fte=[1.0] * 12, dates={**b["dates"], "mp": "2026-12-01"})
    hi = dict(b, code="BR0000000012", name="Beta", customer="Acme", fte=[30.0] * 12, dates={**b["dates"], "mp": "2026-10-01"})
    snap["projects"] += [lo, hi]
    f.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8"); store.invalidate()


def test_project_list_sorts_by_the_clicked_header(ingested):
    _three(ingested)
    t = html(ingested, f"/ui/202609/projects?today={TODAY}")
    assert _plist_names(t) == ["Beta", "THORPE", "alpha"]                                 # 預設：本月 FTE 由大到小
    assert _plist_names(html(ingested, f"/ui/202609/projects?today={TODAY}&sort=name")) == ["alpha", "Beta", "THORPE"]   # 不分大小寫
    assert _plist_names(html(ingested, f"/ui/202609/projects?today={TODAY}&sort=name&dir=desc")) == ["THORPE", "Beta", "alpha"]
    assert _plist_names(html(ingested, f"/ui/202609/projects?today={TODAY}&sort=customer")) == ["Beta", "THORPE", "alpha"]
    assert _plist_names(html(ingested, f"/ui/202609/projects?today={TODAY}&sort=next")) == ["THORPE", "Beta", "alpha"]   # 逾期最前，再依日期


def test_sort_headers_toggle_and_keep_filters(ingested):
    t = html(ingested, f"/ui/202609/projects?today={TODAY}&customer=Dior&sort=name")
    head = t[t.index('<table class="plist">'):t.index("</thead>")]
    assert 'aria-sort="ascending"' in head
    assert 'href="/ui/202609/projects?customer=Dior&amp;sort=name&amp;dir=desc"' in head     # 再點同一欄＝反向，篩選保留
    assert 'href="/ui/202609/projects?customer=Dior&amp;sort=fte"' in head


def test_project_list_columns_are_grouped(ingested):
    t = html(ingested, f"/ui/202609/projects?today={TODAY}")
    head = t[t.index('<table class="plist">'):t.index("</thead>")]
    assert '<tr class="grp"><th colspan="3">Project</th><th colspan="2" class="g">Schedule</th><th colspan="4" class="g">Manpower</th></tr>' in head


def test_bad_sort_value_falls_back_to_default(ingested):
    t = html(ingested, f"/ui/202609/projects?today={TODAY}&sort=%3Cx%3E&dir=up")
    assert "<x>" not in t and "THORPE" in t


def test_plan_column_names_the_unit_and_the_months(ingested):
    """2026-10-03 需求方：「Plan to date」沒說比的是 FTE、也沒說期間。"""
    t = html(ingested, f"/ui/202609/projects?today={TODAY}")
    head = t[t.index('<table class="plist">'):t.index("</thead>")]
    assert "% of planned FTE,<br>Jan to Aug" in head and "Plan to date" not in t
    assert 'title="Actual FTE as a share of planned FTE, summed over Jan to Aug, all roles"' in head
    row = t[t.index('href="/ui/202609/projects/BR0000015346">THORPE'):]
    assert 'title="Jan to Aug: planned FTE ' in row[:row.index("</tr>")]



def test_missing_source_note_does_not_restyle_the_due_soon_pill():
    """2026-10-03：單案頁警示框用了 .warn，與 .pill.warn（Due soon）撞名，標籤被套上 padding、外框與上邊距。"""
    import re
    from src.portfolio.render.css import CSS
    assert not re.search(r"(^|[}\s])\.warn\{", CSS)                                   # 不可有裸的 .warn 規則
    assert ".miss-note{" in CSS


def test_decisions_badge_is_a_count_not_an_unread_marker():
    from src.portfolio.render.css import CSS
    rule = CSS[CSS.index(".side .badge{"):]
    rule = rule[:rule.index("}")]
    assert "var(--signal)" not in rule                                                   # 不用橘色未讀樣式


def test_manpower_group_shows_the_total_and_the_plan_it_is_divided_by(ingested):
    """2026-10-03 需求方：加 Jan to Aug 總數，% 放在它後面；% 欄第二行給 plan 總數，讓算式攤開。"""
    t = html(ingested, f"/ui/202609/projects?today={TODAY}")
    head = t[t.index('<table class="plist">'):t.index("</thead>")]
    order = [head.index(x) for x in ("Trend, Jan to Aug", "FTE Aug", "FTE, Jan to Aug", "% of planned FTE,<br>Jan to Aug")]
    assert order == sorted(order) and '<th colspan="4" class="g">Manpower</th>' in head
    assert 'href="/ui/202609/projects?sort=total"' in head
    row = t[t.index('href="/ui/202609/projects/BR0000015346">THORPE'):]
    row = row[:row.index("</tr>")]
    assert '<td class="num">96.0</td>' in row                                            # fixture：12.0 × 8 個月
    assert "<small>plan " in row


def test_fte_card_states_its_source_instead_of_a_jan_comparison(ingested):
    """2026-10-03 需求方：「from 36.1 in Jan」只比兩個月，看似一路上升（Delta3-7 實際 5 月高峰後連降）；
    逐月走勢由下方 Plan vs actual 圖呈現，卡片只交代數字是什麼。"""
    t = html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
    card = t[t.index('<span class="k-label">FTE, Aug</span>'):]
    card = card[:card.index("</div>")]
    assert "in Jan" not in card and '<span class="k-sub">Resource Summary, all roles</span>' in card
