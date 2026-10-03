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
        {"code": "T", "name": "T", "stage_cat": "Terminated", "in_briefing": True, "dates": {"evt": None, "dvt": None, "pvt": None, "mp": "2026-09-20"}},
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


def test_upcoming_milestones_default_to_the_briefing_snapshot_date(ingested):
    """2026-10-03：網頁、月報、MCP 同一個基準日（Briefing 快照日），不用 server 當天。"""
    err, out = call_tool(ingested, "tok-view", "get_upcoming_milestones", {})
    snap = ingested.state.eis.store.load_snapshot("202609")
    sd = snap["meta"]["snap_date"]
    assert not err and out["today"] == f"{sd[:4]}-{sd[4:6]}-{sd[6:]}"
