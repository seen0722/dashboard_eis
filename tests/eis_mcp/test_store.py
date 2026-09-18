import json
import stat
import pytest
from src.eis_mcp.store import Store, classify_filename, UnknownMonth, SnapshotBroken


def test_classify_filename_accepts_the_four_kinds_and_rejects_the_rest():
    assert classify_filename("Project List-202609.xlsx") == "master"
    assert classify_filename("BU10_Project_Briefing_20260907.xlsx") == "briefing"
    assert classify_filename("2026 EIS Resource Summary.xlsx") == "summary"
    assert classify_filename("2026  EIS Resource Control List-THORPE (Some One).xlsx") == "control_list"
    assert classify_filename("2026 EIS Resource Control List-RFQ_OTHERS(PM).xlsb") == "control_list"
    for bad in ("~$Project List-202609.xlsx", "../Project List-202609.xlsx", "x/Project List-202609.xlsx",
                "evil.exe", "Project List-202609.xlsx.bak", ".hidden.xlsx", ""):
        assert classify_filename(bad) is None, bad


def test_init_layout_and_permissions(store):
    assert store.input_root.is_dir() and store.snapshots_root.is_dir() and store.locks_root.is_dir()
    assert stat.S_IMODE(store.input_root.stat().st_mode) == 0o700
    assert store.check_permissions() == []
    store.input_root.chmod(0o755)
    store.tokens_file.write_text("tokens: []"); store.tokens_file.chmod(0o644)
    problems = store.check_permissions()
    assert any(p == f"chmod 700 {store.input_root}" for p in problems)
    assert any(p == f"chmod 600 {store.tokens_file}" for p in problems)


def test_check_permissions_detects_per_month_dir_issues(store):
    store.register_upload("202609", "Project List-202609.xlsx", b"x", "Alice")
    assert store.check_permissions() == []
    store.input_dir("202609").chmod(0o755)
    problems = store.check_permissions()
    assert any(p == f"chmod 700 {store.input_dir('202609')}" for p in problems)


def test_register_upload_appends_registry_and_overwrites_file(store):
    r1 = store.register_upload("202609", "Project List-202609.xlsx", b"one", "Alice")
    r2 = store.register_upload("202609", "Project List-202609.xlsx", b"three", "Bob")
    assert (store.input_dir("202609") / "Project List-202609.xlsx").read_bytes() == b"three"
    assert r1["size"] == 3 and r2["size"] == 5 and r1["sha256"] != r2["sha256"]
    regs = store.uploads("202609")
    assert [r["uploaded_by"] for r in regs] == ["Alice", "Bob"] and all("uploaded_at" in r for r in regs)
    assert store.uploads("202610") == []
    # Verify per-month dir is 0700 and file is 0600
    assert stat.S_IMODE(store.input_dir("202609").stat().st_mode) == 0o700
    assert stat.S_IMODE((store.input_dir("202609") / "Project List-202609.xlsx").stat().st_mode) == 0o600


def test_ingest_log_roundtrip(store):
    store.record_ingest("202609", {"at": "t1", "by": "Alice", "status": "rejected_pii"})
    store.record_ingest("202609", {"at": "t2", "by": "Alice", "status": "ok"})
    assert [r["status"] for r in store.ingests("202609")] == ["rejected_pii", "ok"]


def _snap(month):
    return {"meta": {"version": "1", "report_month": month, "latest_month": 8, "snap_date": "20260907", "generated": "2026-09-12"},
            "projects": [], "loads": [], "capacity": [0] * 12, "exceptions": [], "health": [], "issues": []}


def test_write_result_then_load_and_months(store):
    store.write_result("202609", _snap("202609"), "<html>r</html>")
    assert store.load_snapshot("202609")["meta"]["report_month"] == "202609"
    assert store.report_html("202609") == "<html>r</html>"
    store.register_upload("202610", "Project List-202610.xlsx", b"x", "Alice")
    (store.snapshot_dir("202608")).mkdir(parents=True); (store.snapshot_dir("202608") / "portfolio.json").write_text("{not json")
    months = store.months()
    assert [m["month"] for m in months] == ["202610", "202609", "202608"]
    assert {m["month"]: m["status"] for m in months} == {"202610": "uploaded_only", "202609": "ok", "202608": "broken"}
    assert months[0]["uploads"][0]["uploaded_by"] == "Alice" and months[1]["last_ingest"] is None
    assert store.latest_month() == "202609"


def test_month_path_traversal_rejected(store):
    for bad in ("../x", "../../etc/passwd", "202609/../../x", "abc"):
        with pytest.raises(UnknownMonth):
            store.load_snapshot(bad)
        with pytest.raises(UnknownMonth):
            store.report_html(bad)
        with pytest.raises(UnknownMonth):
            store.uploads(bad)


def test_load_snapshot_errors_and_cache_invalidation(store):
    try:
        store.load_snapshot("202601"); assert False
    except UnknownMonth as ex:
        assert str(ex) == "202601"
    store.write_result("202609", _snap("202609"), "")
    first = store.load_snapshot("202609")
    assert store.load_snapshot("202609") is first            # 快取命中
    (store.snapshot_dir("202609") / "portfolio.json").write_text("{broken")
    store.invalidate("202609")
    try:
        store.load_snapshot("202609"); assert False
    except SnapshotBroken as ex:
        assert str(ex) == "202609"
    assert store.latest_month() is None
