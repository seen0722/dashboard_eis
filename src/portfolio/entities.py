"""跨層共用型別。所有欄位都可 asdict() 成純 JSON。"""
from dataclasses import dataclass, field

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DATE_KEYS = ("kickoff", "evt", "dvt", "pvt", "mp", "mp_orig")
ROLES = ("FU RD", "BU RD", "PM")


def empty_months() -> list[float]:
    return [0.0] * 12


def empty_dates() -> dict[str, str | None]:
    return {k: None for k in DATE_KEYS}


@dataclass
class Issue:
    level: str          # "decide" | "track" | "ok"
    check: str          # 機器可讀的檢查代號，例如 "budget_missing"
    detail: str         # 人讀得懂的描述
    source: str         # 資料來源
    code: str | None = None


@dataclass
class MasterProject:
    code: str
    name: str
    group: str = ""
    family: str = ""
    active: bool = True


@dataclass
class BriefingRow:
    snap: str                       # "YYYYMMDD"
    name: str
    code: str | None = None
    stage: str = ""
    customer: str = ""
    product: str = ""
    dates: dict[str, str | None] = field(default_factory=empty_dates)
    updated: str | None = None      # 資料更新日
    status_text: str = ""


@dataclass
class MonthlyFTE:
    name: str
    group: str
    fte: list[float] = field(default_factory=empty_months)
    ntd: list[float] = field(default_factory=empty_months)


@dataclass
class PlanVsActual:
    role: str
    plan: list[float] = field(default_factory=empty_months)
    actual: list[float] = field(default_factory=empty_months)
    ntd: list[float] = field(default_factory=empty_months)


@dataclass
class Task:
    month: int                      # 1..12
    side: str                       # "BU" | "FU"
    function: str
    dept: str                       # 部門名最後一段
    fte: float
    description: str                # 已遮罩


@dataclass
class DeptLoadRow:
    dept_code: str
    dept_name: str
    function: str
    month: int
    allocated: float                # 主管填入人力（單一專案）
    keyed_in: int                   # 單位TotalKeyIn人數
    code: str | None = None


@dataclass
class ControlList:
    label: str                      # 檔名裡的專案名
    path: str
    codes: list[str] = field(default_factory=list)
    pva: dict[str, PlanVsActual] = field(default_factory=dict)
    tasks: list[Task] = field(default_factory=list)
    load_rows: list[DeptLoadRow] = field(default_factory=list)


@dataclass
class Project:
    code: str                       # 真代碼，或解析失敗時 "NAME:<normalized>"
    name: str
    group: str = ""
    family: str = ""
    customer: str = ""
    product: str = ""
    stage: str = ""
    stage_cat: str = ""
    dates: dict[str, str | None] = field(default_factory=empty_dates)
    in_briefing: bool = False
    in_control_list: bool = False
    has_plan: bool = False
    fte: list[float] = field(default_factory=empty_months)
    ntd: list[float] = field(default_factory=empty_months)
    pva: dict[str, PlanVsActual] = field(default_factory=dict)
    tasks: list[Task] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)   # [{snap, stage, mp, dvt}]


@dataclass
class Exception_:
    rank: int
    title: str
    evidence: str
    ask: str
    source: str
    codes: list[str] = field(default_factory=list)


@dataclass
class HealthRow:
    level: str
    check: str
    label: str
    count: int
    names: list[str]
    source: str
