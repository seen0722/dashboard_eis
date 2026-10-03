import json
from src.portfolio.cli import main
from src.portfolio.config import load_config
from src.portfolio.pipeline import build_month, MissingInput, NoManpowerMonth, InputUnreadable
from tests.portfolio.conftest import make_xlsx
from tests.portfolio.test_cli import build_input
from tests.portfolio.test_resource_summary import block


def test_build_month_matches_cli_output(tmp_path):
    inp = tmp_path / "input-09"; inp.mkdir(); build_input(inp)
    snaps, out = tmp_path / "snaps", tmp_path / "out"
    assert main(["--input", str(inp), "--report-month", "202609", "--today", "2026-09-12", "--snapshots", str(snaps), "--out", str(out)]) == 0
    res = build_month(inp, "202609", "2026-09-12", snaps, load_config())
    assert res.snap == json.loads((snaps / "202609" / "portfolio.json").read_text(encoding="utf-8"))
    assert res.html == (out / "portfolio_202609_en.html").read_text(encoding="utf-8")
    assert res.pii_hits == []
    assert set(res.summary) == {"projects", "control_lists", "latest_month", "snap_date"}
    assert res.summary["latest_month"] == 8 and res.summary["snap_date"] == "20260907" and res.summary["control_lists"] == 1


def test_build_month_does_not_write_files(tmp_path):
    inp = tmp_path / "input-09"; inp.mkdir(); build_input(inp)
    build_month(inp, "202609", "2026-09-12", tmp_path / "snaps", load_config())
    assert not (tmp_path / "snaps").exists()


def test_missing_input_lists_categories(tmp_path):
    empty = tmp_path / "empty"; empty.mkdir()
    try:
        build_month(empty, "202609", "2026-09-12", tmp_path / "s", load_config())
        assert False, "expected MissingInput"
    except MissingInput as ex:
        assert ex.missing == ["master", "briefing", "summary"]


def test_no_manpower_month_raises(tmp_path):
    inp = tmp_path / "input-zero"; inp.mkdir(); build_input(inp)
    make_xlsx(inp / "2026 EIS Resource Summary.xlsx", {"Trenton": block("THORPE", [0] * 12, [0] * 12)})
    try:
        build_month(inp, "202609", "2026-09-12", tmp_path / "s", load_config())
        assert False, "expected NoManpowerMonth"
    except NoManpowerMonth as ex:
        assert "Resource Summary.xlsx" in str(ex)


def test_unreadable_master_raises(tmp_path):
    inp = tmp_path / "input-bad"; inp.mkdir(); build_input(inp)
    make_xlsx(inp / "Project List-202609.xlsx", {"project": [["nothing", "useful"]]})
    try:
        build_month(inp, "202609", "2026-09-12", tmp_path / "s", load_config())
        assert False, "expected InputUnreadable"
    except InputUnreadable:
        pass


def test_pii_check_is_injectable(tmp_path):
    inp = tmp_path / "input-09"; inp.mkdir(); build_input(inp)
    res = build_month(inp, "202609", "2026-09-12", tmp_path / "s", load_config(), pii_check=lambda text: ["LA0000001"])
    assert "LA0000001" in res.pii_hits


def test_reference_date_defaults_to_the_briefing_snapshot_not_the_run_day(tmp_path):
    """2026-10-03 需求方：延後與天數一律以 Briefing 快照日為準；事後重新 ingest 不可得到不同結果。"""
    inp = tmp_path / "input-09"; inp.mkdir(); build_input(inp)
    res = build_month(inp, "202609", None, tmp_path / "s1", load_config())
    assert res.snap["meta"]["generated"] == "2026-09-07"                                 # fixture 的 Briefing 快照日 20260907
    again = build_month(inp, "202609", None, tmp_path / "s2", load_config())
    assert again.snap["exceptions"] == res.snap["exceptions"] and again.html == res.html


def test_cli_without_today_uses_the_briefing_snapshot(tmp_path):
    inp = tmp_path / "input-09"; inp.mkdir(); build_input(inp)
    snaps, out = tmp_path / "snaps", tmp_path / "out"
    assert main(["--input", str(inp), "--report-month", "202609", "--snapshots", str(snaps), "--out", str(out)]) == 0
    assert json.loads((snaps / "202609" / "portfolio.json").read_text(encoding="utf-8"))["meta"]["generated"] == "2026-09-07"
