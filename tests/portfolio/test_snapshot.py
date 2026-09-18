import json
from src.portfolio.entities import Project, Exception_, HealthRow, Issue
from src.portfolio.model.load import DeptLoad
from src.portfolio.model.snapshot import build_snapshot, write_snapshot, read_previous
from src.portfolio.model.diff import cross_month_corrections


def test_write_and_read_previous(tmp_path):
    p = Project(code="BR1", name="A"); p.fte[6] = 17.0
    d = build_snapshot("202608", 7, "20260803", "2026-08-10", [p], [DeptLoad("D1", "x", "BSP")], [200] * 12,
                       [Exception_(1, "k", "e", "a", "s")], [HealthRow("ok", "c", "c", 0, [], "s")], [Issue("ok", "x", "1", "s")])
    path = write_snapshot(d, tmp_path)
    assert path == tmp_path / "202608" / "portfolio.json"
    assert json.loads(path.read_text())["projects"][0]["fte"][6] == 17.0
    assert list(path.parent.glob("*.tmp")) == []
    assert read_previous(tmp_path, "202609")["meta"]["report_month"] == "202608"
    assert read_previous(tmp_path, "202608") is None


def test_cross_month_corrections():
    prev = {"meta": {"latest_month": 7}, "projects": [{"code": "BR1", "name": "A", "fte": [0] * 6 + [17.0, 0, 0, 0, 0, 0]}]}
    p = Project(code="BR1", name="A"); p.fte[6] = 3.7; p.fte[7] = 4.0
    issues = cross_month_corrections(prev, [p], 8)
    assert len(issues) == 1 and issues[0].check == "cross_month_correction" and "Jul" in issues[0].detail and "17.0" in issues[0].detail
    assert cross_month_corrections(None, [p], 8) == []


def test_cross_month_corrections_malformed_prev_no_meta_short_fte():
    # prev with no meta, short fte should not raise and return []
    prev = {"projects": [{"code": "BR1", "name": "A", "fte": [17.0]}]}
    p = Project(code="BR1", name="A"); p.fte[6] = 3.7
    issues = cross_month_corrections(prev, [p], 8)
    assert issues == []


def test_cross_month_corrections_malformed_prev_missing_fte():
    # prev project entry missing "fte" should not raise and return []
    prev = {"meta": {"latest_month": 7}, "projects": [{"code": "BR1", "name": "A"}]}
    p = Project(code="BR1", name="A"); p.fte[6] = 3.7
    issues = cross_month_corrections(prev, [p], 8)
    assert issues == []


def test_read_previous_missing_root(tmp_path):
    # read_previous with non-existent root directory should return None
    assert read_previous(tmp_path / "nowhere", "202609") is None


def test_read_previous_missing_file(tmp_path):
    # read_previous with empty earlier directory and no portfolio.json should return None
    (tmp_path / "202607").mkdir()
    assert read_previous(tmp_path, "202608") is None
