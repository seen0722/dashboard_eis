"""eis_mcp 測試共用：fixtures 與跨 ASGI 的 MCP client helper（不需要 pytest-asyncio）。

mcp 2.2.0 的 StreamableHTTPSessionManager.run() 只能對同一個 instance 呼叫一次
（_has_started 一設就不會重置）；一個真正的 server 也只在啟動時進入一次 lifespan，
然後在裡面服務所有請求。因此這裡的 helper 不是每次呼叫都重新進出 lifespan，而是
把每個 app 的 lifespan 懶啟動一次、放到一個共用的背景 event loop 上執行，之後所有
呼叫都在同一個 loop 上執行；`app` fixture 在測試結束時會請求把該 app 的 lifespan
退出並從 `_started` 移除，避免每個測試留下的 Store／Audit／task group 累積一整個
pytest process 的生命週期。

anyio 的 CancelScope／TaskGroup 要求 enter 與 exit 發生在同一個 asyncio Task 裡，
所以「進入 lifespan」與「退出 lifespan」不能是分別獨立提交到 loop 的兩個 coroutine
（那樣會落在兩個不同的 Task 上，__aexit__ 時會拿到
「Attempted to exit cancel scope in a different task than it was entered in」）。
因此改成單一常駐 Task（`_AppLifespan.run`）從頭到尾包住整個
`async with app.router.lifespan_context(app):` 區塊，靠 `ready`／`stop` 兩個
asyncio.Event 對外面的呼叫方發訊號；啟動與收尾都只是設訊號、等訊號，不會跨 Task
去動 CancelScope。對外的 fixture／函式簽章與回傳值都維持原樣。
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

try:
    from builtins import BaseExceptionGroup
except ImportError:
    BaseExceptionGroup = Exception  # type: ignore

TOKENS = {"tok-up": Principal("Alice", "uploader"), "tok-view": Principal("Bob", "viewer")}
TODAY = "2026-09-12"

_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, name="eis-mcp-test-loop", daemon=True).start()
_started: dict[int, tuple] = {}  # id(app) -> (app, _AppLifespan, task)；保留 app 的強參照避免 id() 被回收重用


def _run(coro):
    return asyncio.run_coroutine_threadsafe(coro, _loop).result()


class _AppLifespan:
    """把一個 app 的 lifespan 包成單一常駐 task：enter/exit 都在這個 task 裡發生。"""

    def __init__(self, app):
        self.app = app
        self.ready = asyncio.Event()
        self.stop = asyncio.Event()

    async def run(self):
        async with self.app.router.lifespan_context(self.app):
            self.ready.set()
            await self.stop.wait()


async def _ensure_lifespan(app):
    key = id(app)
    if key in _started:
        return
    lc = _AppLifespan(app)
    task = asyncio.ensure_future(lc.run())
    ready_f = asyncio.ensure_future(lc.ready.wait())
    # 等 ready 與 task 兩者其一先完成：如果 lifespan __aenter__ 直接丟例外，run()
    # 這個 task 會先結束（而 ready 永遠不會被設），這裡要把例外浮出去，而不是讓
    # 呼叫方在 `await lc.ready.wait()` 上永遠卡住（進而讓整個 pytest 行程掛住）。
    done, _ = await asyncio.wait({ready_f, task}, return_when=asyncio.FIRST_COMPLETED)
    if task in done and not ready_f.done():
        ready_f.cancel()
        try:
            await ready_f
        except asyncio.CancelledError:
            pass
        task.result()  # 重新丟出讓 lifespan 啟動失敗的例外
    _started[key] = (app, lc, task)


async def _teardown_lifespan(app):
    entry = _started.pop(id(app), None)
    if entry is not None:
        _, lc, task = entry
        lc.stop.set()
        await task


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
    a = build_app(store, TOKENS)
    yield a
    _run(_teardown_lifespan(a))


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


def _leaf(exc: BaseException) -> BaseException:
    """anyio/mcp 包成 ExceptionGroup；測試要看的是最裡面那個錯。"""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


def read_resource(app, token, uri):
    """回 (text, mime_type)；讀不到時 raise 最內層的例外。"""
    async def go():
        await _ensure_lifespan(app)
        try:
            async with Client(streamable_http_client("http://test/mcp", http_client=http(app, token))) as cl:
                r = await cl.read_resource(uri)
                return r.contents[0].text, r.contents[0].mime_type
        except BaseExceptionGroup as eg:
            raise _leaf(eg) from eg
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
