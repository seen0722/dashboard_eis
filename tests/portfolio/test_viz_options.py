from src.portfolio.entities import Exception_, PlanVsActual, Project
from src.portfolio.model.load import DeptLoad
from src.portfolio.model.snapshot import build_snapshot
from src.portfolio.render.viz import options as O

TH = {"mp_slip_days": 60, "spare_capacity_pct": 85, "upcoming_weeks": 8, "timeline_months": 6}
TODAY = "2026-09-12"


def snap():
    a = Project(code="BR1", name="THORPE", stage="PVT", stage_cat="Execution", customer="Trimble", in_briefing=True, in_control_list=True, has_plan=True)
    a.dates.update({"kickoff": "2024-04-02", "pvt": "2026-09-08", "mp": "2026-10-20", "mp_orig": "2026-06-01"})
    a.pva = {"BU RD": PlanVsActual("BU RD", plan=[10] * 12, actual=[9] * 8 + [0] * 4), "PM": PlanVsActual("PM", plan=[1] * 12, actual=[1] * 8 + [0] * 4),
             "FU RD": PlanVsActual("FU RD", actual=[2] * 8 + [0] * 4)}
    b = Project(code="BR2", name="TOMY", stage="RFQ", stage_cat="RFQ / RFI", customer="Trimble", in_briefing=True)
    c = Project(code="BR3", name="Q11", stage="suspended", stage_cat="Suspended", customer="TBD", in_briefing=True)
    c.dates.update({"evt": "2026-09-20"})
    d = Project(code="BR4", name="AX200", stage="MP", stage_cat="MP", customer="Axelera", in_briefing=True)
    d.dates.update({"pvt": "2026-09-08", "mp": "2026-10-30"})
    e = Project(code="BR5", name="KOS", stage="Terminate", stage_cat="Terminated", customer="NA", in_briefing=True)
    f = Project(code="TR_KOS", name="TR_BU10_IPC_KOS", in_control_list=True)
    f.pva = {"BU RD": PlanVsActual("BU RD", actual=[3] * 8 + [0] * 4)}
    g = Project(code="BR6", name="N1X", stage="EVT", stage_cat="Execution", customer="Dell", in_briefing=True)
    g.dates.update({"pvt": "2026-09-02"})
    ex = [Exception_(1, "milestones_passed", "N1X PVT 2026-09-02 (+10d, stage EVT)", "milestones_passed", "briefing", ["BR6"], count=1)]
    loads = [DeptLoad("D1", "研發一課", "ME", keyed_in=[4] * 8 + [0] * 4, allocated=[4.0] * 8 + [0.0] * 4),
             DeptLoad("D2", "研發二課", "ME", keyed_in=[6] * 8 + [0] * 4, allocated=[3.0] * 8 + [0.0] * 4),
             DeptLoad("D3", "測試課", "QTC")]
    return build_snapshot("202609", 8, "20260907", TODAY, [a, b, c, d, e, f, g], loads, [10] * 8 + [0] * 4, ex, [], [])


def test_kpis_and_at_risk_reuse_existing_rules():
    k = {x["key"]: x for x in O.kpis(snap(), "en", TH)}
    assert k["total"]["value"] == 7 and k["total"]["sub"] == "6 in Briefing, 2 terminated or suspended"
    assert (k["rfq"]["value"], k["poc"]["value"], k["exec"]["value"], k["mp"]["value"]) == (1, 0, 2, 1)
    assert k["mp"]["sub"] == "1 MP, 0 sustain / EOP"
    assert k["risk"]["codes"] == ["BR6", "BR1"] and k["risk"]["value"] == 2 and k["risk"]["tone"] == "bad"   # passed ∪ mp slipped 141d
    assert O.late_codes(snap()) == {"BR6"}


def test_stage_donut_keeps_not_in_briefing_as_its_own_slice():
    ch = O.stage_donut(snap(), "en")
    data = ch.option["series"][0]["data"]
    assert [d["name"] for d in data] == ["RFQ / RFI  1", "Execution  2", "MP  1", "Terminated  1", "Suspended  1", "Not in Briefing  1"]
    assert sum(d["value"] for d in data) == 7 and ch.option["title"]["text"] == "7"
    assert ch.rows[-1] == ("Not in Briefing", 1, "14%")


def test_customer_bars_keep_blank_and_na_separate_and_fold_the_tail():
    ch = O.customer_bars(snap(), "en")
    assert dict(ch.rows) == {"Trimble": 2, "Not in Briefing": 1, "Axelera": 1, "Dell": 1, "NA": 1, "TBD": 1}
    assert ch.option["yAxis"]["data"][-1] == "Trimble"                      # 最大的在最上面
    top3 = O.customer_bars(snap(), "en", top=3)
    assert top3.rows == (("Trimble", 2), ("Axelera", 1), ("Dell", 1), ("Others", 3))


def test_gantt_rows_markers_and_customer_variants():
    ch = O.gantt(snap(), "en", TODAY, 6)
    assert ch.option["yAxis"]["data"] == ["TOMY", "AX200", "THORPE", "N1X"]      # 依里程碑先後；第一列在最上面
    assert [r[0] for r in ch.rows] == ["N1X", "THORPE", "AX200", "TOMY"]         # Q11（暫停）、KOS（結案）、不在 Briefing 的都不列
    marks = ch.option["series"][1]["data"]
    n1x = next(m for m in marks if m["label"]["formatter"] == "PVT 09/02")
    assert n1x["itemStyle"]["color"] == "#DC2626"                                 # 已過且階段未前進 → 紅
    thorpe = next(m for m in marks if m["label"]["formatter"] == "PVT 09/08")
    assert thorpe["itemStyle"]["color"] == "#2563EB"                              # 已過但不在 milestones_passed → 不標紅
    assert any(m["label"]["formatter"] == "RFQ, no dates yet" for m in marks)
    assert ch.option["series"][0]["renderItem"] == {"$fn": "ganttBar"}
    assert set(ch.variants) == {"Axelera", "Dell", "Trimble"}
    assert ch.variants["Trimble"]["yAxis"]["data"] == ["TOMY", "THORPE"]
    assert ch.note.startswith("Red marks a milestone")


def test_heatmap_by_function_never_shows_missing_months_as_zero():
    ch = O.load_heatmap(snap(), "en", 85)
    assert ch.id == "heat-function" and ch.option["yAxis"]["data"] == ["QTC", "ME"]
    cells, nodata = ch.option["series"][0]["data"], ch.option["series"][1]["data"]
    assert cells == [[m, 1, 70] for m in range(8)]                       # (4+3)/(4+6) = 70%
    assert len(nodata) == 16 and [9, 1, 0] in nodata and all(c[1] == 0 or c[0] >= 8 for c in nodata)
    assert ch.rows[0] == ("ME", *([70] * 8), None, None, None, None) and ch.rows[1] == ("QTC", *([None] * 12))
    pieces = ch.option["visualMap"]["pieces"]
    assert pieces[0]["lt"] == 85 and pieces[2]["gte"] == 95
    assert "not headcount" in ch.note


def test_heatmap_by_department_has_one_row_per_department():
    ch = O.load_heatmap(snap(), "en", 85, by="dept")
    assert ch.id == "heat-dept" and ch.option["yAxis"]["data"] == ["QTC  測試課", "ME  研發二課", "ME  研發一課"]


def test_forecast_capacity_series_and_budget_coverage():
    """2026-10-02 改為「人力去哪了」：長條拆成有 budget／沒 budget 兩段（加總＝實際），plan 只與有 budget 那段比。"""
    ch = O.forecast_capacity(snap(), "en")
    s = {x["name"]: x for x in ch.option["series"]}
    val = lambda d: d["value"] if isinstance(d, dict) else d  # noqa: E731
    assert s["Keyed-in BU headcount"]["data"] == [10] * 8 + [None] * 4
    assert [val(d) for d in s["Headcount, assumed same as Aug"]["data"]] == [None] * 7 + [10] * 5
    val = lambda d: d["value"] if isinstance(d, dict) else d  # noqa: E731
    withb, nob = s["With budget, 1 projects"], s["No budget, 1 projects"]
    assert withb["stack"] == nob["stack"] == "actual"
    assert [val(d) for d in withb["data"]] == [10.0] * 8 + [None] * 4               # THORPE：BU RD 9 + PM 1
    assert [val(d) for d in nob["data"]] == [3.0] * 8 + [None] * 4                  # TR_KOS：沒有 budget
    plan = s["Budget plan, BU RD + PM"]
    assert [val(d) for d in plan["data"]] == [11.0] * 12 and plan["symbol"] == "rect"
    assert plan["data"][11]["label"]["formatter"] == "Plan 11"                     # 拿掉圖例後，短橫線要自己說明是什麼
    assert nob["data"][7]["label"]["formatter"] == "No budget 3"                    # 最新月直接標在長條旁，不靠圖例
    assert "legend" not in ch.option
    carried = s["Headcount, assumed same as Aug"]
    assert carried["data"][11]["label"]["position"] == "top" and carried["data"][11]["label"]["align"] == "right"   # 長標籤放線上方、往左長，不被右緣切掉
    assert "endLabel" not in carried and carried["data"][11]["label"]["formatter"] == "Aug headcount 10, assumed unchanged" and carried["data"][11]["symbol"] != "none"   # endLabel 遇到前段 null 會算出 NaN（瀏覽器實測）
    assert ch.headline == "Aug: 13 of 10 in use, 3 over"
    assert ch.note == "Budget covers 1 / 2 projects, BU RD + PM only"
    assert ch.rows[7] == ("Aug", 10, 13.0, 10.0, 3.0, 11.0)
    assert ch.rows[8] == ("Sep", None, None, None, None, 11.0)


def test_forecast_headline_counts_what_is_left():
    s = snap(); s["capacity"] = [20] * 8 + [0] * 4
    assert O.forecast_capacity(s, "en").headline == "Aug: 13 of 20 in use, 7 left"


def test_pva_without_plan_draws_actual_only_and_says_so():
    ps = {p["code"]: p for p in snap()["projects"]}
    with_plan = O.pva(ps["BR1"], "BU RD", 8, "en", 0)
    assert with_plan.id == "pva-0-burd" and len(with_plan.option["series"]) == 2 and with_plan.note == ""
    no_plan = O.pva(ps["TR_KOS"], "BU RD", 8, "en", 5)
    assert no_plan.id == "pva-5-burd" and len(no_plan.option["series"]) == 1 and no_plan.note == "No budget plan for this group."
    assert no_plan.option["series"][0]["data"] == [3.0] * 8 + [None] * 4


def test_gantt_visual_fixes_from_browser_check():
    """2026-10-02 瀏覽器實測：symbol none 讓「no dates yet」標籤不見；Today 標籤壓到月份；375px 下整張圖擠成一團。"""
    ch = O.gantt(snap(), "en", TODAY, 6)
    nodate = next(m for m in ch.option["series"][1]["data"] if m["label"]["formatter"] == "RFQ, no dates yet")
    assert nodate["symbol"] != "none" and nodate["symbolSize"] > 0
    assert ch.option["series"][1]["markLine"]["label"]["position"] == "start"
    assert ch.min_width == 720 and O.load_heatmap(snap(), "en", 85).min_width == 560
    assert ch.option["grid"]["bottom"] >= 24 and O.load_heatmap(snap(), "en", 85).option["grid"]["right"] >= 16   # Today 標籤、Dec 不被裁掉


def test_customer_bars_put_projects_outside_briefing_in_their_own_bar():
    """Review 2026-10-02：「(blank) 14」其實全是不在 Briefing 的專案；圖上的標籤要指得回資料。"""
    rows = dict(O.customer_bars(snap(), "en").rows)
    assert rows.get("Not in Briefing") == 1 and "(blank)" not in rows
    s = snap(); next(p for p in s["projects"] if p["code"] == "BR2")["customer"] = "  "
    assert dict(O.customer_bars(s, "en").rows)["(blank)"] == 1                 # Briefing 內真正空白的仍標 (blank)


def test_gantt_tooltips_show_data_not_axis_internals():
    """Review：預設 tooltip 顯示「2026-09-01 08:00:00  15」（時區換算＋內部 y 索引）。"""
    s = snap(); next(p for p in s["projects"] if p["code"] == "BR6")["name"] = "N1X<b>"
    ch = O.gantt(s, "en", TODAY, 6)
    assert ch.option["useUTC"] is True
    marks = ch.option["series"][1]["data"]
    assert all("formatter" in m["tooltip"] for m in marks)
    assert any(m["tooltip"]["formatter"] == "N1X&lt;b&gt;: PVT 2026-09-02" for m in marks)
    assert any(m["tooltip"]["formatter"] == "TOMY: RFQ, no dates yet" for m in marks)


def _with_categories():
    s = snap()
    cat = {"BR1": ("Tablet", "ODM"), "BR2": ("Tablet", "ODM"), "BR3": ("NB", "EMS"), "BR4": ("Box PC", "JDM"), "BR5": ("Dock", "ODM"), "BR6": ("", "")}
    for p in s["projects"]:
        if p["code"] in cat:
            p["category"], p["biz_type"] = cat[p["code"]]
    return s


def test_category_donut_uses_the_briefing_column_and_names_what_others_holds():
    ch = O.category_donut(_with_categories(), "en", top=2)
    # (blank) 與 Not in Briefing 永遠單獨一塊，不參與排名、不會被併進 Others
    assert ch.id == "category" and ch.rows == (("Tablet", 2, "29%"), ("Box PC", 1, "14%"), ("Others", 2, "29%"), ("(blank)", 1, "14%"), ("Not in Briefing", 1, "14%"))
    assert ch.note == "Others: Dock, NB"
    assert sum(d["value"] for d in ch.option["series"][0]["data"]) == 7 and ch.option["title"]["text"] == "7"
    assert O.category_donut(_with_categories(), "en").note == ""                      # 類別不多於 top 時不併 Others


def test_type_donut_counts_odm_ems_jdm_and_keeps_blank_visible():
    ch = O.type_donut(_with_categories(), "en")
    assert ch.id == "type" and dict((r[0], r[1]) for r in ch.rows) == {"ODM": 3, "EMS": 1, "JDM": 1, "(blank)": 1, "Not in Briefing": 1}


def test_fu_plan_vs_actual_uses_one_denominator():
    s = snap(); a = next(p for p in s["projects"] if p["code"] == "BR1")
    a["pva"]["FU RD"]["plan"] = [3.0] * 12
    ch = O.fu_plan_actual(s, "en")
    series = {x["name"]: x["data"] for x in ch.option["series"]}
    val = lambda d: d["value"] if isinstance(d, dict) else d  # noqa: E731
    assert ch.id == "fu" and [val(d) for d in series["FU RD plan"]] == [3.0] * 12
    assert [val(d) for d in series["FU RD actual, same projects"]] == [2.0] * 8 + [None] * 4
    assert ch.note == "Plan covers 1 / 2 projects, FU RD only. All 2 projects: 2.0 FTE in Aug."
    assert ch.rows[7] == ("Aug", 3.0, 2.0, 2.0)
    assert O.fu_plan_actual(snap(), "en").note.startswith("Plan covers 0 / 2 projects, FU RD only")


def test_forecast_tooltip_tells_series_apart():
    """瀏覽器實測：tooltip 裡 plan／人數／推算人數都是同一顆黑點；8 月 209 出現兩次；數字 141.63 與標籤 142 不一致。"""
    ch = O.forecast_capacity(snap(), "en")
    names = [x["name"] for x in ch.option["series"]]
    tip = ch.option["tooltip"]
    assert tip["formatter"] == {"$fn": "axisTip", "args": [["bar", "bar", "mark", "line", "dashed"], {"4": 3}, 1]}
    assert names[4] == "Headcount, assumed same as Aug" and names[3] == "Keyed-in BU headcount"     # 推算線在實線有值的月份不列
    plan = next(x for x in ch.option["series"] if x["name"] == "Budget plan, BU RD + PM")
    assert plan["itemStyle"]["color"] != next(x for x in ch.option["series"] if x["name"] == "Keyed-in BU headcount")["itemStyle"]["color"]


def test_plan_vs_actual_charts_share_one_design_language():
    """2026-10-02：Forecast、FU、單案 PVA 統一：actual 長條、plan 紫色短橫、無圖例、tooltip 圖示與圖形一致。"""
    from src.portfolio.render.viz import tokens as T
    s = snap(); a = next(p for p in s["projects"] if p["code"] == "BR1"); a["pva"]["FU RD"]["plan"] = [3.0] * 12
    val = lambda d: d["value"] if isinstance(d, dict) else d  # noqa: E731
    fu = O.fu_plan_actual(s, "en")
    pva = O.pva(next(p for p in s["projects"] if p["code"] == "BR1"), "BU RD", 8, "en", 0)
    for ch in (O.forecast_capacity(s, "en"), fu, pva):
        assert "legend" not in ch.option, ch.id
        assert ch.option["tooltip"]["formatter"]["$fn"] == "axisTip", ch.id
        plans = [x for x in ch.option["series"] if x["itemStyle"]["color"] == T.PLAN_MARK]
        assert len(plans) == 1 and plans[0]["symbol"] == "rect" and plans[0]["lineStyle"] == {"width": 0}, ch.id
    fs = {x["name"]: x for x in fu.option["series"]}
    assert fs["FU RD actual, same projects"]["data"][7]["label"]["formatter"] == "Actual 2"
    assert fs["FU RD plan"]["data"][11]["label"]["formatter"] == "Plan 3"
    assert [val(d) for d in fs["FU RD plan"]["data"]] == [3.0] * 12
    assert fu.headline == "Aug: 2 of 3 planned, 67%"
    assert fu.option["tooltip"]["formatter"]["args"][0] == ["bar", "mark"]



def test_paired_charts_use_one_title_and_headline_pattern():
    """2026-10-02：並排的兩張卡片標題、結論、註記同一句型。"""
    s = snap(); next(p for p in s["projects"] if p["code"] == "BR1")["pva"]["FU RD"]["plan"] = [3.0] * 12
    bu, fu = O.forecast_capacity(s, "en"), O.fu_plan_actual(s, "en")
    assert (bu.title, fu.title) == ("BU RD + PM: actual vs headcount", "FU RD: actual vs plan")
    assert bu.headline.startswith("Aug: 13 of 10 ") and fu.headline.startswith("Aug: 2 of 3 ")
    assert bu.note.endswith("projects, BU RD + PM only") and fu.note.startswith("Plan covers 1 / 2 projects, FU RD only")
