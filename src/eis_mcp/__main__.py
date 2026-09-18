"""python -m src.eis_mcp --data server_data --host 0.0.0.0 --port 8765 [--allowed-host eis-host:8765]"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
import uvicorn
from .app import build_app
from .auth import load_tokens
from .store import Store


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="EIS MCP server")
    ap.add_argument("--data", default="server_data", help="data root (tokens.yaml, input/, snapshots/, audit.sqlite)")
    ap.add_argument("--host", default="0.0.0.0"); ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--allowed-host", action="append", default=None,
                    help="Host header values to accept (enables DNS-rebinding protection); repeatable, e.g. eis-host:8765")
    a = ap.parse_args(argv)
    store = Store(Path(a.data)); store.init_layout()
    if not store.tokens_file.exists():
        print(f"{store.tokens_file} not found. Create it with entries like:\n"
              "tokens:\n  - token: <secrets.token_urlsafe(32)>\n    name: Alice\n    role: uploader\n"
              f"then: chmod 600 {store.tokens_file}", file=sys.stderr)
        return 1
    problems = store.check_permissions()
    if problems:
        print("refusing to start; fix permissions first:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    try:
        tokens = load_tokens(store.tokens_file)
    except ValueError as ex:
        print(str(ex), file=sys.stderr); return 1
    app = build_app(store, tokens, host=a.host, allowed_hosts=a.allowed_host)
    uvicorn.run(app, host=a.host, port=a.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
