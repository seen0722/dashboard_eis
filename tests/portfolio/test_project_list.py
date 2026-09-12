from src.portfolio.extract.project_list import read_project_list

HDR = ["BU", "維護月份", "PROJECTCODE", "PROJECTNAME", "PROJECTGROUP", "產品別", "當月生失效", "通知人員"]


def test_reads_rows_and_skips_blank_code(xlsx):
    p = xlsx("pl.xlsx", {"project": [HDR,
        ["BU10", "202609", "BR0000013157", "ZZTOP", "Unicorn", "BU10_IPC", "Y", "X"],
        ["BU10", "202609", None, "GHOST", "Unicorn", "BU10_IPC", "Y", "X"],
        ["BU10", "202609", "BR0000009956", "Pineapple", "Trenton", "BU10_IPC", "N", "X"]]})
    rows, issues = read_project_list(p)
    assert [r.code for r in rows] == ["BR0000013157", "BR0000009956"]
    assert rows[0].name == "ZZTOP" and rows[0].group == "Unicorn" and rows[0].family == "BU10_IPC"
    assert rows[1].active is False
    assert len(issues) == 1 and issues[0].check == "master_row_without_code"


def test_missing_header_raises(xlsx):
    p = xlsx("bad.xlsx", {"project": [["a", "b"], [1, 2]]})
    import pytest
    with pytest.raises(ValueError):
        read_project_list(p)
