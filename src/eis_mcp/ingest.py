"""ingest 一個月份：檔案鎖 → build_month() → 寫快照/HTML/ingest.json。PII 命中就什麼都不寫。"""
from __future__ import annotations
import fcntl
from ..portfolio.pipeline import build_month
from ..portfolio.render.pii import find_pii   # 獨立 import：測試會 monkeypatch src.eis_mcp.ingest.find_pii
from .state import ServerState
from .store import MONTH_RE, now_iso


class IngestBusy(Exception):
    pass


def mask_hit(s: str) -> str:
    """遮蔽一個 PII 命中片段：只留前 2 字元，其餘換成 '*'；不足 3 字元就整段遮掉。"""
    if len(s) < 3:
        return "**"
    return s[:2] + "*" * (len(s) - 2)


def run_ingest(state: ServerState, month: str, today: str, by: str) -> dict:
    if not MONTH_RE.match(month):
        raise ValueError(f"bad_month: '{month}' must be YYYYMM")
    lock_path = state.store.locks_root / f"{month}.lock"
    with open(lock_path, "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise IngestBusy(month) from None
        try:
            return _ingest_locked(state, month, today, by)
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _ingest_locked(state: ServerState, month: str, today: str, by: str) -> dict:
    store = state.store
    res = build_month(store.input_dir(month), month, today, store.snapshots_root, state.cfg, pii_check=find_pii)
    warnings = []
    if res.summary["control_lists"] == 0:
        warnings.append("no Control List was uploaded for this month: plan-vs-actual, tasks and dept loads are empty")
    base = {"at": now_iso(), "by": by, "today": today, "summary": res.summary, "issues_count": len(res.issues)}
    if res.pii_hits:
        store.record_ingest(month, {**base, "status": "rejected_pii", "pii_hits": res.pii_hits[:5]})
        return {"status": "rejected_pii", "hits": [mask_hit(h) for h in res.pii_hits[:5]], "hits_count": len(res.pii_hits),
                "summary": res.summary, "warnings": warnings,
                "next": "nothing was written; fix the source file (usually a Control List task description), re-upload it and call "
                        "ingest_month again; the unmasked fragments are in the server-side ingest log for this month"}
    store.write_result(month, res.snap, res.html)
    store.record_ingest(month, {**base, "status": "ok"})
    return {"status": "ok", "summary": res.summary,
            "health": [{"level": h["level"], "check": h["check"], "count": h["count"]} for h in res.snap["health"]],
            "issues_count": len(res.issues), "warnings": warnings}
