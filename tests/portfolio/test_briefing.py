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
    assert (latest.biz_type, latest.category, latest.panel_size) == ("", "", "")   # 舊版面沒有這三欄，留空不推算
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


# 2026-09 起 PM 改版：表頭第一格是 Type、Product 拆成 Category + Panel Size、Project Code 移到 H 欄（Y 欄仍保留一份）、日期為 datetime。
HDR_V2 = [None, "Type", "Stage", "Category", "Customer ", "Project Name", "Panel Size", "Project Code",
          "EVT Date", "DVT Date", "PVT Date", "Original MP Date", "MP Date ", "Project status", "Sales", "PM ",
          "PM Lead ", "Project Lead", "RFQ Date", "BA Date", "Kick-Off Date", "EOP Date", "EOS Date", "資料更新日", "Project Code"]
PRE_V2 = [[None] * 25, [None, "(2026/09/29)"], [None, None, "BU10 Project Brief"]]


def row_v2(n, stage, name, code, evt=None, mp=None, category="Tablet", panel='10"', upd=None):
    return [n, "JDM", stage, category, "Dell", name, panel, code, evt, None, None, None, mp, "status", "SALES_NAME",
            "PM_NAME", "LEAD", "LEAD2", None, None, None, "NA", "NA", upd, code]


def test_reads_v2_layout_with_type_column_first(xlsx):
    p = xlsx("b.xlsx", {"20260929": PRE_V2 + [
        HDR_V2, row_v2("1", "RFQ", "KILO10", "BR0000016638", evt=dt.datetime(2026, 12, 25), mp=dt.datetime(2027, 8, 12), upd=dt.datetime(2026, 6, 16)),
        row_v2("2", "POC", "Aeris", "BR0000016203", category="NB", panel='14"'),
        row_v2("3", "RFQ", "N1X", "BR0000016916", category="AI PC", panel="NA")]})
    rows, issues = read_briefing(p)
    assert issues == []
    by = {r.name: r for r in rows}
    k = by["KILO10"]
    assert k.code == "BR0000016638" and k.stage == "RFQ" and k.customer == "Dell"
    assert k.dates["evt"] == "2026-12-25" and k.dates["mp"] == "2027-08-12" and k.updated == "2026-06-16"
    assert k.product == 'Tablet 10"'            # Category + Panel Size 組回舊版 Product 的形狀
    assert by["Aeris"].product == 'NB 14"'
    assert by["N1X"].product == "AI PC"          # Panel Size 為 NA 時不拼
    assert (k.biz_type, k.category, k.panel_size) == ("JDM", "Tablet", '10"')
    assert (by["N1X"].biz_type, by["N1X"].category, by["N1X"].panel_size) == ("JDM", "AI PC", "NA")
    assert not any("SALES_NAME" in r.status_text for r in rows)


def test_mixed_old_and_v2_sheets_in_one_workbook(xlsx):
    p = xlsx("b.xlsx", {
        "20260929": PRE_V2 + [HDR_V2, row_v2("1", "PVT", "Foxtrot", "BR0000016394")],
        "20260907": PRE + [HDR, row("1", "DVT2", "Foxtrot", code="BR0000016394")]})
    rows, issues = read_briefing(p)
    assert issues == [] and latest_snap(rows) == "20260929"
    stages = {r.snap: r.stage for r in rows if r.code == "BR0000016394"}
    assert stages == {"20260907": "DVT2", "20260929": "PVT"}
