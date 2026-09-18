"""server 資料根目錄的佈局與讀寫。所有路徑都從這裡出去，別的模組不自己拼路徑。

server_data/
├── tokens.yaml            0600
├── audit.sqlite
├── input/{YYYYMM}/        0700；原檔 + _upload.json
├── snapshots/{YYYYMM}/    portfolio.json + report_en.html + ingest.json
└── locks/{YYYYMM}.lock
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from ..portfolio.model.snapshot import write_snapshot

MONTH_RE = re.compile(r"^\d{6}$")
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("master", re.compile(r"^Project List-\d{6}\.xlsx$")),
    ("briefing", re.compile(r"^BU10_Project_Briefing_\d{8}\.xlsx$")),
    ("summary", re.compile(r"^.+Resource Summary\.xlsx$")),
    ("control_list", re.compile(r"^.+Resource Control List-.+\.(xlsx|xlsb)$")),
]
ALLOWED_DESCRIPTIONS = ["Project List-YYYYMM.xlsx", "BU10_Project_Briefing_YYYYMMDD.xlsx",
                        "<year> EIS Resource Summary.xlsx", "<year> EIS Resource Control List-<project> (<pm>).xlsx|.xlsb"]
_FORBIDDEN_CHARS = ("/", "\\", "\0")


def classify_filename(name: str) -> str | None:
    if not name or name.startswith("~$") or name.startswith(".") or ".." in name or any(c in name for c in _FORBIDDEN_CHARS):
        return None
    for cat, rx in PATTERNS:
        if rx.match(name):
            return cat
    return None


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class UnknownMonth(Exception):
    pass


def _check_month(month: str) -> str:
    """任何要把 month 拼進路徑之前都先過這關；擋掉 '../x' 這類 traversal。"""
    if not MONTH_RE.match(month):
        raise UnknownMonth(month)
    return month


class SnapshotBroken(Exception):
    pass


def _read_list(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _append(path: Path, rec: dict) -> None:
    rows = _read_list(path); rows.append(rec)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    path.chmod(0o600)


@dataclass
class Store:
    root: Path
    _cache: dict[str, tuple[int, dict]] = field(default_factory=dict, init=False, repr=False)

    @property
    def tokens_file(self) -> Path: return self.root / "tokens.yaml"
    @property
    def audit_db(self) -> Path: return self.root / "audit.sqlite"
    @property
    def input_root(self) -> Path: return self.root / "input"
    @property
    def snapshots_root(self) -> Path: return self.root / "snapshots"
    @property
    def locks_root(self) -> Path: return self.root / "locks"

    def init_layout(self) -> None:
        for d in (self.input_root, self.snapshots_root, self.locks_root):
            d.mkdir(parents=True, exist_ok=True)
            d.chmod(0o700)

    def check_permissions(self) -> list[str]:
        problems = []
        if stat.S_IMODE(self.input_root.stat().st_mode) & 0o077:
            problems.append(f"chmod 700 {self.input_root}")
        if self.snapshots_root.exists() and stat.S_IMODE(self.snapshots_root.stat().st_mode) & 0o077:
            problems.append(f"chmod 700 {self.snapshots_root}")
        if self.tokens_file.exists() and stat.S_IMODE(self.tokens_file.stat().st_mode) & 0o077:
            problems.append(f"chmod 600 {self.tokens_file}")
        if self.audit_db.exists() and stat.S_IMODE(self.audit_db.stat().st_mode) & 0o077:
            problems.append(f"chmod 600 {self.audit_db}")
        # Check per-month input directories and the raw files inside them (may carry PII fragments)
        if self.input_root.exists():
            for d in self.input_root.iterdir():
                if d.is_dir() and MONTH_RE.match(d.name):
                    if stat.S_IMODE(d.stat().st_mode) & 0o077:
                        problems.append(f"chmod 700 {d}")
                    for f in d.iterdir():
                        if f.is_file() and stat.S_IMODE(f.stat().st_mode) & 0o077:
                            problems.append(f"chmod 600 {f}")
        return problems

    def input_dir(self, month: str) -> Path: return self.input_root / _check_month(month)
    def snapshot_dir(self, month: str) -> Path: return self.snapshots_root / _check_month(month)

    # ---- 上傳 ----
    def register_upload(self, month: str, name: str, data: bytes, by: str) -> dict:
        d = self.input_dir(month); d.mkdir(parents=True, exist_ok=True); d.chmod(0o700)
        f = d / name; f.write_bytes(data); f.chmod(0o600)
        rec = {"name": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "uploaded_by": by, "uploaded_at": now_iso()}
        _append(d / "_upload.json", rec)
        return rec

    def uploads(self, month: str) -> list[dict]:
        return _read_list(self.input_dir(month) / "_upload.json")

    # ---- ingest ----
    def record_ingest(self, month: str, rec: dict) -> None:
        _append(self.snapshot_dir(month) / "ingest.json", rec)

    def ingests(self, month: str) -> list[dict]:
        return _read_list(self.snapshot_dir(month) / "ingest.json")

    def write_result(self, month: str, snap: dict, html: str) -> None:
        snap_path = write_snapshot(snap, self.snapshots_root)
        snap_path.chmod(0o600)
        html_path = self.snapshot_dir(month) / "report_en.html"
        html_path.write_text(html, encoding="utf-8")
        html_path.chmod(0o600)
        self.invalidate(month)

    # ---- 快照 ----
    def invalidate(self, month: str | None = None) -> None:
        if month is None:
            self._cache.clear()
        else:
            self._cache.pop(month, None)

    def load_snapshot(self, month: str) -> dict:
        f = self.snapshot_dir(month) / "portfolio.json"
        if not f.exists():
            raise UnknownMonth(month)
        mtime = f.stat().st_mtime_ns
        hit = self._cache.get(month)
        if hit and hit[0] == mtime:
            return hit[1]
        try:
            snap = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as ex:
            raise SnapshotBroken(month) from ex
        self._cache[month] = (mtime, snap)
        return snap

    def report_html(self, month: str) -> str:
        f = self.snapshot_dir(month) / "report_en.html"
        if not f.exists():
            raise UnknownMonth(month)
        return f.read_text(encoding="utf-8")

    def _status(self, month: str) -> str:
        f = self.snapshot_dir(month) / "portfolio.json"
        if not f.exists():
            return "uploaded_only"
        try:
            self.load_snapshot(month)
            return "ok"
        except SnapshotBroken:
            return "broken"

    def months(self) -> list[dict]:
        """已有月份的清單。uploads 不含原始檔名（Control List 檔名內嵌 PM 姓名）——
        只回 category/size/sha256/uploaded_by/uploaded_at；完整紀錄（含 name）只留在
        server 端的 input/<month>/_upload.json，供 /upload 當下的 HTTP 回應與稽核用。
        """
        names = set()
        for root in (self.input_root, self.snapshots_root):
            if root.exists():
                names |= {p.name for p in root.iterdir() if p.is_dir() and MONTH_RE.match(p.name)}
        out = []
        for m in sorted(names, reverse=True):
            ing = self.ingests(m)
            uploads = [{"category": classify_filename(u["name"]), "size": u["size"], "sha256": u["sha256"],
                       "uploaded_by": u["uploaded_by"], "uploaded_at": u["uploaded_at"]} for u in self.uploads(m)]
            out.append({"month": m, "status": self._status(m), "uploads": uploads, "last_ingest": ing[-1] if ing else None})
        return out

    def latest_month(self) -> str | None:
        for m in self.months():
            if m["status"] == "ok":
                return m["month"]
        return None
