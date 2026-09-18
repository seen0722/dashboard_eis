import fcntl
import pytest
from src.eis_mcp.ingest import IngestBusy, run_ingest
from tests.eis_mcp.conftest import TODAY, call_tool


def test_viewer_cannot_ingest(uploaded):
    err, text = call_tool(uploaded, "tok-view", "ingest_month", {"report_month": "202609", "today": TODAY})
    assert err and "forbidden" in text and "uploader" in text
    assert uploaded.state.eis.audit.rows()[-1]["status"] == "forbidden"


def test_ingest_without_files_names_missing_categories(app):
    err, text = call_tool(app, "tok-up", "ingest_month", {"report_month": "202609", "today": TODAY})
    assert err and "missing_input" in text and "master" in text and "eis-upload.sh 202609" in text


def test_ingest_bad_month(app):
    err, text = call_tool(app, "tok-up", "ingest_month", {"report_month": "2026-09"})
    assert err and "bad_month" in text


def test_ingest_ok_writes_snapshot_and_log(uploaded):
    err, out = call_tool(uploaded, "tok-up", "ingest_month", {"report_month": "202609", "today": TODAY})
    assert not err, out
    assert out["status"] == "ok" and out["summary"]["latest_month"] == 8 and out["summary"]["control_lists"] == 1
    assert isinstance(out["health"], list) and {"level", "check", "count"} <= set(out["health"][0])
    assert out["warnings"] == []
    store = uploaded.state.eis.store
    assert (store.snapshot_dir("202609") / "portfolio.json").exists() and (store.snapshot_dir("202609") / "report_en.html").exists()
    log = store.ingests("202609")
    assert len(log) == 1 and log[0]["status"] == "ok" and log[0]["by"] == "Alice"
    row = uploaded.state.eis.audit.rows()[-1]
    assert row["action"] == "ingest_month" and row["status"] == "ok" and row["name"] == "Alice"


def test_ingest_warns_when_no_control_list(app, input_pack):
    from tests.eis_mcp.conftest import post_upload
    files = {p.name: p.read_bytes() for p in input_pack.iterdir() if "Control List" not in p.name}
    assert post_upload(app, "tok-up", "202609", files).status_code == 200
    err, out = call_tool(app, "tok-up", "ingest_month", {"report_month": "202609", "today": TODAY})
    assert not err and out["status"] == "ok" and any("Control List" in w for w in out["warnings"])


def test_ingest_rejected_pii_writes_nothing(uploaded, monkeypatch):
    monkeypatch.setattr("src.eis_mcp.ingest.find_pii", lambda text, *a, **kw: ["LA0000001"])
    err, out = call_tool(uploaded, "tok-up", "ingest_month", {"report_month": "202609", "today": TODAY})
    assert not err and out["status"] == "rejected_pii" and out["hits"] == ["LA0000001", "LA0000001"] and "next" in out
    store = uploaded.state.eis.store
    assert not (store.snapshot_dir("202609") / "portfolio.json").exists()
    assert store.ingests("202609")[-1]["status"] == "rejected_pii"
    assert (store.input_dir("202609") / "Project List-202609.xlsx").exists()   # 原檔保留
    assert uploaded.state.eis.audit.rows()[-1]["status"] == "ok"                # tool 本身正常結束


def test_ingest_busy_when_lock_held(uploaded):
    state = uploaded.state.eis
    lock = state.store.locks_root / "202609.lock"
    fh = open(lock, "w"); fcntl.flock(fh, fcntl.LOCK_EX)
    try:
        with pytest.raises(IngestBusy):
            run_ingest(state, "202609", TODAY, "Alice")
        err, text = call_tool(uploaded, "tok-up", "ingest_month", {"report_month": "202609", "today": TODAY})
        assert err and "busy" in text
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN); fh.close()


def test_list_months_shows_uploads_and_ingest(ingested):
    err, out = call_tool(ingested, "tok-view", "list_months")
    assert not err
    m = out["months"][0]
    assert m["month"] == "202609" and m["status"] == "ok" and len(m["uploads"]) == 4
    assert m["last_ingest"]["by"] == "Alice" and m["last_ingest"]["status"] == "ok"


def test_rerun_appends_ingest_log(ingested):
    err, out = call_tool(ingested, "tok-up", "ingest_month", {"report_month": "202609", "today": TODAY})
    assert not err and len(ingested.state.eis.store.ingests("202609")) == 2
