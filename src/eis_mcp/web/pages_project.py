"""候選清單、單案頁、跨月 diff 的 body（專案列表在 pages_projects.py）。數字全部來自快照與 viz/project.py。"""
from __future__ import annotations
import datetime as dt
from html import escape as e
from ...portfolio.entities import MONTHS
from ...portfolio.render.viz.dash import card, chart_card, kpi_cards, risk_reason
from ...portfolio.render.viz.embed import chart_html
from ...portfolio.render.viz.options import pva
from ...portfolio.render.viz.project import mp_drift, next_milestone, pva_line, task_groups

def candidates_body(month: str, cands: list[dict], query: str) -> str:
    rows = "".join(f'<tr><td><a href="/ui/{month}/projects/{e(c["code"])}">{e(c["code"])}</a></td><td><b>{e(c["name"])}</b></td><td>{e(c["stage"])}</td></tr>' for c in cands)
    return (f'<section><h2>Several projects match "{e(query)}"</h2><p class="lead">Pick one.</p>'
            f'<div class="wide"><table><thead><tr><th>Code</th><th>Project</th><th>Stage</th></tr></thead><tbody>{rows}</tbody></table></div></section>')


def _twelve(label: str, values: list, fmt: str) -> str:
    return f'<tr><th>{e(label)}</th>' + "".join(f'<td class="num">{format(v, fmt) if v is not None else "–"}</td>' for v in values) + "</tr>"


def _top_cards(p: dict, lm: int, today: str, risk: dict | None) -> str:
    why = [risk_reason(w, "en", p["stage"]) for w in (risk or {}).get("why", [])]
    late = next((w for w in (risk or {}).get("why", []) if w["rule"] == "passed" and "date" in w), None)
    nxt = next_milestone(p, today) if p["in_briefing"] else None
    if late:
        nx = {"value": f'{late["ms"]} {late["date"]}', "sub": f'overdue {late["days"]} days', "tone": "bad"}
    elif nxt:
        nx = {"value": f'{nxt["key"].upper()} {nxt["date"]}', "sub": f'in {nxt["days"]} days'}
    else:
        nx = {"value": "–", "sub": "none ahead in the briefing" if p["in_briefing"] else "not in briefing"}
    kind = ", ".join(x for x in (p.get("biz_type", ""), p.get("category", "")) if x)
    fte_sub = f'from {p["fte"][0]:.1f} in Jan' if lm > 1 else "Resource Summary"
    items = [{"key": "stage", "label": "Stage", "value": p["stage"] or "–", "tone": "bad" if why else "",
              "sub": ("At risk: " + "; ".join(why)) if why else (p["stage_cat"] or "not in briefing")},
             {"key": "customer", "label": "Customer", "value": p["customer"] or "–", "sub": kind},
             {"key": "next", "label": "Next milestone", **nx},
             {"key": "fte", "label": f"FTE, {MONTHS[lm - 1]}", "value": f'{p["fte"][lm - 1]:.1f}', "sub": fte_sub}]
    return kpi_cards(items, cls="four")


def _warnings(p: dict) -> str:
    """原本的 key-value 清單只剩「缺什麼」：在 Briefing／Control List／plan 都有就不顯示。"""
    miss = [m for ok, m in ((p["in_briefing"], "not in the Briefing, so no stage or dates"),
                            (p["in_control_list"], "not in any Control List, so no plan vs actual or tasks"),
                            (p["has_plan"] or not p["in_control_list"], "in a Control List but without a plan")) if not ok]
    return f'<p class="warn">This project is {e("; ".join(miss))}.</p>' if miss else ""


def _milestones(p: dict, today: str, risk: dict | None) -> str:
    late = {w["ms"].lower() for w in (risk or {}).get("why", []) if w["rule"] == "passed" and "ms" in w}
    rows = []
    for k in ("kickoff", "evt", "dvt", "pvt", "mp"):
        d = p["dates"].get(k)
        if d:
            n = (dt.date.fromisoformat(d) - dt.date.fromisoformat(today)).days
            when = f"overdue {-n} days" if k in late else (f"in {n} days" if n >= 0 else f"{-n} days ago")
        else:
            when = "not filled" if p["in_briefing"] else "not in briefing"
        cls = ' class="sig"' if k in late else ""
        rows.append(f'<tr{cls}><td>{"Kick-off" if k == "kickoff" else k.upper()}</td><td>{e(d or "–")}</td><td>{e(when)}</td></tr>')
    mo, mp = p["dates"].get("mp_orig"), p["dates"].get("mp")
    if mo:
        gap = (dt.date.fromisoformat(mp) - dt.date.fromisoformat(mo)).days if mp else None
        rows.append(f'<tr class="orig"><td>Original MP</td><td>{e(mo)}</td><td>{e(f"current MP {gap:+d} days" if gap is not None else "current MP not filled")}</td></tr>')
    return card("Milestones", f'<table class="ms-t"><tbody>{"".join(rows)}</tbody></table>', sub="Dates as the latest Briefing states them")


def _drift(p: dict) -> str:
    ch = mp_drift(p, "en")
    if ch is None:
        return card("MP date in each Briefing", '<p class="note">No Briefing on file gives this project an MP date.</p>')
    return chart_card(ch, "en")


def _pva(p: dict, lm: int) -> str:
    if not p.get("pva"):
        return '<p class="empty">No Control List for this project, so there is no plan vs actual.</p>'
    cards = [card(role, chart_html(pva(p, role, lm, "en", 0), "en"), sub=pva_line((p["pva"].get(role) or {"plan": [0] * 12, "actual": [0] * 12}), lm, "en"))
             for role in ("BU RD", "FU RD", "PM")]
    return f'<div class="grid-3 eq">{"".join(cards)}</div>'


def _task_month(m: int, ts: list[dict], open_: bool) -> str:
    bu = sum(1 for x in ts if x["side"] == "BU")
    groups = task_groups(ts, m)
    trs = []
    for g in groups:
        items = "".join(f'<li><span class="tt">{e(i["text"]) or "<i>no description</i>"}</span>'
                        f'<small>{len(i["depts"])} dept{"" if len(i["depts"]) == 1 else "s"}, {i["fte"]:.2f} FTE</small></li>' for i in g["items"])
        trs.append(f'<tr><td>{e(g["side"])}</td><td>{e(g["function"])}</td><td class="num">{g["depts"]}</td><td class="num">{g["fte"]:.2f}</td><td><ul class="ti">{items}</ul></td></tr>')
    raw = "".join(f'<tr><td>{x["side"]}</td><td>{e(x["function"])}</td><td>{e(x["dept"])}</td><td class="num">{x["fte"]:.2f}</td><td class="desc">{e(x["description"])}</td></tr>'
                  for x in sorted(ts, key=lambda x: -x["fte"]))
    summary = f'{MONTHS[m - 1]}: {bu} BU tasks, {len(ts) - bu} FU tasks, {sum(x["fte"] for x in ts):.1f} FTE'
    return (f'<details class="month"{" open" if open_ else ""}><summary data-expand="expand" data-collapse="collapse"><span>{e(summary)}</span></summary>'
            f'<div class="wide"><table class="tg"><thead><tr><th>Side</th><th>Function</th><th class="num">Depts</th><th class="num">FTE</th><th>What they reported (same text merged)</th></tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table></div>'
            f'<details class="raw"><summary data-expand="expand" data-collapse="collapse"><span>Show all {len(ts)} rows</span></summary>'
            f'<div class="wide"><table><thead><tr><th>Side</th><th>Function</th><th>Department</th><th class="num">FTE</th><th>Task</th></tr></thead><tbody>{raw}</tbody></table></div></details></details>')


def _tasks(p: dict) -> str:
    by_m: dict[int, list] = {}
    for x in p["tasks"]:
        by_m.setdefault(x["month"], []).append(x)
    if not by_m:
        return '<p class="empty">No tasks reported in the Control List.</p>'
    ms = sorted(by_m, reverse=True)
    return "".join(_task_month(m, by_m[m], i == 0) for i, m in enumerate(ms))


def project_body(month: str, p: dict, today: str, lm: int, prev: str | None, risk: dict | None = None) -> str:
    """閱讀順序：狀態（含 At risk 原因）→ MP 漂移與里程碑 → plan vs actual → 任務（依 Function 彙總）→ 逐月 FTE/NTD。"""
    cmp_ = (f'<p class="page-actions"><a href="/ui/{e(month)}/projects/{e(p["code"])}/diff?to={e(prev)}">Compare with {prev[:4]}-{prev[4:]}</a>'
            f'<span class="dim">{e(p["code"])}</span></p>') if prev else f'<p class="page-actions"><span class="dim">{e(p["code"])}</span></p>'
    head = "".join(f'<th class="num">{m}</th>' for m in MONTHS)
    months_tbl = (f'<div class="wide"><table><thead><tr><th></th>{head}</tr></thead><tbody>{_twelve("FTE", p["fte"], ".1f")}{_twelve("NTD", p["ntd"], ",.0f")}</tbody></table></div>'
                  f'<p class="dim">Manpower keyed in through {MONTHS[lm - 1]}; later months are plan or zero.</p>')
    return (f'<section>{cmp_}{_top_cards(p, lm, today, risk)}{_warnings(p)}</section>'
            f'<section><div class="tl-row eq">{_drift(p)}{_milestones(p, today, risk)}</div></section>'
            f'<section><h2>Plan vs actual</h2>{_pva(p, lm)}</section>'
            f'<section><h2>Tasks</h2>{_tasks(p)}</section>'
            f'<section><h2>FTE and NTD by month</h2>{months_tbl}</section>')


def _fmt(v) -> str:
    if v is None:
        return "–"
    if isinstance(v, list):
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {_fmt(x)}" for k, x in v.items()) + "}"
    return str(v)


def flatten_changes(changed: dict, prefix: str = "") -> list[tuple[str, str, str]]:
    """queries.diff 的 changed 樹攤成 (欄位路徑, a, b)。葉節點是 {"a","b"} 或 {"a_count","b_count"}；其餘往下走。依路徑排序。"""
    out = []
    for k, v in changed.items():
        path = f"{prefix}{k}"
        if set(v) == {"a", "b"}:
            out.append((path, _fmt(v["a"]), _fmt(v["b"])))
        elif set(v) == {"a_count", "b_count"}:
            out.append((f"{path} (count)", str(v["a_count"]), str(v["b_count"])))
        else:
            out.extend(flatten_changes(v, path + "."))
    return sorted(out)


def diff_body(month: str, res: dict) -> str:
    a, b = res["month_a"], res["month_b"]
    rows = flatten_changes(res["changed"])
    if not rows:
        return f'<section><h2>{e(res["code"])}: identical in {a[:4]}-{a[4:]} and {b[:4]}-{b[4:]}</h2><p class="empty">No field differs (numeric lists compared with 0.05 tolerance).</p></section>'
    trs = "".join(f'<tr><td>{e(f)}</td><td>{e(x)}</td><td class="sig">{e(y)}</td></tr>' for f, x, y in rows)
    return (f'<section><h2>{e(res["code"])}: {len(rows)} change{"" if len(rows) == 1 else "s"}</h2>'
            f'<p class="lead"><a href="/ui/{month}/projects/{e(res["code"])}">Back to the project</a></p>'
            f'<div class="wide"><table><thead><tr><th>Field</th><th>{a[:4]}-{a[4:]} (a)</th><th>{b[:4]}-{b[4:]} (b)</th></tr></thead><tbody>{trs}</tbody></table></div>'
            f'<p class="dim">Only fields that differ are listed; task/history lists report a count change only.</p></section>')
