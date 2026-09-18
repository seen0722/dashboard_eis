"""eis_mcp 測試共用：fixtures 與跨 ASGI 的 MCP client helper（不需要 pytest-asyncio）。

mcp 2.2.0 的 StreamableHTTPSessionManager.run() 只能對同一個 instance 呼叫一次
（_has_started 一設就不會重置）；一個真正的 server 也只在啟動時進入一次 lifespan，
然後在裡面服務所有請求。因此這裡的 helper 不是每次呼叫都重新進出 lifespan，而是
把每個 app 的 lifespan 懶啟動一次、放到一個共用的背景 event loop 上長駐，之後所有
呼叫都在同一個 loop 上執行——對外的 fixture／函式簽章與回傳值都維持原樣。
"""
import asyncio
import json
import threading
import httpx
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from src.eis_mcp.app import build_app
from src.eis_mcp.auth import Principal
from src.eis_mcp.store import Store
from tests.portfolio.test_cli import build_input

TOKENS = {"tok-up": Principal("Alice", "uploader"), "tok-view": Principal("Bob", "viewer")}
TODAY = "2026-09-12"

_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, name="eis-mcp-test-loop", daemon=True).start()
_started: dict[int, tuple] = {}  # id(app) -> (app, cm)；保留 app 的強參照避免 id() 被回收重用


def _run(coro):
    return asyncio.run_coroutine_threadsafe(coro, _loop).result()


async def _ensure_lifespan(app):
    key = id(app)
    if key not in _started:
        cm = app.router.lifespan_context(app)
        await cm.__aenter__()
        _started[key] = (app, cm)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "data"); s.init_layout()
    return s


@pytest.fixture
def input_pack(tmp_path):
    d = tmp_path / "pack"; d.mkdir(); build_input(d)
    return d


@pytest.fixture
def app(store):
    return build_app(store, TOKENS)


@pytest.fixture
def uploaded(app, input_pack):
    files = {p.name: p.read_bytes() for p in input_pack.iterdir()}
    r = post_upload(app, "tok-up", "202609", files)
    assert r.status_code == 200, r.text
    return app


@pytest.fixture
def ingested(uploaded):
    from src.eis_mcp.ingest import run_ingest
    out = run_ingest(uploaded.state.eis, "202609", TODAY, "Alice")
    assert out["status"] == "ok", out
    return uploaded


def http(app, token):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers)


def call_tool(app, token, name, args=None):
    """回 (is_error, payload)。成功時 payload 是 dict；失敗時是錯誤字串。"""
    async def go():
        await _ensure_lifespan(app)
        async with Client(streamable_http_client("http://test/mcp", http_client=http(app, token))) as cl:
            r = await cl.call_tool(name, args or {})
            text = r.content[0].text
            return r.is_error, (text if r.is_error else json.loads(text))
    return _run(go())


def read_resource(app, token, uri):
    """回 (text, mime_type)；讀不到時 raise。"""
    async def go():
        await _ensure_lifespan(app)
        async with Client(streamable_http_client("http://test/mcp", http_client=http(app, token))) as cl:
            r = await cl.read_resource(uri)
            return r.contents[0].text, r.contents[0].mime_type
    return _run(go())


def post_upload(app, token, month, files):
    """files: {filename: bytes}。回 httpx.Response。"""
    async def go():
        await _ensure_lifespan(app)
        async with http(app, token) as c:
            return await c.post(f"/upload/{month}", files=[("file", (n, b)) for n, b in files.items()])
    return _run(go())


def post_raw(app, token, path, **kw):
    async def go():
        await _ensure_lifespan(app)
        async with http(app, token) as c:
            return await c.post(path, **kw)
    return _run(go())
