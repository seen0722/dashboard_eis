import re
import pytest
from src.portfolio.render.strings import STRINGS, t
from src.portfolio.render.css import CSS


def test_en_and_zh_have_same_keys():
    assert set(STRINGS["en"]) == set(STRINGS["zh"])


def test_format_and_missing_key():
    assert t("en", "ex_milestones_passed_title", n=6) == "6 milestones passed without a stage change"
    with pytest.raises(KeyError):
        t("en", "nope")


def test_no_middle_dots_or_all_caps_labels():
    for v in STRINGS["en"].values():
        if isinstance(v, str):
            assert "·" not in v and "→" not in v
            assert not re.fullmatch(r"[A-Z ]{6,}", v)


def test_css_tokens_present():
    for tok in ("#F5F6F4", "#22262A", "#3D5A80", "#5C8D89", "#E8590C"):
        assert tok.lower() in CSS.lower()
