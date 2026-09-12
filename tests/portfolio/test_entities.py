from dataclasses import asdict
from src.portfolio.entities import Issue, Project, PlanVsActual, empty_months


def test_empty_months_is_twelve_zeros():
    assert empty_months() == [0.0] * 12


def test_project_serialises_to_plain_dict():
    p = Project(code="BR0000015346", name="THORPE")
    d = asdict(p)
    assert d["code"] == "BR0000015346"
    assert d["dates"] == {"kickoff": None, "evt": None, "dvt": None, "pvt": None, "mp": None, "mp_orig": None}
    assert d["fte"] == [0.0] * 12


def test_issue_defaults():
    i = Issue(level="track", check="x", detail="d", source="Briefing")
    assert i.code is None
