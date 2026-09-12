import json
from pathlib import Path
from tests.portfolio.conftest import make_xlsx
from tests.portfolio.test_briefing import HDR as BHDR, PRE, row as brow
from tests.portfolio.test_control_list import sheets as cl_sheets
from tests.portfolio.test_resource_summary import block, M
from src.portfolio.cli import main


def build_input(d: Path):
    make_xlsx(d / "Project List-202609.xlsx", {"project": [["BU", "維護月份", "PROJECTCODE", "PROJECTNAME", "PROJECTGROUP", "產品別", "當月生失效", "通知人員"],
                                                          ["BU10", "202609", "BR0000015346", "THORPE", "Trenton", "BU10_IPC", "Y", "X"]]})
    make_xlsx(d / "BU10_Project_Briefing_20260907.xlsx", {"20260907": PRE + [BHDR, brow("1", "PVT", "THORPE", pvt="3/21/2026", mpo="10/13/2025", mp="7/31/2026", code="BR0000015346")]})
    make_xlsx(d / "2026 EIS Resource Summary.xlsx", {"Trenton": block("THORPE", [12.0] * 8 + [0] * 4, [1e6] * 8 + [0] * 4)})
    make_xlsx(d / "2026  EIS Resource Control List-THORPE (Some One).xlsx", cl_sheets())


def test_end_to_end(tmp_path, capsys):
    inp = tmp_path / "input-09"; inp.mkdir(); build_input(inp)
    rc = main(["--input", str(inp), "--report-month", "202609", "--today", "2026-09-12", "--snapshots", str(tmp_path / "snaps"), "--out", str(tmp_path / "out")])
    assert rc == 0
    html = (tmp_path / "out" / "portfolio_202609_en.html").read_text(encoding="utf-8")
    assert "Decisions this month" in html and "THORPE" in html and "LA0801557" not in html and "SECRET_NAME" not in html
    snap = json.loads((tmp_path / "snaps" / "202609" / "portfolio.json").read_text())
    assert snap["meta"]["latest_month"] == 8 and snap["projects"][0]["code"] == "BR0000015346"
    assert snap["meta"]["snap_rev"] == 1
    # 第二次跑（假裝下個月），要能讀到上月快照
    rc2 = main(["--input", str(inp), "--report-month", "202610", "--today", "2026-10-12", "--snapshots", str(tmp_path / "snaps"), "--out", str(tmp_path / "out")])
    assert rc2 == 0 and (tmp_path / "snaps" / "202610" / "portfolio.json").exists()


def test_missing_master_fails(tmp_path):
    inp = tmp_path / "empty"; inp.mkdir()
    assert main(["--input", str(inp), "--report-month", "202609", "--out", str(tmp_path / "o"), "--snapshots", str(tmp_path / "s")]) == 1


def test_pii_hit_writes_neither_html_nor_snapshot(tmp_path, monkeypatch, capsys):
    inp = tmp_path / "input-09"; inp.mkdir(); build_input(inp)
    monkeypatch.setattr("src.portfolio.cli.find_pii", lambda text, *a, **kw: ["LA0000001"])
    out, snaps = tmp_path / "out", tmp_path / "snaps"
    rc = main(["--input", str(inp), "--report-month", "202609", "--today", "2026-09-12", "--snapshots", str(snaps), "--out", str(out)])
    assert rc == 2
    assert "LA0000001" in capsys.readouterr().err
    assert not (out / "portfolio_202609_en.html").exists()
    assert not (snaps / "202609" / "portfolio.json").exists()


def test_no_manpower_month_fails(tmp_path):
    inp = tmp_path / "input-zero"; inp.mkdir(); build_input(inp)
    make_xlsx(inp / "2026 EIS Resource Summary.xlsx", {"Trenton": block("THORPE", [0] * 12, [0] * 12)})
    out, snaps = tmp_path / "out", tmp_path / "snaps"
    rc = main(["--input", str(inp), "--report-month", "202609", "--today", "2026-09-12", "--snapshots", str(snaps), "--out", str(out)])
    assert rc == 1
    assert not (out / "portfolio_202609_en.html").exists()
    assert not (snaps / "202609" / "portfolio.json").exists()
