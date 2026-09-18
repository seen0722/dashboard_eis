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
