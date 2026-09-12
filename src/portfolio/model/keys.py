"""PROJECTCODE 解析。代碼優先；名稱只在沒有代碼時當備援。
解析順序：code → alias → 正規化全名 → 唯一的「段尾碼」比對（見 segments()）。"""
from __future__ import annotations
import re
from ..config import normalize_name
from ..entities import MasterProject

SEP_RE = re.compile(r"[\s_\-]+")


def segments(s: str) -> tuple[str, ...]:
    """把名稱切成大寫的段：`TR_BU10_IPC_Gomez 10` -> ('TR','BU10','IPC','GOMEZ','10')。"""
    return tuple(p for p in SEP_RE.split(str(s).strip().upper()) if p)


class MasterIndex:
    def __init__(self, master: list[MasterProject]):
        self.by_code = {m.code: m for m in master}
        self.by_norm = {normalize_name(m.name): m for m in master}
        self.by_segments = [(segments(m.name), m) for m in master]

    def segment_suffix_match(self, name: str) -> MasterProject | None:
        """只有剛好一個 master 的段序列以候選的段序列結尾時才算命中；0 個或多個都視為對不上。
        用段比對而不是字串 endswith，避免 `OKOS` 被當成 `..._KOS`。"""
        segs = segments(name)
        if not segs:
            return None
        hits = [m for ms, m in self.by_segments if len(ms) >= len(segs) and ms[-len(segs):] == segs]
        return hits[0] if len(hits) == 1 else None


def resolve_code(name: str, code: str | None, idx: MasterIndex, aliases: dict[str, str]) -> tuple[str, bool]:
    if code and str(code).strip():
        return str(code).strip(), True
    norm = normalize_name(name)
    norm = aliases.get(norm, norm)
    if norm in idx.by_norm:
        return idx.by_norm[norm].code, True
    m = idx.segment_suffix_match(name)
    if m is not None:
        return m.code, True
    return f"NAME:{norm}", False
