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


def test_get_project_resolves_alias(ingested, monkeypatch):
    from src.portfolio.config import normalize_name
    cfg = ingested.state.eis.cfg
    monkeypatch.setitem(cfg.aliases, normalize_name("Thorpy-Old"), normalize_name("THORPE"))
    err, out = call_tool(ingested, "tok-view", "get_project", {"query": "thorpy old"})
    assert not err and out["project"]["code"] == CODE
    err, text = call_tool(ingested, "tok-view", "get_project", {"query": "thorpy"})
    assert err and "not_found" in text   # alias is a whole-value match, not a prefix
