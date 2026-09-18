"""靜態 Bearer token 認證、角色、稽核。tokens.yaml 由管理者手動維護，改了要重啟。"""
from __future__ import annotations
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import yaml
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from .store import now_iso

ROLES = ("uploader", "viewer")


@dataclass(frozen=True)
class Principal:
    name: str
    role: str


def load_tokens(path: Path) -> dict[str, Principal]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, Principal] = {}
    for i, row in enumerate(doc.get("tokens") or []):
        tok, name, role = row.get("token"), row.get("name"), row.get("role")
        if not tok or not name or role not in ROLES:
            raise ValueError(f"tokens.yaml entry {i}: need token, name and role in {ROLES}")
        if str(tok) in out:
            raise ValueError(f"tokens.yaml: duplicate token used by {out[str(tok)].name} and {name}")
        out[str(tok)] = Principal(str(name), role)
    if not out:
        raise ValueError("tokens.yaml has no tokens")
    return out


def principal_from_headers(headers: Mapping[str, str], tokens: dict[str, Principal]) -> Principal | None:
    auth = headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    return tokens.get(auth[7:].strip())


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, tokens: dict[str, Principal]):
        super().__init__(app)
        self.tokens = tokens

    async def dispatch(self, request: Request, call_next):
        p = principal_from_headers(request.headers, self.tokens)
        if p is None:
            return JSONResponse({"error": "unauthorized", "detail": "send 'Authorization: Bearer <token>'; ask the server owner for a token"}, status_code=401)
        request.state.principal = p
        return await call_next(request)


class Audit:
    """每次 upload / tool / resource 一列。只存參數，不存回傳。"""
    COLUMNS = ("id", "at", "name", "role", "kind", "action", "args_json", "status", "duration_ms", "detail")

    def __init__(self, db: Path):
        self.db = Path(db)
        with sqlite3.connect(self.db) as c:
            c.execute("CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at TEXT, name TEXT, role TEXT, kind TEXT, "
                      "action TEXT, args_json TEXT, status TEXT, duration_ms INTEGER, detail TEXT)")

    def record(self, principal: Principal | None, kind: str, action: str, args: dict, status: str, duration_ms: int, detail: str = "") -> None:
        with sqlite3.connect(self.db) as c:
            c.execute("INSERT INTO audit(at, name, role, kind, action, args_json, status, duration_ms, detail) VALUES (?,?,?,?,?,?,?,?,?)",
                      (now_iso(), principal.name if principal else None, principal.role if principal else None, kind, action,
                       json.dumps(args, ensure_ascii=False), status, duration_ms, detail))

    def rows(self) -> list[dict]:
        with sqlite3.connect(self.db) as c:
            return [dict(zip(self.COLUMNS, r)) for r in c.execute("SELECT " + ", ".join(self.COLUMNS) + " FROM audit ORDER BY id")]
