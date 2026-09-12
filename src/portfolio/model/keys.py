"""PROJECTCODE 解析。代碼優先；名稱只在沒有代碼時當備援。"""
from __future__ import annotations
from ..config import normalize_name
from ..entities import MasterProject


class MasterIndex:
    def __init__(self, master: list[MasterProject]):
        self.by_code = {m.code: m for m in master}
        self.by_norm = {normalize_name(m.name): m for m in master}


def resolve_code(name: str, code: str | None, idx: MasterIndex, aliases: dict[str, str]) -> tuple[str, bool]:
    if code and str(code).strip():
        return str(code).strip(), True
    norm = normalize_name(name)
    norm = aliases.get(norm, norm)
    if norm in idx.by_norm:
        return idx.by_norm[norm].code, True
    return f"NAME:{norm}", False
