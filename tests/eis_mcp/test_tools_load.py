import json
from tests.eis_mcp.conftest import call_tool


def test_get_dept_loads_sorted_and_filtered(ingested):
    err, out = call_tool(ingested, "tok-view", "get_dept_loads")
    assert not err and out["count"] >= 1 and out["latest_month"] == 8
    rows = out["loads"]
    assert {"dept_code", "dept_name", "function", "keyed_in", "allocated", "util", "latest_util"} <= set(rows[0])
    assert [r["latest_util"] for r in rows] == sorted((r["latest_util"] for r in rows), reverse=True)
    assert all(r["latest_util"] == r["util"][7] for r in rows)
    err, out = call_tool(ingested, "tok-view", "get_dept_loads", {"min_util": 1000})
    assert not err and out["count"] == 0 and out["loads"] == []
    err, out = call_tool(ingested, "tok-view", "get_dept_loads", {"min_util": 0.0})
    assert not err and out["count"] == len(rows)


def _add_null_util_dept(app):
    """快照裡多放一個 latest_util 為 None 的部門（該月無人填報）。"""
    store = app.state.eis.store
    f = store.snapshot_dir("202609") / "portfolio.json"
    snap = json.loads(f.read_text(encoding="utf-8"))
    twin = dict(snap["loads"][0])
    twin["dept_code"] = "ZZ_NONE"
    twin["util"] = list(twin["util"])
    twin["util"][7] = None
    snap["loads"].append(twin)
    f.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    store.invalidate()


def test_get_dept_loads_tolerates_null_util(ingested):
    _add_null_util_dept(ingested)
    err, out = call_tool(ingested, "tok-view", "get_dept_loads")
    assert not err
    rows = out["loads"]
    assert rows[-1]["dept_code"] == "ZZ_NONE" and rows[-1]["latest_util"] is None
    err, out = call_tool(ingested, "tok-view", "get_dept_loads", {"min_util": 0})
    assert not err
    assert "ZZ_NONE" not in {r["dept_code"] for r in out["loads"]}


def test_get_capacity(ingested):
    err, out = call_tool(ingested, "tok-view", "get_capacity")
    assert not err
    snap = ingested.state.eis.store.load_snapshot("202609")
    assert out["capacity"] == snap["capacity"] and len(out["capacity"]) == 12 and out["months"] == ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
