"""組頁。所有文字走 t()，所有數字來自 snapshot dict。"""
from __future__ import annotations
import datetime as dt
from html import escape as e
from ..entities import INACTIVE, MONTHS
from .css import CSS
from .strings import t
from .viz.dash import at_risk_html, card, kpi_cards, milestone_table, safe_chart_card, side_nav, status_html
from .viz.embed import chart_html, scripts
from .viz.options import category_donut, composition, customer_bars, forecast_capacity, fu_plan_actual, gantt, kpis, late_codes, load_heatmap, pva, stage_donut, type_donut

STAGE_KEYS = [("RFQ / RFI", "stage_rfq"), ("POC", "stage_poc"), ("Execution", "stage_exec"), ("MP", "stage_mp"), ("Sustain / EOP", "stage_sustain"), ("Terminated", "stage_terminated"), ("Suspended", "stage_suspended")]


def _days(a: str, b: str) -> int:
    return (dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days


def _title_block(m: dict, lang: str, n_cl: int, latest_month: int) -> str:
    ym = f"{m['report_month'][:4]}-{m['report_month'][4:]}"
    rows = [(t(lang, "tb_report"), ym), (t(lang, "tb_data"), t(lang, "tb_data_v", start=f"{m['report_month'][:4]}-01", end=f"{m['report_month'][:4]}-{latest_month:02d}", n=n_cl)),
            (t(lang, "tb_snap"), t(lang, "tb_snap_v", date=f"{m['snap_date'][:4]}-{m['snap_date'][4:6]}-{m['snap_date'][6:]}", rev=m.get("snap_rev", "?"))),
            (t(lang, "tb_gen"), t(lang, "tb_gen_v", date=m["generated"], ver=m["version"]))]
    return '<div class="tb">' + "".join(f"<div><span>{e(k)}</span><span>{e(v)}</span></div>" for k, v in rows) + "</div>"


def _susp_twin_line(tw: dict, lang: str, mon: str) -> str:
    cl = t(lang, "ex_susp_twin_cl") if tw["twin_in_cl"] else ""
    cat = t(lang, {"Terminated": "cat_terminated", "Suspended": "cat_suspended"}.get(tw.get("cat"), "cat_inactive"))
    return t(lang, "ex_susp_twin_line", name=tw["name"], code=tw["code"], cat=cat, twin=tw["twin"], twin_code=tw["twin_code"],
              fte=f"{tw['twin_fte']:.2f}", mon=mon, cl=cl)


def _suspended_charging_body(x: dict, lang: str, lm: int) -> str:
    """例外 2 的細節，只列需要決定的：先亮橘色的「第二身分」，再列仍掛帳（Terminated 掛帳是異常，標註分類）、
    暫停但已無人力（會重啟嗎？）、暫停且全年無人力。已結案且人力為零是正常收尾，不列（總數在 stage strip）。
    任何一段沒資料就整段省略。"""
    extra = x.get("extra", {})
    twins, charging = extra.get("twin_list", []), extra.get("charging_list", [])
    wound, zero = extra.get("wound_list", []), extra.get("zero_list", [])
    mon = MONTHS[lm - 1]
    blocks = []
    if twins:
        lines = "".join(f'<div class="sig">{e(_susp_twin_line(tw, lang, mon))}</div>' for tw in twins)
        blocks.append(f'<div class="body"><b class="sig">{e(t(lang, "ex_susp_twin_h"))}</b>{lines}</div>')
    if charging:
        lines = "".join(f'<div>{e(f"{c["name"]} {c["fte"]:.1f} FTE" + (f" ({t(lang, "cat_terminated")})" if c.get("cat") == "Terminated" else ""))}</div>' for c in charging)
        blocks.append(f'<div class="body"><b>{e(t(lang, "ex_susp_charging_h", mon=mon))}</b>{lines}</div>')
    def wound_lines(ws):
        return "".join(f'<div>{e(t(lang, "ex_susp_wound_line", name=w["name"], peak=f"{w["peak"]:.1f}", peak_month=w["peak_month"], zero_since=w["zero_since"]))}</div>' for w in ws)
    w_susp = [w for w in wound if w.get("cat") != "Terminated"]
    if w_susp:
        since = ", ".join(sorted({w["zero_since"] for w in w_susp}))
        blocks.append(f'<div class="body"><b>{e(t(lang, "ex_susp_wound_susp_h", since=since))}</b>{wound_lines(w_susp)}</div>')
    z_susp = [z for z in zero if z.get("cat") != "Terminated"]
    if z_susp:
        blocks.append(f'<div class="body"><b>{e(t(lang, "ex_susp_zero_h", n=len(z_susp)))}</b> {e(", ".join(z["name"] for z in z_susp))}</div>')
    return "".join(blocks) or f'<div class="body">{e(t(lang, "none"))}</div>'


def _exceptions(snap: dict, lang: str, th: dict) -> str:
    out = []
    lm = snap["meta"]["latest_month"]
    for x in snap["exceptions"]:
        k = x["title"]; kw = {"n": x["count"], "days": th["mp_slip_days"], "pct": th["spare_capacity_pct"], "full": x.get("ask_data", "")}
        kw.update(x.get("extra", {}))
        # 2026-10-01 之前 ingest 的快照沒有 terminated/suspended/briefed：用不分類的標題，不要 KeyError（曾讓 /ui 總覽 500）
        if k == "suspended_charging" and "suspended" not in kw:
            k = "suspended_charging_legacy"
        src_kw = {"date": f"{snap['meta']['snap_date'][4:6]}/{snap['meta']['snap_date'][6:]}"}
        body = _suspended_charging_body(x, lang, lm) if x["title"] == "suspended_charging" else f'<div class="body">{e(x["evidence"]) or e(t(lang, "none"))}</div>'
        out.append(f'<li><div class="n">{x["rank"]}</div><div><b>{e(t(lang, f"ex_{k}_title", **kw))}</b>'
                   f'{body}'
                   f'<div class="ask"><em>{e(t(lang, "decision_needed"))}</em> {e(t(lang, f"ex_{k}_ask", **kw))}</div>'
                   f'<div class="src">{e(t(lang, "source"))} {e(t(lang, f"src_{x["source"]}", **src_kw))}</div></div></li>')
    return f'<ol class="ex">{"".join(out)}</ol>'


def _stage_strip(snap: dict, lang: str, latest_month: int) -> str:
    ps = [p for p in snap["projects"] if p["in_briefing"]]
    cells = [f'<div><b class="{"sig" if cat in INACTIVE else ""}">{sum(1 for p in ps if p["stage_cat"] == cat)}</b><span>{e(t(lang, key))}</span></div>' for cat, key in STAGE_KEYS]
    total = sum(p["fte"][latest_month - 1] for p in snap["projects"])
    cells.append(f'<div><b>{total:.1f}</b><span>{e(t(lang, "stage_fte", mon=MONTHS[latest_month - 1]))}</span></div>')
    return f'<div class="stages">{"".join(cells)}</div>'


def _upcoming_rows(snap: dict, today: str, weeks: int, late: set[str]) -> list[dict]:
    """與舊版同一個視窗：過去 7 天到未來 weeks 週；只看 Briefing 內、非結案／暫停的專案。"""
    rows = []
    for p in snap["projects"]:
        if not p["in_briefing"] or p["stage_cat"] in INACTIVE:
            continue
        for k in ("evt", "dvt", "pvt", "mp"):
            d = p["dates"][k]
            if d and -7 <= _days(d, today) <= weeks * 7:
                rows.append({"date": d, "name": p["name"], "code": p["code"], "customer": p["customer"], "milestone": k,
                             "days_left": _days(d, today), "late": p["code"] in late})
    return sorted(rows, key=lambda r: (r["date"], r["name"]))


def _health(snap: dict, lang: str) -> str:
    rows = "".join(f'<tr><td><span class="dot {h["level"][0]}"></span>{e(t(lang, "lv_" + h["level"]))}</td><td>{e(t(lang, "hc_" + h["check"]))}</td>'
                   f'<td class="num {"sig" if h["level"] == "decide" and h["count"] else ""}">{h["count"]}</td>'
                   f'<td style="white-space:normal;max-width:60ch" class="dim">{e(", ".join(h["names"]))}</td><td class="dim">{e(t(lang, "hs_" + h["source"]))}</td></tr>' for h in snap["health"])
    return (f'<table><thead><tr><th>{e(t(lang, "col_level"))}</th><th>{e(t(lang, "col_check"))}</th><th class="num">{e(t(lang, "col_count"))}</th>'
            f'<th>{e(t(lang, "col_projects"))}</th><th>{e(t(lang, "col_source"))}</th></tr></thead><tbody>{rows}</tbody></table>')


def _appendix_one(p: dict, lang: str, today: str, latest_month: int, i: int) -> str:
    ms = []
    for k in ("kickoff", "evt", "dvt", "pvt", "mp"):
        d = p["dates"][k]
        sub = (t(lang, "days_ahead", d=_days(d, today)) if _days(d, today) >= 0 else t(lang, "days_ago", d=-_days(d, today))) if d else (t(lang, "not_filled") if p["in_briefing"] else t(lang, "not_in_briefing"))
        ms.append(f'<div><small>{e(t(lang, "ms_" + k))}</small><b>{e(d or "–")}</b><small>{e(sub)}</small></div>')
    if not p.get("pva"):
        body = f'<p class="dim">{e(t(lang, "no_control_list"))}</p>'
    else:
        cards = []
        for role in ("BU RD", "FU RD", "PM"):
            v = p["pva"].get(role) or {"plan": [0] * 12, "actual": [0] * 12}
            plan, act = sum(v["plan"]), sum(v["actual"][:latest_month])
            cards.append(f'<div><h4>{role}</h4><div class="s">{e(t(lang, "pva_line", plan=f"{plan:.1f}", missing="" if plan else t(lang, "pva_missing"), mon=MONTHS[latest_month - 1], actual=f"{act:.1f}"))}</div>{chart_html(pva(p, role, latest_month, lang, i), lang)}</div>')
        by_m: dict[int, list] = {}
        for task in p["tasks"]:
            by_m.setdefault(task["month"], []).append(task)
        dets = []
        for m in sorted(by_m, reverse=True):
            ts = sorted(by_m[m], key=lambda x: -x["fte"]); bu = sum(1 for x in ts if x["side"] == "BU"); fu = len(ts) - bu
            trs = "".join(f'<tr><td>{x["side"]}</td><td>{e(x["function"])}</td><td>{e(x["dept"])}</td><td class="num">{x["fte"]:.2f}</td><td class="desc">{e(x["description"])}</td></tr>' for x in ts)
            dets.append(f'<details><summary data-expand="{e(t(lang, "expand"))}" data-collapse="{e(t(lang, "collapse"))}"><span>{e(t(lang, "task_summary", mon=MONTHS[m - 1], bu=bu, fu=fu, fte=f"{sum(x["fte"] for x in ts):.1f}"))}</span></summary>'
                        f'<div class="wide"><table><thead><tr><th>{e(t(lang, "col_side"))}</th><th>{e(t(lang, "col_function"))}</th><th>{e(t(lang, "col_dept"))}</th><th class="num">{e(t(lang, "col_fte"))}</th><th>{e(t(lang, "col_task"))}</th></tr></thead><tbody>{trs}</tbody></table></div></details>')
        body = f'<div class="pva">{"".join(cards)}</div><h3 style="font-size:15px;margin:26px 0 6px">{e(t(lang, "s_tasks"))}</h3>{"".join(dets)}'
    # biz_type（JDM/ODM/EMS）來自 2026-09 起的 Briefing Type 欄；product 在新版已是 Category + Panel Size，不再重複列。舊版面為空就略過。
    meta = "  ".join(x for x in (p["code"] if not p["code"].startswith("NAME:") else "", p["customer"], p.get("biz_type", ""), p["product"], p["group"]) if x)
    return f'<div class="proj" data-idx="{i}"><div class="dim">{e(meta)}</div><div class="ms">{"".join(ms)}</div>{body}</div>'


def _overview(snap: dict, lang: str, today: str, th: dict, late: set[str]) -> str:
    weeks, months = th["upcoming_weeks"], th["timeline_months"]
    rows = _upcoming_rows(snap, today, weeks, late)
    ms = milestone_table(rows, lang) if rows else f'<p class="note">{e(t(lang, "none"))}</p>'
    strip = kpi_cards([k for k in kpis(snap, lang, th) if k["key"] != "risk"], cls="strip")
    return (status_html(snap, lang, th, decisions_href="#decisions") + strip
            + f'<div class="grid-2">{safe_chart_card(t(lang, "v_c_forecast"), lambda: forecast_capacity(snap, lang), lang)}'
            + f'{safe_chart_card(t(lang, "v_c_fu"), lambda: fu_plan_actual(snap, lang), lang)}</div>'
            + safe_chart_card(t(lang, "v_c_composition"), lambda: composition(snap, lang), lang)
            + f'<div class="grid-2">{safe_chart_card(t(lang, "v_c_customer"), lambda: customer_bars(snap, lang), lang)}'
            + f'{card(t(lang, "v_c_milestones", weeks=weeks), ms)}</div>'
            + safe_chart_card(t(lang, "v_c_gantt", months=months), lambda: gantt(snap, lang, today, months), lang)
            + safe_chart_card(t(lang, "v_c_heat"), lambda: load_heatmap(snap, lang, th["spare_capacity_pct"]), lang))


def render_page(snap: dict, lang: str, today: str, th: dict, echarts: str = "inline") -> str:
    m = snap["meta"]; lm = m["latest_month"]
    if lm < 1:
        raise ValueError("no manpower month in snapshot")   # 整頁都以「最新月」定位，沒有它不該畫出半張報表
    ps = snap["projects"]; cl = [p for p in ps if p["in_control_list"]]
    late = late_codes(snap)
    order = sorted(range(len(ps)), key=lambda i: ps[i]["name"].casefold())   # 附錄依專案名稱字母排序（需求方 2026-09-30）
    options = "".join(f'<option value="{i}">{e(ps[i]["name"])}{", " + e(ps[i]["stage"]) if ps[i]["stage"] else ""}</option>' for i in order)
    appendix = "".join(_appendix_one(ps[i], lang, today, lm, i) for i in order)
    ym = f"{m['report_month'][:4]}-{m['report_month'][4:]}"
    links = "".join(f'<a href="#{a}">{e(t(lang, k))}</a>' for a, k in (("overview", "v_nav_overview"), ("decisions", "v_nav_decisions"),
                                                                          ("health", "v_nav_health"), ("appendix", "v_nav_appendix")))
    side = side_nav(f'<a class="brand" href="#overview">{e(t(lang, "h1"))}</a>', links, t(lang, "v_menu"), label=t(lang, "h1"))
    return f"""<!DOCTYPE html><html lang="{t(lang, "html_lang")}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(t(lang, "doc_title", ym=ym))}</title><style>{CSS}</style></head><body><div class="app">{side}<main class="main">
<header><div><h1>{e(t(lang, "h1"))}</h1><p>{e(t(lang, "intro"))}</p></div>{_title_block(m, lang, len(cl), lm)}</header>
<section id="overview">{_overview(snap, lang, today, th, late)}</section>
<section id="decisions"><h2>{e(t(lang, "s_decisions"))}</h2><p class="lead">{e(t(lang, "s_decisions_lead"))}</p>{at_risk_html(snap, lang, th)}<div class="card">{_exceptions(snap, lang, th)}</div></section>
<section id="health"><h2>{e(t(lang, "s_health"))}</h2><p class="lead">{e(t(lang, "s_health_lead"))}</p><div class="card"><div class="wide">{_health(snap, lang)}</div></div></section>
<section id="appendix"><h2>{e(t(lang, "s_appendix"))}</h2><p class="lead">{e(t(lang, "s_appendix_lead"))}</p><select id="pick">{options}</select><div id="projects">{appendix}</div></section>
<footer><p>{e(t(lang, "foot_1"))}</p><p>{e(t(lang, "foot_2"))}</p><p>{e(t(lang, "foot_3"))}</p></footer>
</main></div>{scripts(echarts)}
<script>(function(){{var s=document.getElementById('pick'),ps=document.querySelectorAll('#projects .proj');function show(i){{ps.forEach(function(p){{p.style.display=p.dataset.idx===String(i)?'':'none';}});if(window.eisCharts)window.eisCharts.init(document.getElementById('projects'));}}s.addEventListener('change',function(){{show(s.value);}});show(s.value);}})();</script>
</body></html>"""


# 給 src/eis_mcp/web 重用的片段（底線版本仍是本模組內部的名字）。
exceptions_html, stage_strip_html, health_html, project_card_html = _exceptions, _stage_strip, _health, _appendix_one
