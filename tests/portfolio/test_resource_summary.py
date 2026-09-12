from src.portfolio.extract.resource_summary import read_resource_summary, latest_month

M = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "TTL"]


def block(name, fte, ntd):
    return [[name] + M, ["Total EIS 人力"] + fte + [sum(fte)], ["Total Amount NTD"] + ntd + [sum(ntd)], [None] * 14]


def test_reads_blocks_and_skips_summary(xlsx):
    fte = [1, 2, 3, 4, 5, 6, 7, 8, 0, 0, 0, 0]
    p = xlsx("rs.xlsx", {
        "Dior": block("D5K", fte, [10] * 8 + [0] * 4) + block("DIOR SUMMARY", fte, fte),
        "Unicorn": block("ZZTOP", [0.5] * 8 + [0] * 4, [1] * 12),
        "Summary": block("DIOR", fte, fte), "2026 佔比": [["人力"] + M]})
    rows, issues = read_resource_summary(p)
    assert [(r.name, r.group) for r in rows] == [("D5K", "Dior"), ("ZZTOP", "Unicorn")]
    assert rows[0].fte == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 0, 0, 0, 0]
    assert rows[0].ntd[0] == 10.0
    assert latest_month(rows) == 8
    assert issues == []


def test_latest_month_all_zero():
    assert latest_month([]) == 0


def test_block_without_ntd_row_is_reported(xlsx):
    p = xlsx("rs.xlsx", {"Dior": [["D5K"] + M, ["Total EIS 人力"] + [1] * 12 + [12], [None] * 14]})
    rows, issues = read_resource_summary(p)
    assert rows[0].ntd == [0.0] * 12
    assert issues[0].check == "summary_block_without_ntd"
