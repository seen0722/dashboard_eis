"""單案頁與專案列表共用的計算（2026-10-03 review：狀態卡、MP 漂移、任務彙總、列表的趨勢與達成率）。"""
from src.portfolio.render.viz.project import mp_drift, next_milestone, plan_to_date, sparkline_svg, task_groups


def proj(**kw):
    p = {"code": "BR1", "name": "AX100", "stage": "PVT", "stage_cat": "Execution", "in_briefing": True,
         "dates": {"kickoff": "2025-03-03", "evt": None, "dvt": "2026-03-18", "pvt": "2026-05-11", "mp": "2026-10-31", "mp_orig": "2026-06-30"},
         "fte": [3.0, 2.0, 1.0, 0, 0, 0, 0, 1.2, 0, 0, 0, 0], "pva": {}, "tasks": [], "history": []}
    p.update(kw)
    return p


def test_next_milestone_is_the_first_date_on_or_after_today():
    assert next_milestone(proj(), "2026-09-29") == {"key": "mp", "date": "2026-10-31", "days": 32}
    assert next_milestone(proj(), "2026-11-01") is None


def test_plan_to_date_sums_every_role_through_the_latest_month():
    pva = {"BU RD": {"plan": [2.0] * 12, "actual": [3.0] * 12}, "PM": {"plan": [1.0] * 12, "actual": [0.5] * 12}}
    assert plan_to_date(proj(pva=pva), 8) == (24.0, 28.0)


def test_plan_to_date_is_unknown_without_a_plan_not_zero():
    """AGENTS.md 第一守則：沒有 Control List 不是 0%。"""
    assert plan_to_date(proj(), 8) is None
    assert plan_to_date(proj(pva={"PM": {"plan": [0.0] * 12, "actual": [1.0] * 12}}), 8) is None


def test_sparkline_draws_the_keyed_in_months_only():
    svg = sparkline_svg([3.0, 2.0, 1.0, 0, 0, 0, 0, 1.2, 9, 9, 9, 9], 8)
    assert svg.startswith("<svg") and svg.count(" ") > 0 and "polyline" in svg
    assert len(svg.split('points="')[1].split('"')[0].split()) == 8
    assert "<title>Jan 3.0, Feb 2.0, Mar 1.0, Apr 0.0, May 0.0, Jun 0.0, Jul 0.0, Aug 1.2</title>" in svg


def test_sparkline_of_all_zero_is_a_flat_line_not_an_error():
    assert "polyline" in sparkline_svg([0] * 12, 8)


def test_task_groups_sum_by_side_and_function_and_merge_identical_text():
    ts = [{"month": 8, "side": "FU", "function": "SW", "dept": "軟體一課", "fte": 0.10, "description": "SW MR."},
          {"month": 8, "side": "FU", "function": "SW", "dept": "軟體二課", "fte": 0.05, "description": "SW MR."},
          {"month": 8, "side": "FU", "function": "RF", "dept": "射頻一課", "fte": 0.02, "description": "Factory bug debug"},
          {"month": 8, "side": "BU", "function": "BSP", "dept": "研發三部", "fte": 3.10, "description": "Thorpe SW maintenance release."},
          {"month": 7, "side": "BU", "function": "BSP", "dept": "研發三部", "fte": 9.0, "description": "old month"}]
    g = task_groups(ts, 8)
    assert [(x["side"], x["function"], round(x["fte"], 2), x["depts"]) for x in g] == [("BU", "BSP", 3.1, 1), ("FU", "SW", 0.15, 2), ("FU", "RF", 0.02, 1)]
    sw = g[1]["items"]
    assert len(sw) == 1 and sw[0]["text"] == "SW MR." and sw[0]["depts"] == ["軟體一課", "軟體二課"] and round(sw[0]["fte"], 2) == 0.15


def test_task_groups_keep_blank_descriptions_visible():
    ts = [{"month": 8, "side": "BU", "function": "PM", "dept": "一課", "fte": 1.0, "description": ""}]
    assert task_groups(ts, 8)[0]["items"][0]["text"] == ""


def test_mp_drift_steps_through_each_briefing_and_marks_the_original_date():
    hist = [{"snap": "20260629", "stage": "DVT", "mp": "2026-07-15"}, {"snap": "20260706", "stage": "DVT", "mp": "2026-07-15"},
            {"snap": "20260727", "stage": "PVT", "mp": "2026-08-31"}, {"snap": "20260929", "stage": "PVT", "mp": "2026-10-31"}]
    ch = mp_drift(proj(history=hist), "en")
    s = ch.option["series"][0]
    assert s["step"] == "end" and [d["value"][1] for d in s["data"]] == ["2026-07-15", "2026-07-15", "2026-08-31", "2026-10-31"]
    assert ch.option["series"][0]["markLine"]["data"][0]["yAxis"] == "2026-06-30"
    assert ch.headers == ("Briefing", "Stage", "MP", "Change")
    assert [r[3] for r in ch.rows] == ["–", "0 days", "+47 days", "+61 days"]
    assert ch.headline == "Now 2026-10-31, +123 days vs original 2026-06-30"


def test_mp_drift_needs_at_least_one_dated_briefing():
    assert mp_drift(proj(history=[]), "en") is None
    assert mp_drift(proj(history=[{"snap": "20260629", "stage": "RFQ", "mp": None}]), "en") is None


def test_pva_line_compares_the_same_months():
    """review：「budget 101.0, actual through Aug 97.8」是全年預算對 8 個月實際，期間不一致。"""
    from src.portfolio.render.viz.project import pva_line
    v = {"plan": [2.0] * 12, "actual": [3.0] * 12}
    assert pva_line(v, 8, "en") == "Jan–Aug plan 16.0, actual 24.0; full-year plan 24.0"
    assert pva_line({"plan": [0.0] * 12, "actual": [1.0] * 12}, 8, "en") == "Jan–Aug plan not filled, actual 8.0"


def test_mp_drift_says_which_briefings_it_covers():
    """THORPE：+291 天全發生在留存的 Briefing 之前，圖上是一條平線 → 必須寫明涵蓋期間，免得讀成「從沒延後」。"""
    hist = [{"snap": "20260629", "stage": "PVT", "mp": "2026-07-31"}, {"snap": "20260929", "stage": "PVT", "mp": "2026-07-31"}]
    ch = mp_drift(proj(history=hist), "en")
    assert ch.note == "Briefings on file: 2026-06-29 to 2026-09-29. Changes before that are not shown."
    last = ch.option["series"][0]["data"][-1]["label"]
    assert last["position"] == "top" and last["align"] == "right"                       # 點的上方、往左延伸：不被右邊界切掉，也不壓在平線上
