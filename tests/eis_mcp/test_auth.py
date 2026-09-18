import asyncio
import stat
import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from src.eis_mcp.auth import Audit, BearerAuthMiddleware, Principal, load_tokens, principal_from_headers

TOKENS = {"tok-up": Principal("Alice", "uploader"), "tok-view": Principal("Bob", "viewer")}


def test_load_tokens_ok_and_errors(tmp_path):
    f = tmp_path / "tokens.yaml"
    f.write_text("tokens:\n  - token: abc\n    name: Alice\n    role: uploader\n  - token: def\n    name: Bob\n    role: viewer\n")
    assert load_tokens(f) == {"abc": Principal("Alice", "uploader"), "def": Principal("Bob", "viewer")}
    f.write_text("tokens:\n  - token: abc\n    name: Alice\n    role: admin\n")
    with pytest.raises(ValueError, match="role"):
        load_tokens(f)
    f.write_text("tokens:\n  - token: abc\n    name: A\n    role: viewer\n  - token: abc\n    name: B\n    role: viewer\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_tokens(f)
    f.write_text("tokens: []\n")
    with pytest.raises(ValueError, match="no tokens"):
        load_tokens(f)


def test_load_tokens_rejects_invalid_types(tmp_path):
    f = tmp_path / "tokens.yaml"
    f.write_text("tokens:\n  - token: 0\n    name: Alice\n    role: uploader\n")
    with pytest.raises(ValueError, match="non-empty strings"):
        load_tokens(f)
    f.write_text("tokens:\n  - token: ''\n    name: Alice\n    role: uploader\n")
    with pytest.raises(ValueError, match="non-empty strings"):
        load_tokens(f)


def test_load_tokens_rejects_non_mapping(tmp_path):
    f = tmp_path / "tokens.yaml"
    f.write_text("- token: abc\n  name: Alice\n  role: uploader\n")
    with pytest.raises(ValueError, match="mapping"):
        load_tokens(f)


def test_load_tokens_rejects_non_mapping_entry(tmp_path):
    f = tmp_path / "tokens.yaml"
    f.write_text("tokens:\n  - - invalid\n")
    with pytest.raises(ValueError, match="must be a mapping"):
        load_tokens(f)


def test_principal_from_headers():
    assert principal_from_headers({"authorization": "Bearer tok-up"}, TOKENS) == Principal("Alice", "uploader")
    assert principal_from_headers({"authorization": "bearer tok-view "}, TOKENS) == Principal("Bob", "viewer")
    assert principal_from_headers({"authorization": "Basic tok-up"}, TOKENS) is None
    assert principal_from_headers({}, TOKENS) is None
    assert principal_from_headers({"authorization": "Bearer nope"}, TOKENS) is None
    assert principal_from_headers({"authorization": "Bearer "}, TOKENS) is None
    assert principal_from_headers({"authorization": "Bearer"}, TOKENS) is None


def _app():
    async def who(request):
        return JSONResponse({"name": request.state.principal.name, "role": request.state.principal.role})
    app = Starlette(routes=[Route("/who", who)])
    app.add_middleware(BearerAuthMiddleware, tokens=TOKENS)
    return app


def _get(app, headers):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", headers=headers) as c:
            return await c.get("/who")
    return asyncio.run(go())


def test_middleware_401_without_token_and_sets_principal():
    app = _app()
    r = _get(app, {}); assert r.status_code == 401 and r.json()["error"] == "unauthorized"
    r = _get(app, {"Authorization": "Bearer nope"}); assert r.status_code == 401
    r = _get(app, {"Authorization": "Bearer tok-view"}); assert r.status_code == 200 and r.json() == {"name": "Bob", "role": "viewer"}


def test_audit_db_created_owner_only(tmp_path):
    db = tmp_path / "audit.sqlite"
    Audit(db)
    assert stat.S_IMODE(db.stat().st_mode) == 0o600


def test_audit_records_rows(tmp_path):
    a = Audit(tmp_path / "audit.sqlite")
    a.record(Principal("Alice", "uploader"), "tool", "ingest_month", {"report_month": "202609"}, "ok", 1234)
    a.record(None, "upload", "upload:202609", {}, "error", 5, "bad month")
    rows = a.rows()
    assert len(rows) == 2
    assert rows[0]["name"] == "Alice" and rows[0]["role"] == "uploader" and rows[0]["kind"] == "tool" and rows[0]["status"] == "ok"
    assert rows[0]["args_json"] == '{"report_month": "202609"}' and rows[0]["duration_ms"] == 1234 and rows[0]["at"]
    assert rows[1]["name"] is None and rows[1]["detail"] == "bad month"
