import datetime as dt
import pytest
from src.portfolio.extract.briefing import parse_date, read_briefing, latest_snap

HDR = [None, "Stage", "Product", "Customer ", "Project Name", "EVT Date", "DVT Date", "PVT Date",
       "Original MP Date", "MP Date ", "Project status", "Sales", "PM ", "PM Lead ", "Project Lead",
       "RFQ Date", "BA Date", "Kick-Off Date", "EOP Date", "EOS Date", "資料更新日", "Project Code"]
PRE = [[None] * 22, [None, "(2026/09/07)"], [None, "BU10 Project Brief"]]


def row(n, stage, name, evt=None, dvt=None, pvt=None, mpo=None, mp=None, code=None, kick=None, upd=None):
    return [n, stage, "Tablet 10\"", "Dior", name, evt, dvt, pvt, mpo, mp, "status", "SALES_NAME", "PM_NAME",
            "LEAD", "LEAD2", None, None, kick, "NA", "NA", upd, code]


@pytest.mark.parametrize("v,exp", [
    ("12/15/2026", "2026-12-15"), ("2/5/2027", "2027-02-05"), (dt.datetime(2026, 7, 24), "2026-07-24"),
    ("2026-10-29 00:00:00", "2026-10-29"), ("NA", None), ("TBD", None), (None, None), ("Q4 2026", None),
    ("9/1\n8/27已提供NRE費用預估", None)])
def test_parse_date(v, exp):
    assert parse_date(v) == exp


def test_reads_all_snapshot_sheets_and_skips_others(xlsx):
    p = xlsx("b.xlsx", {
        "20260907": PRE + [HDR, row("1", "RFQ", "KILO10", evt="12/15/2026", mpo="8/26/2027", mp="8/12/2027", code="BR0000016638", kick="12/3/2025", upd=dt.datetime(2026, 6, 16))],
        "20260831": PRE + [HDR, row("1", "Pre-EIV", "KILO10", evt="12/15/2026", mpo="8/26/2027", mp="TBD", code="BR0000016638")],
        "PM Resource Allocation": [["x"]],
        "ProjectCode": [["y"]]})
    rows, issues = read_briefing(p)
    assert sorted({r.snap for r in rows}) == ["20260831", "20260907"]
    latest = [r for r in rows if r.snap == "20260907"][0]
    assert latest.code == "BR0000016638" and latest.stage == "RFQ" and latest.customer == "Dior"
    assert latest.dates["evt"] == "2026-12-15" and latest.dates["mp"] == "2027-08-12" and latest.dates["mp_orig"] == "2027-08-26"
    assert latest.dates["kickoff"] == "2025-12-03" and latest.updated == "2026-06-16"
    assert latest_snap(rows) == "20260907"
    assert not any("SALES_NAME" in r.status_text for r in rows)


def test_sheet_without_header_is_reported(xlsx):
    p = xlsx("b.xlsx", {"20260907": [["nothing"]]})
    rows, issues = read_briefing(p)
    assert rows == [] and issues[0].check == "briefing_sheet_unreadable"


def test_no_snapshot_sheet_raises(xlsx):
    p = xlsx("b.xlsx", {"Other": [["x"]]})
    with pytest.raises(ValueError):
        read_briefing(p)
