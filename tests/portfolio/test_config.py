from src.portfolio.config import load_config, normalize_name


def test_normalize_name():
    assert normalize_name(" Kilo 10 ") == "KILO10"
    assert normalize_name("HH-BONE") == "HHBONE" == normalize_name("hh_bone")


def test_load_repo_config():
    c = load_config()
    assert c.thresholds["mp_slip_days"] == 60
    assert c.aliases["AERIS"] == "ABLE"
    assert c.stages[0][0] == "Terminated" and c.stages[0][1].search("discontinued")
    assert c.stages[1][0] == "Suspended" and c.stages[1][1].search("suspend")
    assert c.fallback_stage == "Other"
