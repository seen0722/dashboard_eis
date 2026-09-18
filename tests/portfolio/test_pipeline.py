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
