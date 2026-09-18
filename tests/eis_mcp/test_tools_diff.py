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
    # Re-ingesting 202610 needs raw input under input_dir("202610"); reuse the same uploaded
    # files as 202609 (same pattern as tests/portfolio/test_cli.py::test_end_to_end).
    for p in store.input_dir("202609").iterdir():
        if p.name != "_upload.json":
            store.register_upload("202610", p.name, p.read_bytes(), "Alice")
    assert run_ingest(ingested.state.eis, "202610", "2026-10-12", "Alice")["status"] == "ok"
    err, out = call_tool(ingested, "tok-view", "get_corrections", {"month": "202610"})
    assert not err and out["count"] == 1
    c = out["corrections"][0]
    assert c["check"] == "cross_month_correction" and c["code"] == CODE and "Jul" in c["detail"] and "17.0" in c["detail"]
    err, out = call_tool(ingested, "tok-view", "get_corrections", {"month": "202609"})
    assert not err and out["count"] == 0
