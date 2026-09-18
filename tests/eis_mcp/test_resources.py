import json
import pytest
from tests.eis_mcp.conftest import call_tool, read_resource


def test_months_resource(ingested):
    text, mime = read_resource(ingested, "tok-view", "eis://months")
    assert mime == "application/json"
    assert json.loads(text)["months"][0]["month"] == "202609"


def test_report_resource_and_audit(ingested):
    text, mime = read_resource(ingested, "tok-view", "eis://202609/report.html")
    assert mime == "text/html" and "Decisions this month" in text and "THORPE" in text
    row = ingested.state.eis.audit.rows()[-1]
    assert row["kind"] == "resource" and row["action"] == "eis://202609/report.html" and row["status"] == "ok" and row["name"] == "Bob"


def test_report_resource_unknown_month(ingested):
    with pytest.raises(Exception) as ex:
        read_resource(ingested, "tok-view", "eis://202501/report.html")
    assert "202501" in str(ex.value)
    assert ingested.state.eis.audit.rows()[-1]["status"] == "error"


def test_report_resource_rejects_path_traversal_month(ingested):
    with pytest.raises(Exception):
        read_resource(ingested, "tok-view", "eis://../x/report.html")


def test_tool_output_pii_guard(ingested, monkeypatch):
    """出口保險：快照被塞入工號時，tool 要擋下並記 rejected_pii。"""
    store = ingested.state.eis.store
    snap = store.load_snapshot("202609")
    poisoned = json.loads(json.dumps(snap)); poisoned["projects"][0]["name"] = "THORPE LA0000001"
    monkeypatch.setattr(store, "load_snapshot", lambda month: poisoned)
    err, text = call_tool(ingested, "tok-view", "get_project", {"query": "BR0000015346"})
    assert err and "rejected_pii" in text and "LA0000001" not in text
    assert ingested.state.eis.audit.rows()[-1]["status"] == "rejected_pii"
