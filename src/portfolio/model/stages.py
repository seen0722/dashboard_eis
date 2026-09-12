"""Briefing Stage 文字 → stage_cat，規則在 config/stages.yaml。"""
from __future__ import annotations
from ..config import Config


def stage_cat(stage: str, cfg: Config) -> str:
    s = (stage or "").strip()
    if not s:
        return ""
    for cat, pat in cfg.stages:
        if pat.search(s):
            return cat
    return cfg.fallback_stage
