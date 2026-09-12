"""組頁。所有文字走 t()，所有數字來自 snapshot dict。"""
from __future__ import annotations
import datetime as dt
from html import escape as e
from ..entities import MONTHS
from .css import CSS
from .charts import timeline_svg, capacity_svg, pva_svg
from .strings import t

STAGE_KEYS = [("RFQ / RFI", "stage_rfq"), ("POC", "stage_poc"), ("Execution", "stage_exec"), ("MP", "stage_mp"), ("Sustain / EOP", "stage_sustain"), ("Suspended", "stage_suspended")]


def _days(a: str, b: str) -> int:
    return (dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days


def _title_block(m: dict, lang: str, n_cl: int, latest_month: int) -> str:
    ym = f"{m['report_month'][:4]}-{m['report_month'][4:]}"
    rows = [(t(lang, "tb_report"), ym), (t(lang, "tb_data"), t(lang, "tb_data_v", start=f"{m['report_month'][:4]}-01", end=f"{m['report_month'][:4]}-{latest_month:02d}", n=n_cl)),
            (t(lang, "tb_snap"), t(lang, "tb_snap_v", date=f"{m['snap_date'][:4]}-{m['snap_date'][4:6]}-{m['snap_date'][6:]}", rev=m.get("snap_rev", "?"))),
            (t(lang, "tb_gen"), t(lang, "tb_gen_v", date=m["generated"], ver=m["version"]))]
    return '<div class="tb">' + "".join(f"<div><span>{e(k)}</span><span>{e(v)}</span></div>" for k, v in rows) + "</div>"


def _exceptions(snap: dict, lang: str, th: dict) -> str:
    out = []
    for x in snap["exceptions"]:
        k = x["title"]; kw = {"n": x["count"], "days": th["mp_slip_days"], "pct": th["spare_capacity_pct"], "full": x.get("ask_data", "")}
        kw.update(x.get("extra", {}))
        src_kw = {"date": f"{snap['meta']['snap_date'][4:6]}/{snap['meta']['snap_date'][6:]}"}
        out.append(f'<li><div class="n">{x["rank"]}</div><div><b>{e(t(lang, f"ex_{k}_title", **kw))}</b>'
                   f'<div class="body">{e(x["evidence"]) or e(t(lang, "none"))}</div>'
                   f'<div class="ask"><em>{e(t(lang, "decision_needed"))}</em> {e(t(lang, f"ex_{k}_ask", **kw))}</div>'
                   f'<div class="src">{e(t(lang, "source"))} {e(t(lang, f"src_{x["source"]}", **src_kw))}</div></div></li>')
    return f'<ol class="ex">{"".join(out)}</ol>'


def _stage_strip(snap: dict, lang: str, latest_month: int) -> str:
    ps = [p for p in snap["projects"] if p["in_briefing"]]
    cells = [f'<div><b class="{"sig" if cat == "Suspended" else ""}">{sum(1 for p in ps if p["stage_cat"] == cat)}</b><span>{e(t(lang, key))}</span></div>' for cat, key in STAGE_KEYS]
    total = sum(p["fte"][latest_month - 1] for p in snap["projects"])
    cells.append(f'<div><b>{total:.1f}</b><span>{e(t(lang, "stage_fte", mon=MONTHS[latest_month - 1]))}</span></div>')
    return f'<div class="stages">{"".join(cells)}</div>'


def _passed_mark(lang: str, overdue: bool, sig: bool) -> str:
    if not overdue:
        return ""
    return f' <span class="{"sig" if sig else "dim"}">{e(t(lang, "passed"))}</span>'


def _upcoming(snap: dict, lang: str, today: str, weeks: int, late: set[str]) -> str:
    rows = []
    for p in snap["projects"]:
        if not p["in_briefing"] or p["stage_cat"] == "Suspended":
            continue
        for k in ("evt", "dvt", "pvt", "mp"):
            d = p["dates"][k]
            if d and -7 <= _days(d, today) <= weeks * 7:
                rows.append((d, p["name"], p["customer"], k.upper(), _days(d, today) < 0, p["code"] in late))
    rows.sort()
    body = "".join(f'<tr><td>{d[5:].replace("-", "/")}{_passed_mark(lang, overdue, sig)}</td><td><b>{e(n)}</b></td><td>{e(c)}</td><td>{m}</td></tr>' for d, n, c, m, overdue, sig in rows)
    return (f'<table><thead><tr><th>{e(t(lang, "col_date"))}</th><th>{e(t(lang, "col_project"))}</th><th>{e(t(lang, "col_customer"))}</th><th>{e(t(lang, "col_milestone"))}</th></tr></thead>'
            f'<tbody>{body}</tbody></table>')


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
            cards.append(f'<div><h4>{role}</h4><div class="s">{e(t(lang, "pva_line", plan=f"{plan:.1f}", missing="" if plan else t(lang, "pva_missing"), mon=MONTHS[latest_month - 1], actual=f"{act:.1f}"))}</div>{pva_svg(p["pva"], role, latest_month)}</div>')
        by_m: dict[int, list] = {}
        for task in p["tasks"]:
            by_m.setdefault(task["month"], []).append(task)
        dets = []
        for m in sorted(by_m, reverse=True):
            ts = sorted(by_m[m], key=lambda x: -x["fte"]); bu = sum(1 for x in ts if x["side"] == "BU"); fu = len(ts) - bu
            trs = "".join(f'<tr><td>{x["side"]}</td><td>{e(x["function"])}</td><td>{e(x["dept"])}</td><td class="num">{x["fte"]:.2f}</td><td class="desc">{e(x["description"])}</td></tr>' for x in ts)
            dets.append(f'<details><summary data-expand="{e(t(lang, "expand"))}" data-collapse="{e(t(lang, "collapse"))}"><span>{e(t(lang, "task_summary", mon=MONTHS[m - 1], bu=bu, fu=fu, fte=f"{sum(x["fte"] for x in ts):.1f}"))}</span></summary>'
                        f'<table><thead><tr><th>{e(t(lang, "col_side"))}</th><th>{e(t(lang, "col_function"))}</th><th>{e(t(lang, "col_dept"))}</th><th class="num">{e(t(lang, "col_fte"))}</th><th>{e(t(lang, "col_task"))}</th></tr></thead><tbody>{trs}</tbody></table></details>')
        body = f'<div class="pva">{"".join(cards)}</div><h3 style="font-size:15px;margin:26px 0 6px">{e(t(lang, "s_tasks"))}</h3>{"".join(dets)}'
    meta = "  ".join(x for x in (p["code"] if not p["code"].startswith("NAME:") else "", p["customer"], p["product"], p["group"]) if x)
    return f'<div class="proj" data-idx="{i}"><div class="dim">{e(meta)}</div><div class="ms">{"".join(ms)}</div>{body}</div>'


def render_page(snap: dict, lang: str, today: str, th: dict) -> str:
    m = snap["meta"]; lm = m["latest_month"]
    if lm < 1:
        raise ValueError("no manpower month in snapshot")   # 整頁都以「最新月」定位，沒有它不該畫出半張報表
    ps = snap["projects"]; cl = [p for p in ps if p["in_control_list"]]
    late = {c for x in snap["exceptions"] if x["title"] == "milestones_passed" for c in x["codes"]}
    start = f"{today[:7]}-01"
    head_svg, rows = timeline_svg(ps, today, start, th["timeline_months"], late, lang)
    order = sorted(range(len(ps)), key=lambda i: (0 if ps[i]["in_briefing"] and ps[i]["stage_cat"] not in ("Suspended", "Sustain / EOP") else 1, -ps[i]["fte"][lm - 1]))
    options = "".join(f'<option value="{i}">{e(ps[i]["name"])}{", " + e(ps[i]["stage"]) if ps[i]["stage"] else ""}</option>' for i in order)
    appendix = "".join(_appendix_one(ps[i], lang, today, lm, i) for i in order)
    ym = f"{m['report_month'][:4]}-{m['report_month'][4:]}"
    return f"""<!DOCTYPE html><html lang="{t(lang, "html_lang")}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(t(lang, "doc_title", ym=ym))}</title><style>{CSS}</style></head><body>
<header><div><h1>{e(t(lang, "h1"))}</h1><p>{e(t(lang, "intro"))}</p></div>{_title_block(m, lang, len(cl), lm)}</header>
<section><h2>{e(t(lang, "s_decisions"))}</h2><p class="lead">{e(t(lang, "s_decisions_lead"))}</p>{_exceptions(snap, lang, th)}</section>
<section>{_stage_strip(snap, lang, lm)}<div class="two"><div><h2>{e(t(lang, "s_upcoming", weeks=th["upcoming_weeks"]))}</h2><p class="lead">{e(t(lang, "s_upcoming_lead"))}</p>{_upcoming(snap, lang, today, th["upcoming_weeks"], late)}</div>
<div><h2>{e(t(lang, "s_timeline"))}</h2><p class="lead">{e(t(lang, "s_timeline_lead"))}</p><div class="tl"><table><thead><tr><th>{e(t(lang, "col_project"))}</th><th>{e(t(lang, "col_customer"))}</th><th>{e(t(lang, "col_stage"))}</th><th>{head_svg}</th></tr></thead><tbody>{rows}</tbody></table>
<div class="legend"><span>{e(t(lang, "legend_marks"))}</span><span><i style="background:#E8590C"></i>{e(t(lang, "legend_late"))}</span><span>{e(t(lang, "legend_today"))}</span></div></div></div></div></section>
<section><h2>{e(t(lang, "s_capacity"))}</h2><p class="lead">{e(t(lang, "s_capacity_lead"))}</p>{capacity_svg(ps, snap["capacity"], lm, lang)}
<div class="legend"><span><i style="background:#22262A"></i>{e(t(lang, "lg_capacity"))}</span><span class="dim">{e(t(lang, "lg_capacity_note", mon=MONTHS[lm - 1]))}</span><span><i style="background:#3D5A80"></i>{e(t(lang, "lg_actual"))}</span><span><i style="background:#A9B8CC"></i>{e(t(lang, "lg_budget"))}</span><span><i style="background:#3D5A80;opacity:.6"></i>{e(t(lang, "lg_actual_planned"))}</span><span><i style="background:#5C8D89"></i>{e(t(lang, "lg_fu"))}</span></div></section>
<section><h2>{e(t(lang, "s_health"))}</h2><p class="lead">{e(t(lang, "s_health_lead"))}</p>{_health(snap, lang)}</section>
<section><h2>{e(t(lang, "s_appendix"))}</h2><p class="lead">{e(t(lang, "s_appendix_lead"))}</p><select id="pick">{options}</select><div id="projects">{appendix}</div></section>
<footer><p>{e(t(lang, "foot_1"))}</p><p>{e(t(lang, "foot_2"))}</p><p>{e(t(lang, "foot_3"))}</p></footer>
<script>(function(){{var s=document.getElementById('pick'),ps=document.querySelectorAll('#projects .proj');function show(i){{ps.forEach(function(p){{p.style.display=p.dataset.idx===String(i)?'':'none';}});}}s.addEventListener('change',function(){{show(s.value);}});show(s.value);}})();</script>
</body></html>"""
