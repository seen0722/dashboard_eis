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
    assert "202609" in t and "latest" in t and 'href="/ui/202609/"' in t and "Alice" in t
    assert "Some One" not in t                                   # 上傳檔名（含 PM 姓名）不出現
    r = get(ingested, "/ui/latest/")
    assert r.status_code == 307 and r.headers["location"] == "/ui/202609/"


def test_report_html_is_served_verbatim(ingested):
    t = html(ingested, "/ui/202609/report.html")
    assert t == ingested.state.eis.store.report_html("202609")
    assert "Decisions this month" in t


# ---- 錯誤頁 ----
def test_unknown_and_bad_month_are_404_with_month_links(ingested):
    t = html(ingested, "/ui/202501/report.html", 404)
    assert "No snapshot for 202501" in t and 'href="/ui/202609/"' in t
    t = html(ingested, "/ui/2026-09/report.html", 404)
    assert "No snapshot for 2026-09" in t
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


def test_nav_month_is_not_over_escaped():
    t = render_shell(title="x", body="", months=["202609"], month="202609")
    assert 'href="/ui/202609/projects"' in t


# ---- 總覽 ----
def test_overview_shows_decisions_health_and_milestones(ingested):
    t = html(ingested, f"/ui/202609/?today={TODAY}")
    assert "Decisions this month" in t and "Data health" in t and '<ol class="ex">' in t and "report_month 202609" in t
    assert "Milestones within 8 weeks" in t and "THORPE" in t and "-43" in t          # MP 2026-07-31 距 2026-09-12 已過 43 天
    t2 = html(ingested, f"/ui/202609/?today={TODAY}&weeks=2")
    assert "Milestones within 2 weeks" in t2 and "-43" not in t2
    assert get(ingested, "/ui/202609/?weeks=0").status_code == 400
    assert get(ingested, "/ui/202609/?today=13/09/2026").status_code == 400


# ---- 專案 ----
def add_twin(app):
    """快照裡多放一個 THORPE2，讓「多筆候選」有東西可測。"""
    store = app.state.eis.store
    f = store.snapshot_dir("202609") / "portfolio.json"
    snap = json.loads(f.read_text(encoding="utf-8"))
    twin = dict(snap["projects"][0]); twin["code"] = "BR0000099999"; twin["name"] = "THORPE2"; twin["stage_cat"] = "POC"; twin["customer"] = "Beta"
    snap["projects"].append(twin)
    f.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8"); store.invalidate()


def test_projects_table_filters_and_single_hit_redirect(ingested):
    add_twin(ingested)
    t = html(ingested, "/ui/202609/projects")
    assert t.count(f'href="/ui/202609/projects/BR0000') == 2 and "THORPE2" in t and "2 projects" in t
    assert 'value="POC" selected' not in t and 'value="POC"' in t and 'value="Beta"' in t     # 下拉有 distinct 值
    t = html(ingested, "/ui/202609/projects?stage_cat=POC")
    assert "THORPE2" in t and 'projects/BR0000015346"' not in t and 'value="POC" selected' in t
    t = html(ingested, "/ui/202609/projects?customer=Beta&stage_cat=")
    assert "1 project" in t and "THORPE2" in t
    r = get(ingested, "/ui/202609/projects?q=THORPE2")
    assert r.status_code == 307 and r.headers["location"] == "/ui/202609/projects/BR0000099999"
    t = html(ingested, "/ui/202609/projects?q=zzz")
    assert "0 projects" in t


def test_project_page_candidates_and_not_found(ingested):
    t = html(ingested, f"/ui/202609/projects/{CODE}?today={TODAY}")
    assert "THORPE" in t and CODE in t and "<svg" in t and "PVT" in t and "Aug" in t and "12.0" in t
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


# ---- diff ----
def test_diff_page_changed_identical_and_errors(ingested):
    clone_month(ingested, "202610", stage="MP", fte=[12.0] * 8 + [5.0] + [0.0] * 3)
    t = html(ingested, f"/ui/202610/projects/{CODE}/diff?to=202609")
    assert "stage" in t and "MP" in t and "PVT" in t and "fte" in t and "5.0" in t and "202610" in t and "202609" in t
    t = html(ingested, f"/ui/202609/projects/{CODE}/diff?to=202609")
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
