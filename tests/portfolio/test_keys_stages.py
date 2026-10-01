import pytest
from src.portfolio.config import load_config
from src.portfolio.entities import MasterProject
from src.portfolio.model.keys import MasterIndex, resolve_code
from src.portfolio.model.stages import stage_cat

MASTER = [MasterProject("BR0000016203", "ABLE"), MasterProject("BR0000016638", "KILO 10"), MasterProject("BR0000013403", "HH_BONE")]
SEG_MASTER = [MasterProject("BR1", "TR_BU10_IPC_KOS"), MasterProject("BR2", "TR_BU10_IPC_Gomez 10"),
              MasterProject("BR3", "TR_BU10_IPC_DUO"), MasterProject("BR4", "TR_BU10_NB_DUO")]


def test_code_wins_over_name():
    idx = MasterIndex(MASTER)
    assert resolve_code("whatever", "BR0000016638", idx, {}) == ("BR0000016638", True)


def test_name_normalised_then_alias_then_unresolved():
    idx = MasterIndex(MASTER)
    assert resolve_code("Kilo10", None, idx, {}) == ("BR0000016638", True)
    assert resolve_code("HH-BONE", "", idx, {}) == ("BR0000013403", True)
    assert resolve_code("AERIS", None, idx, {"AERIS": "ABLE"}) == ("BR0000016203", True)
    assert resolve_code("GHOST 2", None, idx, {}) == ("NAME:GHOST2", False)


def test_unique_segment_suffix_is_accepted():
    idx = MasterIndex(SEG_MASTER)
    assert resolve_code("KOS", None, idx, {}) == ("BR1", True)
    assert resolve_code("Gomez 10", None, idx, {}) == ("BR2", True)
    assert resolve_code("IPC_KOS", None, idx, {}) == ("BR1", True)


def test_ambiguous_or_non_boundary_suffix_stays_unresolved():
    idx = MasterIndex(SEG_MASTER)
    assert resolve_code("DUO", None, idx, {}) == ("NAME:DUO", False)          # 兩個 master 都符合
    assert resolve_code("OKOS", None, idx, {}) == ("NAME:OKOS", False)        # 字串尾碼但不在段邊界
    assert resolve_code("KOS_TR", None, idx, {}) == ("NAME:KOSTR", False)     # 段順序不對
    assert resolve_code("", None, idx, {}) == ("NAME:", False)


@pytest.mark.parametrize("stage,cat", [
    ("RFQ", "RFQ / RFI"), ("RFI", "RFQ / RFI"), ("POC-DVT-1", "POC"), ("DVT2", "Execution"), ("Pre-EIV", "Execution"),
    ("PVT2 --> DVT (for v.D01)", "Execution"), ("MP", "MP"), ("Sustain", "Sustain / EOP"), ("EOP", "Sustain / EOP"),
    ("suspended", "Suspended"), ("Suspending", "Suspended"),
    ("Terminate", "Terminated"), ("Terminated", "Terminated"), ("discontinued", "Terminated"), ("cancelled", "Terminated"),
    ("Suspend", "Suspended"), ("on hold", "Suspended"),   # 2026-10：結案與暫停分開，處置不同（撤人 vs 保留）
    ("", ""), ("banana", "Other")])
def test_stage_cat(stage, cat):
    assert stage_cat(stage, load_config()) == cat
