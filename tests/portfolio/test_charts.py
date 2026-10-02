import datetime as dt
from dataclasses import asdict
from src.portfolio.entities import PlanVsActual, Project
from src.portfolio.render.charts import _add_months, _sum, carry_forward


def test_add_months_rolls_the_year():
    assert _add_months(dt.date(2026, 11, 15), 3) == dt.date(2027, 2, 1)


def test_carry_forward_only_changes_months_after_latest():
    capacity = [12] * 8 + [0] * 4
    assert carry_forward(capacity, 8) == [12] * 12
    assert capacity == [12] * 8 + [0] * 4                                    # 不動呼叫端的 snapshot 值


def test_sum_respects_only_plan():
    a = Project(code="A", name="A", in_control_list=True, has_plan=True); a.pva = {"BU RD": PlanVsActual("BU RD", plan=[1] * 12)}
    b = Project(code="B", name="B", in_control_list=True); b.pva = {"BU RD": PlanVsActual("BU RD", plan=[5] * 12)}
    ps = [asdict(a), asdict(b)]
    assert _sum(ps, "BU RD", "plan", only_plan=True)[0] == 1 and _sum(ps, "BU RD", "plan")[0] == 6
