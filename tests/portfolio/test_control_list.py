from pathlib import Path
from src.portfolio.extract.control_list import read_control_list, find_control_lists, label_from_filename

MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "TTL"]
TASK_HDR = ["部門&Project&月", "Project Code", "Project Name", "部門代碼", "部門名稱", "Function", "年度", "月份", "EIS", "EIS \nCharge", "Task  Description"]
MONTH_HDR = ["年月", "Company Code", "部門代碼", "部門名稱", "部門所屬BU", "部門屬性", "BU/FU", "Function", "部門&Project&月",
             "PROJECTCODE", "PROJECTNAME", "PROJECTGROUP", "主管填入人力", "單位TotalKeyIn人數", "人力百分比", "分攤原則", "NTD", "USD"]


def pva_sheet():
    return [["THROPE (FU RD)"] + MON, ["FU RD Budget plan", 5, 3] + [0] * 10 + [8], ["FU RD EIS 人力", 13.7, 11.1] + [None] * 10 + [24.8],
            ["FU EIS 分攤金額 NTD", 100, 200] + [None] * 10 + [300], ["FU RD Plan - EIS", -8.7] + [None] * 12, [None] * 14,
            ["THROPE  (BU RD)"] + MON, ["BU RD Budget plan ", 14.5] + [0] * 11 + [14.5], ["BU RD EIS 人力", 18.0] + [None] * 11 + [18], [None] * 14,
            ["THROPE  (PM)"] + MON, ["PM Budget plan"] + [None] * 13, ["PEGA PM EIS 人力", 4.1] + [None] * 11 + [4.1], [None] * 14,
            ["THROPE"] + MON, ["Total EIS 人力", 99] + [None] * 12, ["Total Amount NTD", 99] + [None] * 12]


def sheets():
    return {
        "Project List": [["ProjectCode", "ProjectName", "PM"], ["BR0000015346", "THORPE", None]],
        "BU-Task": [[None] * 11, TASK_HDR,
                    ["x", "BR0000015346", "THORPE", "BA80700R01", "第十事業處-研發二處-研發三部", "BSP", "2026", "1", 3.7, 1, "1. Software schedule"],
                    ["x", "BR0000015346", "THORPE", "BA80700R01", "第十事業處-研發二處-研發三部", "BSP", "2026", "7", 3.1, 1, None]],
        "FU-Task": [[None] * 11, TASK_HDR, ["x", "BR0000015346", "THORPE", "F890730R01", "研發資源中心-Regulatory", "HOMOLOGATION", "2026", "1", 0.3, 1, "System compliance"]],
        "8": [MONTH_HDR,
              ["202608", "Pega", "BA80700R01", "第十事業處-研發二處-研發三部", "BU10", "R", "BU", "BSP", "k", "BR0000015346", "THORPE", "Trenton", 3.1, 5, 0.62, "x", 1, 1],
              ["202608", "Pega", "F890730R01", "研發資源中心-Regulatory", "FU", "R", "FU", "HOMOLOGATION", "k", "BR0000015346", "THORPE", "Trenton", 0.06, 3, 0.02, "x", 1, 1]],
        "Plan vs. Acutal ": pva_sheet(),
        "實名制": [["BU", "部門代碼", "部門名稱", "EIS_FUNCTION", "合計"], ["BU", "BA80700R01", "x", "BSP", 3.1]],
        "人力": [["部門代碼", "部門名稱", "工號", "成員", "支援Project"], ["BA80700R01", "x", "LA0801557", "SECRET_NAME(祕密)", "BR0000015346"]],
    }


def test_reads_pva_tasks_and_load(xlsx):
    p = xlsx("2026  EIS Resource Control List-THORPE (Some One).xlsx", sheets())
    cl, issues = read_control_list(p)
    assert cl.label == "THORPE" and cl.codes == ["BR0000015346"]
    assert cl.pva["FU RD"].plan[:2] == [5.0, 3.0] and cl.pva["FU RD"].actual[:2] == [13.7, 11.1] and cl.pva["FU RD"].ntd[1] == 200.0
    assert cl.pva["BU RD"].plan[0] == 14.5 and cl.pva["PM"].actual[0] == 4.1 and cl.pva["PM"].plan == [0.0] * 12
    assert [(t.month, t.side, t.function, t.dept, t.fte, t.description) for t in cl.tasks] == [
        (1, "BU", "BSP", "研發三部", 3.7, "1. Software schedule"), (7, "BU", "BSP", "研發三部", 3.1, ""),
        (1, "FU", "HOMOLOGATION", "Regulatory", 0.3, "System compliance")]
    assert [(l.dept_code, l.month, l.allocated, l.keyed_in, l.code) for l in cl.load_rows] == [("BA80700R01", 8, 3.1, 5, "BR0000015346")]
    assert issues == []


def test_never_touches_people_sheets(xlsx, monkeypatch):
    from src.portfolio.extract import control_list as mod
    p = xlsx("2026  EIS Resource Control List-THORPE (Some One).xlsx", sheets())
    real = mod.open_workbook
    asked = []
    def spy(path):
        wb = real(path); orig = wb.rows
        wb.rows = lambda s: (asked.append(s), orig(s))[1]
        return wb
    monkeypatch.setattr(mod, "open_workbook", spy)
    read_control_list(p)
    assert "人力" not in asked and "實名制" not in asked


def test_missing_sheets_become_issues(xlsx):
    p = xlsx("2026  EIS Resource Control List-ABLE (X Y).xlsx", {"Only": [["x"]]})
    cl, issues = read_control_list(p)
    assert cl.label == "ABLE" and cl.pva == {} and cl.tasks == []
    assert {i.check for i in issues} == {"cl_no_plan_vs_actual", "cl_no_task_sheet", "cl_no_month_sheets"}


def test_short_task_row_does_not_raise(xlsx):
    def short_sheets():
        return {
            "BU-Task": [[None] * 11, TASK_HDR,
                        ["x", "BR0000015346", "THORPE", "BA80700R01", "第十事業處-研發二處-研發三部", "BSP", "2026", "1"]],
            "FU-Task": [[None] * 11, TASK_HDR],
            "Plan vs. Acutal ": pva_sheet(),
            "1": [MONTH_HDR],
        }
    p = xlsx("2026  EIS Resource Control List-SHORT (X Y).xlsx", short_sheets())
    cl, issues = read_control_list(p)
    assert cl.label == "SHORT" and len(cl.tasks) == 1
    t = cl.tasks[0]
    assert t.month == 1 and t.fte == 0.0 and t.description == ""


def test_short_month_row_does_not_raise(xlsx):
    p = xlsx("2026  EIS Resource Control List-SHORTM (X Y).xlsx", {
        "Plan vs. Acutal ": pva_sheet(),
        "BU-Task": [[None] * 11, TASK_HDR],
        "FU-Task": [[None] * 11, TASK_HDR],
        # 第一列短於 header（缺後面幾欄），第二列正常
        "8": [MONTH_HDR,
              ["202608", "Pega", "BA80700R01", "第十事業處-研發二處-研發三部", "BU10", "R", "BU", "BSP", "k", "BR0000015346"],
              ["202608", "Pega", "BA80700R02", "第十事業處-研發二處-研發四部", "BU10", "R", "BU", "BSP", "k", "BR0000015346", "THORPE", "Trenton", 1.5, 4, 0.3, "x", 1, 1]],
    })
    cl, issues = read_control_list(p)
    assert [i.check for i in issues] == []
    assert ("BA80700R02", 1.5, 4) in [(l.dept_code, l.allocated, l.keyed_in) for l in cl.load_rows]


def test_read_month_tolerates_rows_shorter_than_header():
    """xlsb 不像 openpyxl 會把列補齊，短列會讓原本的寫法 IndexError。"""
    from src.portfolio.extract.control_list import _read_month
    rows = [tuple(MONTH_HDR),
            ("202608", "Pega", "BA80700R01", "研發三部", "BU10", "R", "BU", "BSP", "k", "BR0000015346"),
            ("202608", "Pega", "BA80700R02", "研發四部", "BU10", "R", "BU", "BSP", "k", "BR0000015346", "THORPE", "Trenton", 1.5, 4, 0.3, "x", 1, 1)]
    out = _read_month(rows, 8)
    assert [(r.dept_code, r.allocated, r.keyed_in) for r in out] == [("BA80700R01", 0.0, 0), ("BA80700R02", 1.5, 4)]


def test_read_month_with_empty_or_short_header_returns_nothing():
    from src.portfolio.extract.control_list import _read_month
    assert _read_month([], 8) == []
    assert _read_month([()], 8) == []
    assert _read_month([(None,)], 8) == []
    assert _read_month([("年月", "Company Code")], 8) == []       # 缺必要欄


def test_empty_first_row_in_month_sheet_is_skipped(xlsx):
    p = xlsx("2026  EIS Resource Control List-EMPTYM (X Y).xlsx", {
        "Plan vs. Acutal ": pva_sheet(), "BU-Task": [[None] * 11, TASK_HDR], "FU-Task": [[None] * 11, TASK_HDR],
        "8": [[None], MONTH_HDR]})
    cl, issues = read_control_list(p)
    assert cl.load_rows == [] and [i.check for i in issues] == []


def test_parse_failure_becomes_cl_unreadable_not_an_exception(xlsx, monkeypatch):
    from src.portfolio.extract import control_list as mod
    p = xlsx("2026  EIS Resource Control List-BOOM (X Y).xlsx", sheets())
    monkeypatch.setattr(mod, "_read_tasks", lambda rows, side: (_ for _ in ()).throw(IndexError("tuple index out of range")))
    cl, issues = read_control_list(p)
    assert [i.check for i in issues] == ["cl_unreadable"]
    assert "BOOM" in issues[0].detail and "IndexError" in issues[0].detail
    assert cl.label == "BOOM"


def test_find_and_label(tmp_path):
    for n in ["2026  EIS Resource Control List-ABLE (A B).xlsx", "2026  EIS Resource Control List-RFQ_OTHERS(Re Pe).xlsx",
              "2026  EIS Resource Control List-CPL22B (K Y).xlsb", "~$2026 EIS Resource Summary.xlsx", "2026 EIS Resource Summary.xlsx"]:
        (tmp_path / n).write_bytes(b"")
    found = [p.name for p in find_control_lists(tmp_path)]
    assert found == ["2026  EIS Resource Control List-ABLE (A B).xlsx", "2026  EIS Resource Control List-CPL22B (K Y).xlsb",
                     "2026  EIS Resource Control List-RFQ_OTHERS(Re Pe).xlsx"]
    assert label_from_filename(Path(found[2])) == "RFQ_OTHERS"
