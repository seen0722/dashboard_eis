"""純查詢：snapshot dict → dict。MCP tools（tools/*.py）與網頁（web/）共用。

不 import mcp、不碰 ServerState / audit / ctx；月份解析與 meta 包裝留在呼叫端。
回傳格式就是 tool 的回傳格式（少掉 meta），改這裡等於同時改 tool 與網頁。
"""
from __future__ import annotations
from ..portfolio.config import Config, normalize_name
from ..portfolio.entities import INACTIVE, MONTHS
from ..portfolio.model.rules import days_between

MILESTONES = ("evt", "dvt", "pvt", "mp")
TOL = 0.05   # 與 model/diff.cross_month_corrections 的預設容差一致
CORRECTION_CHECK = "cross_month_correction"


class NotFound(Exception):
    """查詢對象不存在。訊息是完整句子，呼叫端自行加 'not_found:' 前綴或翻成 404。"""


# ---- 單案 ----
def resolve_project(snap: dict, query: str, cfg: Config) -> dict | list[dict]:
    """解析順序：代碼精確 → alias → 正規化全名 → 正規化子字串。回單一 dict、或候選清單（可能為空）。"""
    projects = snap["projects"]; q = query.strip()
    exact = [p for p in projects if p["code"].upper() == q.upper()]
    if exact:
        return exact[0]
    nq = normalize_name(q); nq = cfg.aliases.get(nq, nq)
    same = [p for p in projects if normalize_name(p["name"]) == nq]
    if len(same) == 1:
        return same[0]
    if same:
        return same
    partial = [p for p in projects if nq and nq in normalize_name(p["name"])]
    return partial[0] if len(partial) == 1 else partial


def project(snap: dict, query: str, cfg: Config) -> dict:
    hit = resolve_project(snap, query, cfg)
    if isinstance(hit, dict):
        return {"project": hit}
    if not hit:
        raise NotFound(f"no project in {snap['meta']['report_month']} matches '{query}'")
    return {"candidates": [{"code": c["code"], "name": c["name"], "stage": c["stage"]} for c in hit],
            "hint": "several projects match; call get_project again with the exact code"}


def _summary(p: dict, lm: int) -> dict:
    return {"code": p["code"], "name": p["name"], "stage": p["stage"], "stage_cat": p["stage_cat"], "customer": p["customer"],
            "group": p["group"], "biz_type": p.get("biz_type", ""), "category": p.get("category", ""),
            "panel_size": p.get("panel_size", ""), "latest_fte": p["fte"][lm - 1]}


def search(snap: dict, stage_cat: str | None = None, group: str | None = None, customer: str | None = None, text: str | None = None,
           biz_type: str | None = None, category: str | None = None) -> dict:
    """biz_type（JDM/ODM/EMS）與 category 來自 2026-09 起 Briefing 的 Type/Category 欄；舊快照沒有這兩欄時視為空字串。"""
    lm = snap["meta"]["latest_month"]
    nt = normalize_name(text) if text else ""
    ng, nc = (normalize_name(group) if group else ""), (normalize_name(customer) if customer else "")
    nb, nk = (normalize_name(biz_type) if biz_type else ""), (normalize_name(category) if category else "")
    rows = [q for q in snap["projects"]
            if (not stage_cat or q["stage_cat"].lower() == stage_cat.lower())
            and (not ng or normalize_name(q["group"]) == ng)
            and (not nc or normalize_name(q["customer"]) == nc)
            and (not nb or normalize_name(q.get("biz_type", "")) == nb)
            and (not nk or normalize_name(q.get("category", "")) == nk)
            and (not nt or any(nt in normalize_name(q[k]) for k in ("name", "customer", "product")))]
    return {"count": len(rows), "projects": [_summary(q, lm) for q in rows]}


def distinct(snap: dict, field: str) -> list[str]:
    return sorted({p[field] for p in snap["projects"] if p.get(field)})


# ---- 總覽 ----
def exceptions(snap: dict) -> dict:
    return {"count": len(snap["exceptions"]), "exceptions": snap["exceptions"]}


def health(snap: dict) -> dict:
    return {"health": snap["health"]}


def upcoming_milestones(snap: dict, today: str, weeks: int) -> list[dict]:
    """與 rules._active() 同條件：只看 in_briefing 且非 Terminated/Suspended 的專案；視窗前後各 weeks 週；已過期者 days_left 為負。"""
    span = weeks * 7
    out = []
    for p in snap["projects"]:
        if not p.get("in_briefing") or p.get("stage_cat") in INACTIVE:
            continue
        for ms in MILESTONES:
            d = p["dates"].get(ms)
            if not d:
                continue
            left = days_between(d, today)
            if -span <= left <= span:
                out.append({"code": p["code"], "name": p["name"], "stage_cat": p["stage_cat"], "milestone": ms, "date": d, "days_left": left})
    return sorted(out, key=lambda r: (r["days_left"], r["code"]))


def upcoming(snap: dict, today: str, weeks: int) -> dict:
    return {"today": today, "weeks": weeks, "milestones": upcoming_milestones(snap, today, weeks)}


# ---- 負載 ----
def dept_loads(snap: dict, min_util: float | None = None) -> dict:
    lm = snap["meta"]["latest_month"]
    rows = [{**r, "latest_util": r["util"][lm - 1]} for r in snap["loads"]]
    if min_util is not None:
        rows = [r for r in rows if r["latest_util"] is not None and r["latest_util"] >= min_util]
    rows.sort(key=lambda r: (r["latest_util"] is None, -r["latest_util"] if r["latest_util"] is not None else 0, r["dept_code"]))
    return {"latest_month": lm, "count": len(rows), "loads": rows}


def capacity(snap: dict) -> dict:
    return {"months": list(MONTHS), "capacity": snap["capacity"]}


# ---- 跨月 ----
def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def diff_values(a, b, tol: float = TOL) -> dict | None:
    if isinstance(a, dict) and isinstance(b, dict):
        out = {}
        for k in sorted(set(a) | set(b)):
            d = diff_values(a.get(k), b.get(k), tol)
            if d is not None:
                out[k] = d
        return out or None
    if isinstance(a, list) and isinstance(b, list):
        if a and b and all(_is_num(x) for x in a + b):
            if len(a) != len(b) or any(abs(x - y) > tol for x, y in zip(a, b)):
                return {"a": a, "b": b}
            return None
        if any(isinstance(x, dict) for x in a + b):
            return None if len(a) == len(b) else {"a_count": len(a), "b_count": len(b)}
        return None if a == b else {"a": a, "b": b}
    if _is_num(a) and _is_num(b):
        return None if abs(a - b) <= tol else {"a": a, "b": b}
    return None if a == b else {"a": a, "b": b}


def diff(snap_a: dict, snap_b: dict, code: str) -> dict:
    ma, mb = snap_a["meta"]["report_month"], snap_b["meta"]["report_month"]
    pa = next((q for q in snap_a["projects"] if q["code"].upper() == code.upper()), None)
    pb = next((q for q in snap_b["projects"] if q["code"].upper() == code.upper()), None)
    if pa is None or pb is None:
        where = " and ".join(m for m, q in ((ma, pa), (mb, pb)) if q is None)
        raise NotFound(f"{code} is not in the snapshot for {where}")
    return {"code": pa["code"], "month_a": ma, "month_b": mb, "meta_a": snap_a["meta"], "meta_b": snap_b["meta"],
            "changed": diff_values(pa, pb) or {}}


def corrections(snap: dict) -> dict:
    rows = [i for i in snap["issues"] if i["check"] == CORRECTION_CHECK]
    return {"count": len(rows), "corrections": rows}
