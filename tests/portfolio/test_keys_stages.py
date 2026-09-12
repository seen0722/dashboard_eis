import pytest
from src.portfolio.config import load_config
from src.portfolio.entities import MasterProject
from src.portfolio.model.keys import MasterIndex, resolve_code
from src.portfolio.model.stages import stage_cat

MASTER = [MasterProject("BR0000016203", "ABLE"), MasterProject("BR0000016638", "KILO 10"), MasterProject("BR0000013403", "HH_BONE")]


def test_code_wins_over_name():
    idx = MasterIndex(MASTER)
    assert resolve_code("whatever", "BR0000016638", idx, {}) == ("BR0000016638", True)


def test_name_normalised_then_alias_then_unresolved():
    idx = MasterIndex(MASTER)
    assert resolve_code("Kilo10", None, idx, {}) == ("BR0000016638", True)
    assert resolve_code("HH-BONE", "", idx, {}) == ("BR0000013403", True)
    assert resolve_code("AERIS", None, idx, {"AERIS": "ABLE"}) == ("BR0000016203", True)
    assert resolve_code("GHOST 2", None, idx, {}) == ("NAME:GHOST2", False)


@pytest.mark.parametrize("stage,cat", [
    ("RFQ", "RFQ / RFI"), ("RFI", "RFQ / RFI"), ("POC-DVT-1", "POC"), ("DVT2", "Execution"), ("Pre-EIV", "Execution"),
    ("PVT2 --> DVT (for v.D01)", "Execution"), ("MP", "MP"), ("Sustain", "Sustain / EOP"), ("EOP", "Sustain / EOP"),
    ("suspended", "Suspended"), ("Suspending", "Suspended"), ("discontinued", "Suspended"), ("", ""), ("banana", "Other")])
def test_stage_cat(stage, cat):
    assert stage_cat(stage, load_config()) == cat
