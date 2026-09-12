"""部門 × 月負載 = Σ各專案主管填入人力 ÷ 該部門當月填報人數。分母來自月分頁，跨專案應一致。"""
from __future__ import annotations
from dataclasses import dataclass, field
from ..entities import ControlList, Issue, empty_months


@dataclass
class DeptLoad:
    dept_code: str
    dept_name: str
    function: str
    keyed_in: list[int] = field(default_factory=lambda: [0] * 12)
    allocated: list[float] = field(default_factory=empty_months)
    util: list[int | None] = field(default_factory=lambda: [None] * 12)


def _short(name: str) -> str:
    parts = name.split("-")
    return "-".join(parts[1:]) if len(parts) > 1 else name


def build_dept_loads(control_lists: list[ControlList]) -> tuple[list[DeptLoad], list[Issue]]:
    loads: dict[str, DeptLoad] = {}
    seen: dict[tuple[str, int], set[int]] = {}
    seen_functions: dict[str, set[str]] = {}
    for cl in control_lists:
        for r in cl.load_rows:
            d = loads.setdefault(r.dept_code, DeptLoad(r.dept_code, _short(r.dept_name), r.function))
            m = r.month - 1
            d.allocated[m] = round(d.allocated[m] + r.allocated, 4)
            d.keyed_in[m] = max(d.keyed_in[m], r.keyed_in)
            seen.setdefault((r.dept_code, r.month), set()).add(r.keyed_in)
            seen_functions.setdefault(r.dept_code, set()).add(r.function)
    issues = [Issue("track", "dept_denominator_inconsistent", f"{code} month {month}: keyed-in headcount differs across files {sorted(v)}", "Control List")
              for (code, month), v in sorted(seen.items()) if len(v) > 1]
    issues.extend([Issue("track", "dept_function_inconsistent", f"{code}: function differs across files {sorted(v)}; using {loads[code].function}", "Control List")
                   for code, v in sorted(seen_functions.items()) if len(v) > 1])
    for d in loads.values():
        d.util = [round(d.allocated[m] / d.keyed_in[m] * 100) if d.keyed_in[m] else None for m in range(12)]
    return sorted(loads.values(), key=lambda d: (d.function, d.dept_code)), issues


def capacity_by_month(loads: list[DeptLoad]) -> list[int]:
    return [sum(d.keyed_in[m] for d in loads) for m in range(12)]
