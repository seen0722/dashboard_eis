import contextlib
import pytest
from tests.eis_mcp.conftest import post_raw, post_upload


def test_no_token_is_401_on_both_endpoints(app):
    assert post_raw(app, None, "/mcp", json={}).status_code == 401
    assert post_upload(app, None, "202609", {"Project List-202609.xlsx": b"x"}).status_code == 401


def test_viewer_cannot_upload(app):
    r = post_upload(app, "tok-view", "202609", {"Project List-202609.xlsx": b"x"})
    assert r.status_code == 403 and r.json()["error"] == "forbidden"
    assert app.state.eis.audit.rows()[-1]["status"] == "forbidden"


def test_bad_month_is_400(app):
    r = post_upload(app, "tok-up", "2026-09", {"Project List-202609.xlsx": b"x"})
    assert r.status_code == 400 and r.json()["error"] == "bad_month"


def test_bad_filename_rejects_whole_request(app):
    files = {"Project List-202609.xlsx": b"ok", "evil.exe": b"no", "~$Project List-202609.xlsx": b"lock"}
    r = post_upload(app, "tok-up", "202609", files)
    assert r.status_code == 400 and r.json()["error"] == "bad_filename"
    assert sorted(r.json()["rejected"]) == ["evil.exe", "~$Project List-202609.xlsx"]
    assert "allowed" in r.json()
    assert not (app.state.eis.store.input_dir("202609") / "Project List-202609.xlsx").exists()


def test_no_files_is_400(app):
    assert post_raw(app, "tok-up", "/upload/202609", data={"x": "y"}).status_code == 400


def test_uploader_stores_pack_and_registry(app, input_pack):
    files = {p.name: p.read_bytes() for p in input_pack.iterdir()}
    r = post_upload(app, "tok-up", "202609", files)
    assert r.status_code == 200
    body = r.json()
    assert body["month"] == "202609" and len(body["stored"]) == 4
    assert {s["category"] for s in body["stored"]} == {"master", "briefing", "summary", "control_list"}
    store = app.state.eis.store
    assert all((store.input_dir("202609") / n).read_bytes() == b for n, b in files.items())
    assert len(store.uploads("202609")) == 4
    post_upload(app, "tok-up", "202609", {"Project List-202609.xlsx": files["Project List-202609.xlsx"]})
    assert len(store.uploads("202609")) == 5
    row = store.audit_db and app.state.eis.audit.rows()[-1]
    assert row["kind"] == "upload" and row["action"] == "upload:202609" and row["status"] == "ok" and row["name"] == "Alice"


def test_lifespan_startup_error_surfaces_instead_of_hanging(app, monkeypatch):
    """如果 app 的 lifespan __aenter__ 直接丟例外，test helper 要立刻把例外浮出去，
    而不是永遠卡在等 ready 事件上（讓整個 pytest process 掛住、看不到任何 traceback）。"""

    @contextlib.asynccontextmanager
    async def boom(_app):
        raise RuntimeError("boom")
        yield  # pragma: no cover - never reached, keeps this an async generator

    monkeypatch.setattr(app.router, "lifespan_context", boom)
    with pytest.raises(RuntimeError, match="boom"):
        post_raw(app, "tok-up", "/upload/202609", data={})
