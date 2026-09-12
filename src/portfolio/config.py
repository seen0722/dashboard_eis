"""讀 config/*.yaml。root 預設為 repo 根目錄。"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def normalize_name(s: str) -> str:
    return re.sub(r"[\s_\-]", "", str(s).strip().upper())


@dataclass
class Config:
    stages: list[tuple[str, re.Pattern]] = field(default_factory=list)
    fallback_stage: str = "Other"
    aliases: dict[str, str] = field(default_factory=dict)
    thresholds: dict = field(default_factory=dict)


def load_config(root: Path | None = None) -> Config:
    root = Path(root) if root else REPO_ROOT
    cfg = root / "config"
    st = yaml.safe_load((cfg / "stages.yaml").read_text(encoding="utf-8"))
    al = yaml.safe_load((cfg / "portfolio_aliases.yaml").read_text(encoding="utf-8")) or {}
    th = yaml.safe_load((cfg / "thresholds.yaml").read_text(encoding="utf-8")) or {}
    return Config(
        stages=[(o["cat"], re.compile(o["pattern"], re.I)) for o in st["order"]],
        fallback_stage=st.get("fallback", "Other"),
        aliases={normalize_name(k): normalize_name(v) for k, v in (al.get("names") or {}).items()},
        thresholds=th.get("portfolio") or {})
