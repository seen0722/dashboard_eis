"""queries.py 是 MCP tools 與 web 共用的純函式；這裡只用手工 snapshot dict，不跑 ingest。"""
import pytest
from src.eis_mcp import queries as q
from src.portfolio.config import Config

P1 = {"code": "BR0000015346", "name": "THORPE", "group": "Trenton", "family": "", "customer": "ACME", "product": "BU10_IPC",
      "stage": "PVT", "stage_cat": "Execution", "dates": {"kickoff": None, "evt": None, "dvt": None, "pvt": "2026-03-21", "mp": "2026-07-31", "mp_orig": "2025-10-13"},
      "in_briefing": True, "in_control_list": True, "has_plan": True, "fte": [12.0] * 8 + [0.0] * 4, "ntd": [1e6] * 8 + [0.0] * 4,
      "pva": {}, "tasks": [], "history": []}
P2 = {**P1, "code": "BR0000099999", "name": "THORPE2", "customer": "Beta", "stage": "POC", "stage_cat": "POC", "fte": [1.0] * 12}
P3 = {**P1, "code": "BR0000077777", "name": "Sleepy", "stage": "Suspended", "stage_cat": "Suspended", "dates": {**P1["dates"], "mp": "2026-09-20"}}
SNAP = {"meta": {"report_month": "202609", "latest_month": 8, "snap_date": "20260907"}, "projects": [P1, P2, P3],
        "loads": [{"dept_code": "D1", "dept_name": "one", "function": "BIOS", "keyed_in": [3] * 12, "allocated": [3.0] * 12, "util": [100] * 12},
                  {"dept_code": "D2", "dept_name": "two", "function": "SW", "keyed_in": [2] * 12, "allocated": [1.0] * 12, "util": [50] * 12},
                  {"dept_code": "D0", "dept_name": "none", "function": "PM", "keyed_in": [0] * 12, "allocated": [0.0] * 12, "util": [None] * 12}],
        "capacity": [5] * 8 + [0] * 4, "exceptions": [{"rank": 1, "title": "milestones_passed", "count": 1}], "health": [{"level": "ok", "check": "x", "count": 0}],
        "issues": [{"level": "track", "check": "cross_month_correction", "detail": "THORPE Jul FTE 17.0 -> 12.0", "source": "snapshot", "code": "BR0000015346"},
                   {"level": "track", "check": "name_unresolved", "detail": "x", "source": "Briefing", "code": None}]}
CFG = Config(aliases={"thor": "thorpe"})


def test_project_exact_alias_and_candidates():
    assert q.project(SNAP, "br0000015346", CFG)["project"]["code"] == "BR0000015346"
    assert q.project(SNAP, "THOR", CFG)["project"]["name"] == "THORPE"          # alias thor -> thorpe 全名精確
    out = q.project(SNAP, "thorpe", Config())
    assert out["project"]["code"] == "BR0000015346"                              # 全名精確命中不受 THORPE2 影響
    out = q.project(SNAP, "THORP", Config())
    assert "project" not in out and sorted(c["code"] for c in out["candidates"]) == ["BR0000015346", "BR0000099999"] and "hint" in out
    with pytest.raises(q.NotFound, match="no project in 202609 matches 'nope'"):
        q.project(SNAP, "nope", CFG)


def test_search_filters_and_latest_fte():
    assert q.search(SNAP)["count"] == 3
    out = q.search(SNAP, stage_cat="poc")
    assert out["count"] == 1 and out["projects"][0]["code"] == "BR0000099999" and out["projects"][0]["latest_fte"] == 1.0
    assert q.search(SNAP, customer="acme")["count"] == 2
    assert [p["code"] for p in q.search(SNAP, text="sleep")["projects"]] == ["BR0000077777"]
    assert set(q.search(SNAP)["projects"][0]) == {"code", "name", "stage", "stage_cat", "customer", "group", "latest_fte"}


def test_exceptions_health_corrections_are_snapshot_rows():
    assert q.exceptions(SNAP) == {"count": 1, "exceptions": SNAP["exceptions"]}
    assert q.health(SNAP) == {"health": SNAP["health"]}
    out = q.corrections(SNAP)
    assert out["count"] == 1 and out["corrections"][0]["check"] == "cross_month_correction"


def test_upcoming_window_and_suspended_excluded():
    rows = q.upcoming_milestones(SNAP, "2026-09-12", 8)
    assert [(r["code"], r["milestone"], r["days_left"]) for r in rows] == [("BR0000015346", "mp", -43), ("BR0000099999", "mp", -43)]
    assert q.upcoming(SNAP, "2026-09-12", 2) == {"today": "2026-09-12", "weeks": 2, "milestones": []}


def test_dept_loads_sort_filter_and_capacity():
    out = q.dept_loads(SNAP)
    assert out["latest_month"] == 8 and [r["dept_code"] for r in out["loads"]] == ["D1", "D2", "D0"]
    assert out["loads"][0]["latest_util"] == 100 and out["loads"][2]["latest_util"] is None
    assert [r["dept_code"] for r in q.dept_loads(SNAP, min_util=60)["loads"]] == ["D1"]
    assert [r["dept_code"] for r in q.dept_loads(SNAP, min_util=0)["loads"]] == ["D1", "D2"]   # null 一律排除
    assert q.capacity(SNAP) == {"months": list(q.MONTHS), "capacity": SNAP["capacity"]}


def test_diff_and_not_found():
    b = {"meta": {**SNAP["meta"], "report_month": "202610"}, "projects": [{**P1, "stage": "MP", "fte": [12.0] * 8 + [5.0] + [0.0] * 3}]}
    out = q.diff(SNAP, b, "br0000015346")
    assert out["code"] == "BR0000015346" and out["month_a"] == "202609" and out["month_b"] == "202610"
    assert set(out["changed"]) == {"stage", "fte"} and out["changed"]["stage"] == {"a": "PVT", "b": "MP"}
    assert q.diff(SNAP, SNAP, "BR0000015346")["changed"] == {}
    with pytest.raises(q.NotFound, match="BR0000099999 is not in the snapshot for 202610"):
        q.diff(SNAP, b, "BR0000099999")


def test_distinct():
    assert q.distinct(SNAP, "customer") == ["ACME", "Beta"]
    assert q.distinct(SNAP, "family") == []
