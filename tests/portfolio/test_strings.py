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
    for tok in ("#F3F5F8", "#1F2937", "#2563EB", "#1E2735", "#E8590C"):
        assert tok.lower() in CSS.lower()
    assert ".kpis{" in CSS and ".navt:checked~.links" in CSS and "@media(max-width:900px)" in CSS



def test_type_scale_tokens():
    for tok in ("--fs-xs:12px", "--fs-sm:13px", "--fs-base:14px", "--fs-md:16px", "--fs-lg:20px", "--fs-xl:28px"):
        assert tok in CSS, tok
