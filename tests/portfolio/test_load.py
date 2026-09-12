from src.portfolio.entities import ControlList, DeptLoadRow
from src.portfolio.model.load import build_dept_loads, capacity_by_month


def row(dept, month, alloc, keyed, code, fn="BSP", name="第十事業處-研發二處-研發三部"):
    return DeptLoadRow(dept, name, fn, month, alloc, keyed, code)


def test_aggregates_across_projects_and_computes_util():
    a = ControlList("A", "a", load_rows=[row("D1", 8, 3.1, 5, "BR1"), row("D1", 7, 2.0, 5, "BR1"), row("D2", 8, 1.0, 4, "BR1", fn="EE")])
    b = ControlList("B", "b", load_rows=[row("D1", 8, 1.9, 5, "BR2")])
    loads, issues = build_dept_loads([a, b])
    d1 = [l for l in loads if l.dept_code == "D1"][0]
    assert d1.dept_name == "研發二處-研發三部" and d1.function == "BSP"
    assert d1.allocated[7] == 5.0 and d1.keyed_in[7] == 5 and d1.util[7] == 100
    assert d1.util[6] == 40 and d1.util[0] is None
    assert capacity_by_month(loads) == [0, 0, 0, 0, 0, 0, 5, 9, 0, 0, 0, 0]
    assert issues == []


def test_inconsistent_denominator_is_reported():
    a = ControlList("A", "a", load_rows=[row("D1", 8, 1, 5, "BR1")])
    b = ControlList("B", "b", load_rows=[row("D1", 8, 1, 6, "BR2")])
    loads, issues = build_dept_loads([a, b])
    assert issues[0].check == "dept_denominator_inconsistent"
    assert loads[0].keyed_in[7] == 6      # 取最大值，寧可低估負載


def test_inconsistent_function_is_reported():
    a = ControlList("A", "a", load_rows=[row("D1", 8, 1, 5, "BR1", fn="BSP")])
    b = ControlList("B", "b", load_rows=[row("D1", 8, 1, 5, "BR2", fn="PM")])
    loads, issues = build_dept_loads([a, b])
    d1 = loads[0]
    assert d1.function == "BSP"  # first seen wins
    assert any(issue.check == "dept_function_inconsistent" for issue in issues)
