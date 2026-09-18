"""app 與所有 tools 共用的執行期狀態。"""
from __future__ import annotations
from dataclasses import dataclass
from ..portfolio.config import Config
from .auth import Audit, Principal
from .store import Store


@dataclass
class ServerState:
    store: Store
    tokens: dict[str, Principal]
    audit: Audit
    cfg: Config
