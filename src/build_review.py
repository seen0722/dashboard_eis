#!/usr/bin/env python3
"""BU10 人力執行 review — 超配分析（第一版）

只回答一個問題：哪些專案的實際人力超過計畫？來自哪些單位？

用法:
    python src/build_review.py                 # 全部月份，中文
    python src/build_review.py --lang en       # 全部月份，英文
    python src/build_review.py 202605 202606   # 指定月份
    open out/review.html

資料語意、踩過的坑、為何這樣算 —— 見 AGENTS.md（務必先讀）
"""
import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))   # 允許從任何目錄執行
from i18n import strings  # noqa: E402
from themes import THEMES, theme_css  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
CONFIG = ROOT / "config"
OUT = ROOT / "out"

# EIS_FUNCTION 裡代表 PM 的所有寫法。
# ⚠ 不可用 contains('PM')：會誤抓人名「支援BU18 (PM Grace)」、廠區「AXM2/PMX」、系統名「IPMS-開會及研究」
PM_FUNCTIONS = {"PM", "ME PM", "RD PM", "RDPM", "RE PM", "NPI PM", "SYSTEM PM", "Sales PM"}
ROLES = ("FU RD", "BU RD", "BU PM")


def load_config():
    cfg = {}
    for name in ("aliases", "thresholds", "plan_exclusions"):
        with open(CONFIG / f"{name}.yaml", encoding="utf-8") as f:
            cfg[name] = yaml.safe_load(f)
    return cfg


def find_file(pattern):
    """忽略 Excel 鎖檔（~$ 開頭）。"""
    hits = [p for p in RAW.glob(pattern) if not p.name.startswith("~$")]
    if not hits:
        raise FileNotFoundError(f"{RAW}/{pattern} 找不到")
    return hits[0]


def find_sheet(wb, pattern):
    """分頁名每月變動（Project 4 vs. 5 → Project 5 vs.6；有的還多一個開頭空格），
    故一律用 regex 比對，不可用字面名稱。"""
    for name in wb.sheetnames:
        if re.search(pattern, name):
            return wb[name]
    raise KeyError(f"找不到符合 {pattern} 的分頁；現有：{wb.sheetnames}")


def month_col(header, yyyymm):
    """plan 的月份欄位表頭是 datetime，找出對應 yyyymm 的欄索引。"""
    want = f"{yyyymm[:4]}-{yyyymm[4:6]}"
    for i, h in enumerate(header):
        if h and want in str(h):
            return i
    raise KeyError(f"plan 找不到 {want} 的欄位")


class Normalizer:
    """套用別名。比對前一律 lower()，故純大小寫差異不需列進 aliases.yaml。"""

    def __init__(self, aliases_cfg):
        self.alias = {k.lower(): v.lower() for k, v in (aliases_cfg.get("confirmed") or {}).items()}

    def __call__(self, name):
        k = str(name).strip().lower()
        return self.alias.get(k, k)


def read_plan(path, yyyymm, cfg, norm):
    """回傳 (plan dict, display names, 編制檢核區塊)。

    ⚠ 必須用 -updated 不是 -PM：-PM 是過時版，用它會讓 D5K/D7K/VASCO 從
      「計畫已歸零但人還在」變成「人力不足 69%」——結論完全相反。
    """
    ex = cfg["plan_exclusions"]
    subtotals = {s.lower() for s in ex["product_subtotals"]}
    non_project = set(ex["non_project_units"])

    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["人力分攤-updated"]
    rows = list(ws.iter_rows(values_only=True))
    ci = month_col(rows[0], yyyymm)

    plan, disp = {}, {}
    for r in rows[1:]:
        name, unit = r[1], r[2]
        if not name or not unit or unit in non_project:
            continue
        key = norm(name)
        if key in subtotals:
            continue
        disp.setdefault(key, str(name).strip())
        plan.setdefault(key, dict.fromkeys(ROLES, 0.0))
        if unit in ROLES and isinstance(r[ci], (int, float)):
            plan[key][unit] += r[ci]

    headcount = read_headcount_block(ws, rows[0])
    wb.close()
    return plan, disp, headcount


def read_headcount_block(ws, header):
    """列 129~131 的編制檢核區塊。

    ⚠ 初版把列 130（人力『編列』= SUM(BU RD + BU PM)）誤當成編制上限，
      得出「編制已貼滿 205.8/205.7」——那是把 205.75 減 205.75 的同義反覆。
      列 129 硬編的 203 才是編制；列 131 是 PM 自己算好的真訊號。
    """
    def row_by_label(label):
        for r in range(115, 145):
            if str(ws.cell(r, 3).value or "").strip() == label:
                return r
        return None

    r_est = row_by_label("BU RD+ PM 人力")
    r_gap = row_by_label("不足/超出人力")
    if not (r_est and r_gap):
        return None

    months, est, gap = [], [], []
    for i, h in enumerate(header):
        if h and str(h).startswith("20"):
            months.append(int(str(h)[5:7]))          # 月份用整數，語言在 render 時才套
            est.append(ws.cell(r_est, i + 1).value)
            gap.append(ws.cell(r_gap, i + 1).value)
    return {"months": months, "establishment": est, "gap": gap}


def read_actual(path, yyyymm, cfg, norm, disp):
    """回傳 (actual dict, 逐部門明細, 部門名稱)。

    資料源分工（見 AGENTS.md）：
      - D 組用『人力明細』：唯一有 EIS_FUNCTION 的表，才分得出 BU PM
      - Y 組用『ProjectCode人力』：全公司的百分比分攤（FU 支援）
      兩者不重疊，直接相加，不需去重。
    """
    ex = cfg["plan_exclusions"]
    bad_prefix = tuple(ex["exclude_dept_prefix"])

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)

    # dept_org：部門自己所屬的組織。
    # ⚠ 與『人力明細.BU』（＝專案歸屬的 BU）同名不同義，切勿混用。
    pct = list(find_sheet(wb, r"\d{6}-百分比分攤").iter_rows(values_only=True))
    ibu = list(pct[0]).index("BU")
    dept_org = {r[1]: r[ibu] for r in pct[1:] if r[1]}

    def is_external(dept, project_bu):
        """FU RD = 非本 BU 的支援（含其他 BU）。此規則完全重現人工樞紐（19/19、誤差 0）。
        ⚠ 不可用來源分頁或部門首字推斷——8 個 FU 部門逐人填報、其他 BU 也會支援 BU10。"""
        org = dept_org.get(dept)
        return str(dept)[0] == "F" if org is None else org != project_bu

    actual = defaultdict(lambda: dict.fromkeys(ROLES, 0.0))
    by_dept = defaultdict(lambda: defaultdict(float))
    dept_name = {}

    for r in find_sheet(wb, r"\d{6}-人力明細").iter_rows(min_row=2, values_only=True):
        dept, func, fte, name, bu = r[0], r[5], r[6], r[10], r[13]
        if not name or not isinstance(fte, (int, float)):
            continue
        if str(dept).startswith(bad_prefix) or bu != "BU10":
            continue
        key = norm(name)
        disp.setdefault(key, str(name).strip())
        dept_name[dept] = str(r[1])
        role = "FU RD" if is_external(dept, bu) else ("BU PM" if func in PM_FUNCTIONS else "BU RD")
        actual[key][role] += fte
        by_dept[key][(dept, role)] += fte

    for r in find_sheet(wb, r"\d{6}-ProjectCode人力").iter_rows(min_row=2, values_only=True):
        dept, fte, flag, name, bu = r[0], r[3], r[6], r[7], r[10]
        if flag != "Y" or not name or not isinstance(fte, (int, float)):
            continue
        if str(dept).startswith(bad_prefix) or bu != "BU10":
            continue
        key = norm(name)
        disp.setdefault(key, str(name).strip())
        dept_name[dept] = str(r[1])
        role = "FU RD" if is_external(dept, bu) else "BU RD"
        actual[key][role] += fte
        by_dept[key][(dept, role)] += fte

    wb.close()
    return actual, by_dept, dept_name


def classify(plan, actual, disp, cfg):
    """分三類 + 全專案表。

    A. plan>0 且 actual>plan —— 兩側名字都對得上才可能成立，
       故別名失敗只會讓專案「消失」，不會憑空長出來。可信度最高。
    B. plan=0 但有 actual —— 受別名覆蓋率影響，需個別確認。
    all_projects —— 逐月趨勢用：不套門檻、不分類，保留每個專案的 plan/actual。
    """
    rfq = re.compile(cfg["plan_exclusions"]["rfq_pattern"])
    plan_keys = set(plan)          # ⚠ 先固定：actual 是 defaultdict，讀取會建立 key
    min_excess = cfg["thresholds"]["over_allocation"]["min_excess_fte"]

    over, other, skipped, all_projects = [], [], [], {}
    for key in plan_keys | set(actual):
        if rfq.match(disp.get(key, "").lower()):
            continue
        p = sum(plan.get(key, {}).values())
        a = sum(actual[key].values()) if key in actual else 0.0
        all_projects[key] = {"name": disp[key], "plan": p, "actual": a, "excess": a - p}
        if p > 0.05 and a > p:
            item = {"key": key, "name": disp[key], "plan": p, "actual": a, "excess": a - p,
                    "plan_roles": plan[key], "actual_roles": actual[key]}
            (over if a - p >= min_excess else skipped).append(item)
        elif p < 0.05 and a > 0.05:
            other.append({"key": key, "name": disp[key], "actual": a,
                          "kind": "zeroed" if key in plan_keys else "unplanned"})

    over.sort(key=lambda x: -x["excess"])
    other.sort(key=lambda x: -x["actual"])
    skipped.sort(key=lambda x: -x["excess"])
    return over, other, skipped, all_projects


def available_months():
    """從 data/raw 找出所有可用月份。
    ⚠ 月份 M 的資料一律取自 M 檔本身——不可用次月檔的前月欄（見 AGENTS.md「取月規則」）。"""
    ms = set()
    for p in RAW.glob("*.xlsx"):
        if p.name.startswith("~$"):
            continue
        m = re.match(r"(\d{6})", p.name)
        if m:
            ms.add(m.group(1))
    return sorted(ms)


def build_month(yyyymm, cfg, norm):
    """單月的完整資料集。"""
    plan_file = find_file("*plan*.xlsx")
    review_file = find_file(f"{yyyymm}*.xlsx")
    disp = {}
    plan, disp, headcount = read_plan(plan_file, yyyymm, cfg, norm)
    actual, by_dept, dept_name = read_actual(review_file, yyyymm, cfg, norm, disp)
    over, other, skipped, all_projects = classify(plan, actual, disp, cfg)
    return {
        "yyyymm": yyyymm, "over": over, "other": other, "skipped": skipped,
        "all": all_projects, "by_dept": by_dept, "dept_name": dept_name,
        "headcount": headcount, "review_file": review_file.name,
        "excluded_mfg": mfg_total(review_file, cfg),
    }


# ---------- HTML ----------

def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def fmt(v, dp=2):
    return f"{v:.{dp}f}"


def dept_rows(by_dept, key, dept_name, top_n, S):
    rows = sorted(by_dept[key].items(), key=lambda x: -x[1])
    out = []
    for (dept, role), fte in rows[:top_n]:
        out.append(f'<tr><td class="mono">{esc(dept)}</td><td>{esc(dept_name.get(dept,"?"))}</td>'
                   f'<td class="mono dim">{role}</td><td class="num">{fmt(fte)}</td></tr>')
    if len(rows) > top_n:
        rest = sum(v for _, v in rows[top_n:])
        out.append(f'<tr class="rest"><td></td><td>{S["dept_rest"].format(n=len(rows)-top_n)}</td><td></td>'
                   f'<td class="num">{fmt(rest)}</td></tr>')
    return "".join(out)


# ---------- 圖表（inline SVG，無外部依賴） ----------

def scrollable(svg):
    """寬圖表包進自己的橫向捲動容器 —— 頁面 body 永不橫向捲動。
    ⚠ 沒有這層時，900 寬的 viewBox 在 390px 手機上會被壓到 0.4 倍，
      11px 的文字變成 4.4px，圖表等於不存在。"""
    return f'<div class="chart-wrap">{svg}</div>'


def trend_table(months, series, S):
    """slope chart 的手機版 —— 同一份資料，換一種呈現。"""
    if len(months) < 2 or not series:
        return ""
    head = "".join(f'<th>{S["month"](int(str(m)[4:6]))}</th>' for m in months)
    rows = ""
    for s in series:
        vals = "".join(f'<td class="num">{v:+.1f}</td>' if v is not None else '<td class="num dim">—</td>'
                       for _, v in s["values"])
        pts = [v for _, v in s["values"] if v is not None]
        d = pts[-1] - pts[0] if len(pts) >= 2 else 0
        cls = "up" if d > 0 else ("down" if d < 0 else "flat")
        rows += f'<tr><td>{esc(s["name"])}</td>{vals}<td class="num d-{cls}">{d:+.1f}</td></tr>'
    return (f'<table class="trend-tbl"><thead><tr><th></th>{head}<th>Δ</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>')


def chart_headcount(hc, yyyymm, S):
    """編制 vs 計畫編列：12 個月長條 + 編制參考線。"""
    months, est, plan_v = [], [], []
    for m, e, g in zip(hc["months"], hc["establishment"], hc["gap"]):
        if not isinstance(e, (int, float)) or not isinstance(g, (int, float)):
            continue
        months.append(m)
        est.append(e)
        plan_v.append(e - g)          # plan 編列 = 編制 − 不足/超出

    W, H = 900, 300
    pad_l, pad_r, pad_t, pad_b = 46, 16, 24, 46
    iw, ih = W - pad_l - pad_r, H - pad_t - pad_b
    lo, hi = 150, max(max(plan_v), max(est)) * 1.07
    n = len(months)
    bw = iw / n * 0.54
    cur = int(yyyymm[4:6])

    def y(v):
        return pad_t + ih - (v - lo) / (hi - lo) * ih

    def x(i):
        return pad_l + iw / n * (i + 0.5)

    parts = []
    for v in range(160, int(hi) + 1, 20):
        parts.append(f'<line class="grid" x1="{pad_l}" y1="{y(v):.1f}" x2="{W-pad_r}" y2="{y(v):.1f}"/>'
                     f'<text class="ax" x="{pad_l-8}" y="{y(v)+4:.1f}" text-anchor="end">{v}</text>')
    for i, (m, e, p) in enumerate(zip(months, est, plan_v)):
        over = p > e
        cls = "bar--over" if over else "bar"
        hl = "tick--cur" if m == cur else "tick"
        parts.append(f'<rect class="{cls}" x="{x(i)-bw/2:.1f}" y="{y(p):.1f}" width="{bw:.1f}" '
                     f'height="{max(pad_t+ih-y(p),0):.1f}" rx="1.5"/>')
        parts.append(f'<text class="val{" val--over" if over else ""}" x="{x(i):.1f}" y="{y(p)-7:.1f}" '
                     f'text-anchor="middle">{p:.1f}</text>')
        parts.append(f'<text class="{hl}" x="{x(i):.1f}" y="{H-pad_b+18:.1f}" '
                     f'text-anchor="middle">{S["month"](m)}</text>')
    e0 = est[0]
    label = S["hc_ref"].format(est=e0)
    parts.append(f'<line class="ref" x1="{pad_l}" y1="{y(e0):.1f}" x2="{W-pad_r}" y2="{y(e0):.1f}"/>')
    parts.append(f'<rect class="ref__bg" x="{pad_l+4}" y="{y(e0)-15:.1f}" '
                 f'width="{len(label)*6.6+10:.0f}" height="14" rx="3"/>')
    parts.append(f'<text class="ref__t" x="{pad_l+9}" y="{y(e0)-4:.1f}">{esc(label)}</text>')

    return scrollable(f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
                      f'aria-label="{esc(S["hc_h"])}">{"".join(parts)}</svg>')


def chart_over(over, S):
    """超配專案：plan / actual 橫向對照。"""
    if not over:
        return ""
    W = 900
    row_h, gap = 46, 14
    pad_l, pad_r, pad_t = 128, 96, 32      # pad_r 留給右側「超出」欄，避免與長條標籤相撞
    H = pad_t + len(over) * (row_h + gap) + 6
    iw = W - pad_l - pad_r - 52            # 再留 52px 給長條末端的數值標籤
    hi = max(o["actual"] for o in over) * 1.02

    parts = [f'<text class="lg" x="{pad_l}" y="16">{esc(S["lg_plan"])}</text>',
             f'<text class="lg lg--a" x="{pad_l+62}" y="16">{esc(S["lg_act"])}</text>',
             f'<text class="lg lg--e" x="{pad_l+134}" y="16">{esc(S["lg_ex"])}</text>',
             f'<text class="lg lg--e" x="{W-6}" y="16" text-anchor="end">{esc(S["lg_axis"])}</text>']
    for i, o in enumerate(over):
        yt = pad_t + i * (row_h + gap)
        pw, aw = o["plan"] / hi * iw, o["actual"] / hi * iw
        parts.append(f'<text class="lbl" x="{pad_l-10}" y="{yt+23:.1f}" text-anchor="end">{esc(o["name"])}</text>')
        parts.append(f'<rect class="b-plan" x="{pad_l}" y="{yt:.1f}" width="{max(pw,1):.1f}" height="15" rx="1.5"/>')
        parts.append(f'<rect class="b-act" x="{pad_l}" y="{yt+19:.1f}" width="{max(aw,1):.1f}" height="15" rx="1.5"/>')
        parts.append(f'<rect class="b-ex" x="{pad_l+pw:.1f}" y="{yt+19:.1f}" width="{max(aw-pw,1):.1f}" height="15" rx="1.5"/>')
        parts.append(f'<text class="bv" x="{pad_l+pw+6:.1f}" y="{yt+12:.1f}">{o["plan"]:.1f}</text>')
        parts.append(f'<text class="bv bv--a" x="{pad_l+aw+6:.1f}" y="{yt+31:.1f}">{o["actual"]:.2f}</text>')
        parts.append(f'<text class="ex" x="{W-6}" y="{yt+24:.1f}" text-anchor="end">+{o["excess"]:.2f}</text>')
    return scrollable(f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
                      f'aria-label="{esc(S["over_h"])}">{"".join(parts)}</svg>')


def chart_roles(plan_roles, actual_roles):
    """單一專案的三層 plan/actual 迷你長條。"""
    hi = max([plan_roles.get(r, 0) for r in ROLES] + [actual_roles.get(r, 0) for r in ROLES] + [0.1])
    cells = []
    for role in ROLES:
        p, a = plan_roles.get(role, 0), actual_roles.get(role, 0)
        if p < 0.05 and a < 0.05:
            cells.append(f'<div class="rl rl--empty"><span class="rl__k">{role}</span>'
                         f'<span class="rl__v">—</span><span class="rl__pct"></span></div>')
            continue
        pct = a / p * 100 if p > 0.05 else None
        over = pct is not None and pct > 110
        under = pct is not None and pct < 70
        cls = "rl--over" if over else ("rl--under" if under else "")
        pw, aw = p / hi * 100, a / hi * 100
        pct_t = f"{pct:.0f}%" if pct is not None else ""
        cells.append(
            f'<div class="rl {cls}">'
            f'<span class="rl__k">{role}</span>'
            f'<span class="rl__v">{fmt(p,1)}<i>→</i>{fmt(a,1)}</span>'
            f'<span class="rl__pct">{pct_t}</span>'
            f'<span class="rl__bars"><i class="rl__p" style="width:{pw:.0f}%"></i>'
            f'<i class="rl__a" style="width:{aw:.0f}%"></i></span>'
            f'</div>')
    return "".join(cells)


def chart_trend(months, series, S):
    """逐月超出 FTE。2 個月時是 slope chart，補到 6 個月自然變成折線圖——同一個元件。

    series: [{name, values: [(month, excess|None)]}]，已依最新月超出量排序。
    """
    if len(months) < 2 or not series:
        return ""
    W = 900
    pad_l, pad_r, pad_t, pad_b = 92, 92, 34, 34
    H = max(320, 68 + len(series) * 30)
    iw, ih = W - pad_l - pad_r, H - pad_t - pad_b
    vals = [v for s in series for _, v in s["values"] if v is not None]
    lo, hi = min(0, min(vals)), max(vals) * 1.08
    n = len(months)

    def x(i):
        return pad_l + (iw * i / (n - 1) if n > 1 else iw / 2)

    def y(v):
        return pad_t + ih - (v - lo) / (hi - lo) * ih

    def declutter(items):
        """標籤去重疊：值太接近時垂直推開，回傳 {idx: label_y}。

        ⚠ 必要而非美化 —— 未處理時 D5K2 +1.6 / AF900 +1.5 / AON100 +1.4
          三條標籤完全疊死，圖表等於讀不出來。
        """
        GAP = 14.0
        order = sorted(items, key=lambda t: t[1])          # (idx, y) 由上而下
        placed = {}
        prev = -1e9
        for idx, yy in order:
            ny = max(yy, prev + GAP)
            placed[idx] = ny
            prev = ny
        # 若整體被推超出下緣，整體上移
        overflow = max(placed.values(), default=0) - (pad_t + ih + 6)
        if overflow > 0:
            for k in placed:
                placed[k] -= overflow
        return placed

    parts = []
    parts.append(f'<line class="zero" x1="{pad_l}" y1="{y(0):.1f}" x2="{W-pad_r}" y2="{y(0):.1f}"/>')
    for i, m in enumerate(months):
        parts.append(f'<line class="colrule" x1="{x(i):.1f}" y1="{pad_t-8}" x2="{x(i):.1f}" y2="{pad_t+ih:.1f}"/>')
        parts.append(f'<text class="colm" x="{x(i):.1f}" y="{H-pad_b+20:.1f}" text-anchor="middle">'
                     f'{S["month"](int(str(m)[4:6]))}</text>')

    drawn = []
    for si, s in enumerate(series):
        pts = [(i, v) for i, (_, v) in enumerate(s["values"]) if v is not None]
        if not pts:
            continue
        first, last = pts[0][1], pts[-1][1]
        cls = "up" if last > first else ("down" if last < first else "flat")
        d = " ".join(f'{"M" if k == 0 else "L"}{x(i):.1f},{y(v):.1f}' for k, (i, v) in enumerate(pts))
        parts.append(f'<path class="tl tl--{cls}" d="{d}"/>')
        for i, v in pts:
            parts.append(f'<circle class="td td--{cls}" cx="{x(i):.1f}" cy="{y(v):.1f}" r="3"/>')
        drawn.append((si, s, pts, cls))

    left_y = declutter([(si, y(pts[0][1])) for si, _, pts, _ in drawn])
    right_y = declutter([(si, y(pts[-1][1])) for si, _, pts, _ in drawn])

    for si, s, pts, cls in drawn:
        i0, v0 = pts[0]
        i1, v1 = pts[-1]
        ly, ry = left_y[si], right_y[si]
        # 標籤被推開時，補一條引線指回原點
        if abs(ly - y(v0)) > 1.5:
            parts.append(f'<path class="lead" d="M{x(i0)-6:.1f},{y(v0):.1f} L{x(i0)-14:.1f},{ly-4:.1f}"/>')
        if abs(ry - y(v1)) > 1.5:
            parts.append(f'<path class="lead" d="M{x(i1)+6:.1f},{y(v1):.1f} L{x(i1)+14:.1f},{ry-4:.1f}"/>')
        parts.append(f'<text class="tlbl" x="{x(i0)-16:.1f}" y="{ly:.1f}" text-anchor="end">'
                     f'{esc(s["name"])} <tspan class="tnum">{v0:+.1f}</tspan></text>')
        parts.append(f'<text class="tlbl tlbl--{cls}" x="{x(i1)+16:.1f}" y="{ry:.1f}">'
                     f'<tspan class="tnum">{v1:+.1f}</tspan> '
                     f'<tspan class="tdelta">({v1-v0:+.1f})</tspan></text>')
    # slope chart 標籤在左右兩端，捲動會讓一端消失 → 手機改用表格（見 trend_table）
    return ('<div class="chart-wrap chart-wrap--wide">'
            f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="{esc(S["trend_h"])}">{"".join(parts)}</svg></div>')


def chart_totals(months_data, S):
    """每月超出合計 + 專案數。"""
    W, H = 900, 130
    pad_l, pad_r, pad_t, pad_b = 46, 46, 22, 30
    iw, ih = W - pad_l - pad_r, H - pad_t - pad_b
    tot = [sum(o["excess"] for o in d["over"]) for d in months_data]
    hi = max(tot) * 1.25
    n = len(months_data)
    bw = min(iw / n * 0.3, 70)
    parts = []
    for i, (d, t) in enumerate(zip(months_data, tot)):
        cx = pad_l + iw * (i + 0.5) / n
        parts.append(f'<rect class="tb" x="{cx-bw/2:.1f}" y="{pad_t+ih-t/hi*ih:.1f}" width="{bw:.1f}" '
                     f'height="{t/hi*ih:.1f}" rx="1.5"/>')
        parts.append(f'<text class="tv" x="{cx:.1f}" y="{pad_t+ih-t/hi*ih-7:.1f}" text-anchor="middle">+{t:.2f}</text>')
        parts.append(f'<text class="colm" x="{cx:.1f}" y="{H-pad_b+18:.1f}" text-anchor="middle">'
                     f'{S["month"](int(d["yyyymm"][4:6]))}　<tspan class="dim">{len(d["over"])}</tspan></text>')
    parts.append(f'<line class="zero" x1="{pad_l}" y1="{pad_t+ih:.1f}" x2="{W-pad_r}" y2="{pad_t+ih:.1f}"/>')
    return scrollable(f'<svg class="chart" viewBox="0 0 {W} {H}" role="img">{"".join(parts)}</svg>')


# ---------- HTML ----------

CSS_BASE = """
/* 結構層 —— 只管佈局與元件骨架。顏色/字體/圓角/陰影全由 themes.py 決定。 */
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  color: var(--ink);
  font-family: var(--sans);
  font-size: 15px;
  line-height: 1.62;
  -webkit-font-smoothing: antialiased;
  background: var(--bg);
}
.wrap { max-width: 980px; margin: 0 auto; padding: clamp(2.25rem,5vw,4.5rem) clamp(1rem,4vw,2rem) 7rem; }

/* Masthead —— 上下雙規線，kicker 用寬字距大寫 */
.kicker { font-size: 0.66rem; letter-spacing: 0.2em; text-transform: uppercase;
  color: var(--accent); font-weight: 700; font-family: var(--sans); }
.masthead h1 { font-size: clamp(2.1rem, 5.2vw, 3.15rem); margin: 0.5rem 0 0.45rem;
  line-height: 1.06; letter-spacing: -0.022em; }
.masthead h1 em { font-style: normal; color: var(--ink-3); font-weight: 400; }
.masthead__sub { color: var(--ink-2); margin: 0; font-size: 0.86rem; font-family: var(--mono);
  letter-spacing: -0.01em; }

section { margin: 3.75rem 0; }
.sec__h { display: flex; align-items: baseline; gap: 0.75rem; margin-bottom: 0.3rem; }
.sec__n { font-family: var(--serif); font-size: 0.95rem; color: var(--accent); font-weight: 600;
  border-bottom: 2px solid var(--accent); line-height: 1; padding-bottom: 2px; }
.sec__h h2 { font-size: 1.62rem; margin: 0; letter-spacing: -0.018em; }
.src { font-size: 0.79rem; color: var(--ink-3); margin: 0 0 1.4rem; max-width: var(--measure); }
.src code, footer code { font-family: var(--mono); font-size: 0.92em; color: var(--ink-2); }
.note { font-size: 0.82rem; color: var(--ink-2); margin: 1.1rem 0 0; }

/* 單一圓角底卡 + overflow:hidden；標頭只是內部 band —— 避免兩個圓角矩形互咬露出凹口 */
.band { background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); overflow: hidden;
  box-shadow: var(--shadow); }
.band__head { background: var(--head-bg); padding: 1.15rem 1.5rem 0.95rem; border-bottom: 1px solid var(--rule); }
.band__head h2 { margin: 0 0 0.2rem; font-size: 1.12rem; letter-spacing: -0.015em; }
.band__head .src { margin: 0; max-width: none; }

/* 圖表 */
.chart { display: block; width: 100%; height: auto; padding: 1.35rem 1.1rem 0.5rem; }
.chart .grid { stroke: var(--rule); stroke-width: 1; }
.chart .ax { fill: var(--ink-3); font-size: 11px; font-family: var(--mono); }
.chart .bar { fill: var(--bar-neutral); }
.chart .bar--over { fill: var(--accent); }
.chart .val { fill: var(--ink-3); font-size: 11px; font-family: var(--serif); font-variant-numeric: tabular-nums; }
.chart .val--over { fill: var(--accent); font-weight: 600; }
.chart .tick { fill: var(--ink-3); font-size: 11px; font-family: var(--sans); }
.chart .tick--cur { fill: var(--accent); font-size: 11px; font-weight: 700; font-family: var(--sans); }
.chart .ref { stroke: var(--accent); stroke-width: 1.5; stroke-dasharray: 5 4; }
.chart .ref__bg { fill: var(--surface); }
.chart .ref__t { fill: var(--accent); font-size: 10.5px; font-weight: 600; font-family: var(--mono); }
.chart .lbl { fill: var(--ink); font-size: 13px; font-family: var(--serif); }
.chart .b-plan { fill: var(--bar-neutral); }
.chart .b-act { fill: var(--accent-2); }
.chart .b-ex { fill: var(--accent); }
.chart .bv { fill: var(--ink-3); font-size: 10.5px; font-family: var(--mono); }
.chart .bv--a { fill: var(--ink-2); }
.chart .ex { fill: var(--accent); font-size: 13.5px; font-weight: 600; font-family: var(--serif);
  font-variant-numeric: tabular-nums; }
.chart .lg { fill: var(--ink-3); font-size: 10px; font-family: var(--mono); }
.chart .lg--a { fill: var(--accent-2); }
.chart .lg--e { fill: var(--accent); }

.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(128px, 1fr)); gap: 1px;
  background: var(--rule); border-top: 1px solid var(--rule); }
.kpis--flat { border: 1px solid var(--rule); border-radius: var(--radius-sm); overflow: hidden; margin: 0.4rem 0 0; }
.kpi { background: var(--surface); padding: 0.8rem 1rem 0.85rem; }
.kpi__k { display: block; font-size: 0.67rem; color: var(--ink-3); letter-spacing: 0.02em; }
.kpi__v { font-family: var(--serif); font-size: 1.5rem; font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em; }
.kpi__u { font-size: 0.68rem; color: var(--ink-3); margin-left: 0.28rem; }
.kpi--neg .kpi__v { color: var(--accent); }

h3.sub { font-size: 0.72rem; letter-spacing: 0.14em; text-transform: uppercase; font-family: var(--sans);
  font-weight: 700; color: var(--ink-3); margin: 2.5rem 0 1rem; padding-bottom: 0.45rem;
  border-bottom: 1px solid var(--rule); }

.card { background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius);
  border-left-width: 3px; margin-bottom: 0.9rem; overflow: hidden;
  box-shadow: var(--shadow-sm); }
.sev--high { border-left-color: var(--accent); }
.sev--mid  { border-left-color: var(--accent-2); }
.sev--low  { border-left-color: var(--rule-2); }
.card__head { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem;
  padding: 1rem 1.35rem 0.8rem; flex-wrap: wrap; }
.card__title { display: flex; align-items: baseline; gap: 0.7rem; }
.rank { font-family: var(--mono); font-size: 0.7rem; color: var(--ink-3); min-width: 1.1em; }
.card__title h3 { margin: 0; font-size: 1.26rem; letter-spacing: -0.015em; }
.card__excess { display: flex; align-items: baseline; gap: 0.35rem; }
.excess { font-family: var(--serif); font-size: 1.85rem; font-weight: 600; color: var(--accent);
  font-variant-numeric: tabular-nums; line-height: 1; letter-spacing: -0.025em; }
.excess__u { font-size: 0.7rem; color: var(--ink-3); }
.excess__pct { font-size: 0.74rem; color: var(--ink-3); margin-left: 0.55rem; font-family: var(--mono); }
.card__body { padding: 0 1.35rem 1rem; }

.roles { display: grid; grid-template-columns: repeat(auto-fit, minmax(172px, 1fr)); gap: 1px;
  background: var(--rule); border: 1px solid var(--rule); border-radius: var(--radius-sm); overflow: hidden;
  margin-bottom: 0.85rem; }
.rl { background: var(--surface); padding: 0.58rem 0.8rem 0.68rem;
  display: grid; grid-template-columns: auto 1fr auto; gap: 0.35rem 0.5rem; align-items: baseline; }
.rl__k { font-size: 0.63rem; letter-spacing: 0.07em; color: var(--ink-3); font-family: var(--mono); }
.rl__v { font-family: var(--serif); font-size: 1rem; font-variant-numeric: tabular-nums; }
.rl__v i { color: var(--ink-3); font-style: normal; padding: 0 0.18em; }
.rl__pct { font-size: 0.72rem; color: var(--ink-3); font-variant-numeric: tabular-nums; text-align: right;
  font-family: var(--mono); }
.rl__bars { grid-column: 1 / -1; display: flex; flex-direction: column; gap: 2px; margin-top: 0.15rem; }
.rl__bars i { display: block; height: 3.5px; border-radius: 2px; min-width: 1px; }
.rl__p { background: var(--bar-neutral); }
.rl__a { background: var(--accent-2); }
.rl--over { background: color-mix(in srgb, var(--accent) 6%, var(--surface)); }
.rl--over .rl__pct { color: var(--accent); font-weight: 600; }
.rl--over .rl__a { background: var(--accent); }
.rl--under { background: color-mix(in srgb, var(--cool) 5%, var(--surface)); }
.rl--under .rl__pct { color: var(--cool); font-weight: 600; }
.rl--under .rl__a { background: var(--cool); }
.rl--empty { opacity: 0.38; }

details { border-top: 1px solid var(--rule); padding-top: 0.65rem; }
summary { cursor: pointer; font-size: 0.75rem; color: var(--ink-3); user-select: none;
  letter-spacing: 0.04em; transition: color 150ms ease; }
summary:hover { color: var(--accent); }
summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 2px; }
.depts { width: 100%; border-collapse: collapse; margin-top: 0.65rem; font-size: 0.8rem; }
.depts td { padding: 0.34rem 0.5rem; border-bottom: 1px solid var(--rule); }
.depts tr:last-child td { border-bottom: none; }
.depts tr.rest td { color: var(--ink-3); font-style: italic; }
.mono { font-family: var(--mono); font-size: 0.92em; }
.dim { color: var(--ink-3); }
.num { text-align: right; font-family: var(--serif); font-variant-numeric: tabular-nums; }

.two { display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); gap: 1.15rem; }
.list { background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); overflow: hidden;
  box-shadow: var(--shadow-sm); }
.list h3 { margin: 0; padding: 0.85rem 1.2rem; font-size: 0.95rem; border-bottom: 1px solid var(--rule);
  background: var(--head-bg); letter-spacing: -0.01em; }
.list ul { list-style: none; margin: 0; padding: 0.5rem 0; }
.list li { display: flex; justify-content: space-between; gap: 1rem; padding: 0.32rem 1.2rem;
  font-size: 0.86rem; }
.list li span:last-child { font-family: var(--serif); font-variant-numeric: tabular-nums; }
.list p { margin: 0; padding: 0.65rem 1.2rem 1rem; font-size: 0.75rem; color: var(--ink-3);
  border-top: 1px solid var(--rule); }

footer { margin-top: 5rem; padding-top: 1.4rem; border-top: 1px solid var(--rule-2);
  font-size: 0.755rem; color: var(--ink-3); line-height: 1.72; max-width: var(--measure); }
footer h4 { font-family: var(--sans); font-size: 0.64rem; letter-spacing: 0.16em; text-transform: uppercase;
  color: var(--ink-2); margin: 1.4rem 0 0.45rem; font-weight: 700; }
footer ul { margin: 0; padding-left: 1.05rem; }
footer li { margin-bottom: 0.3rem; }
footer b { color: var(--ink-2); }

/* 月份導覽 —— 一條帶刻度的規線，不是 tab bar */
.rail { display: flex; align-items: flex-end; gap: 0; margin: 1.6rem 0 0;
  border-bottom: 1px solid var(--rule-2); }
.rail__y { font-family: var(--mono); font-size: 0.68rem; color: var(--ink-3);
  padding: 0 0.9rem 0.55rem 0; letter-spacing: 0.08em; }
.rail button { appearance: none; background: none; border: 0; cursor: pointer;
  font-family: var(--serif); font-size: 1rem; color: var(--ink-3); padding: 0.35rem 0.95rem 0.5rem;
  border-bottom: 2px solid transparent; margin-bottom: -1px; letter-spacing: -0.01em;
  transition: color 160ms ease, border-color 160ms ease; }
.rail button:hover { color: var(--ink); }
.rail button[aria-selected="true"] { color: var(--accent); font-weight: 600;
  border-bottom-color: var(--accent); }
.rail button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 3px; }
.rail__gap { flex: 1; }
.rail__note { font-size: 0.66rem; color: var(--ink-3); padding-bottom: 0.55rem; font-family: var(--mono); }

/* slope / 折線 */
.chart .zero { stroke: var(--rule-2); stroke-width: 1; }
.chart .colrule { stroke: var(--rule); stroke-width: 1; stroke-dasharray: 2 3; }
.chart .colm { fill: var(--ink-2); font-size: 12px; font-family: var(--sans); }
.chart .colm .dim { fill: var(--ink-3); font-size: 10px; }
.chart .tl { fill: none; stroke-width: 1.6; }
.chart .tl--up { stroke: var(--accent); }
.chart .tl--down { stroke: var(--cool); }
.chart .tl--flat { stroke: var(--ink-3); }
.chart .td--up { fill: var(--accent); }
.chart .td--down { fill: var(--cool); }
.chart .td--flat { fill: var(--ink-3); }
.chart .tlbl { fill: var(--ink-2); font-size: 11.5px; font-family: var(--sans); }
.chart .tlbl--up { fill: var(--accent); }
.chart .tlbl--down { fill: var(--cool); }
.chart .tnum { font-family: var(--serif); font-variant-numeric: tabular-nums; font-size: 12.5px; }
.chart .tdelta { font-size: 10.5px; opacity: 0.75; font-family: var(--mono); }
.chart .lead { fill: none; stroke: var(--rule-2); stroke-width: 0.8; }
.chart .tb { fill: var(--accent-2); }
.chart .tv { fill: var(--accent); font-size: 12px; font-weight: 600; font-family: var(--serif);
  font-variant-numeric: tabular-nums; }

.legend { display: flex; gap: 1.1rem; font-size: 0.7rem; color: var(--ink-3); font-family: var(--mono);
  padding: 0 1.1rem 1rem; }
.legend i { display: inline-block; width: 14px; height: 2px; vertical-align: middle;
  margin-right: 0.35rem; }
.legend .i-up { background: var(--accent); }
.legend .i-down { background: var(--cool); }

/* ── 響應式 ────────────────────────────────────────────────
   圖表以 900 寬的 viewBox 繪製。桌機下 100% 寬剛好等於原尺寸；
   窄螢幕下若任其等比縮放，11px 文字會變成 4px —— 故改為捲動。 */
.chart-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
.chart { min-width: 680px; }
.trend-tbl { display: none; }

@media (max-width: 720px) {
  /* 月份列黏在頂端 —— 內容有 4000px+ 長，捲到一半才想切月份時不必再捲回去 */
  .rail { position: sticky; top: 0; z-index: 20; background: var(--surface);
    margin-left: -1rem; margin-right: -1rem; padding: 0 1rem;
    box-shadow: 0 1px 0 var(--rule-2), 0 6px 12px -8px rgba(0,0,0,.18); }
  /* 觸控目標 ≥44px（Apple HIG）—— 原本 38px 太小，手指容易點空 */
  .rail button { padding: 0.75rem 1.15rem; font-size: 1.05rem; min-height: 44px; }
  .rail__y, .rail__note { display: none; }
  .rail__gap { display: none; }

  /* 兩側淡出，提示可捲（開場停在最右，故左緣也要提示） */
  .chart-wrap { position: relative;
    -webkit-mask-image: linear-gradient(90deg, transparent 0, #000 5%, #000 95%, transparent 100%);
            mask-image: linear-gradient(90deg, transparent 0, #000 5%, #000 95%, transparent 100%); }
  /* slope chart 標籤在左右兩端，捲動必然失去一端 → 換成表格 */
  .chart-wrap--wide { display: none; }
  .trend-tbl { display: table; width: 100%; border-collapse: collapse;
    font-size: 0.8rem; margin: 0.4rem 0 0.2rem; }
  .trend-tbl th { font-size: 0.64rem; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--ink-3); font-weight: 600; text-align: right; padding: 0.5rem 0.5rem 0.4rem;
    border-bottom: 1px solid var(--rule-2); }
  .trend-tbl th:first-child { text-align: left; }
  .trend-tbl td { padding: 0.42rem 0.5rem; border-bottom: 1px solid var(--rule); }
  .trend-tbl .d-up { color: var(--accent); font-weight: 600; }
  .trend-tbl .d-down { color: var(--cool); font-weight: 600; }
  .legend { display: none; }
  .wrap { padding-left: 1rem; padding-right: 1rem; }
  section { margin: 2.75rem 0; }
  .card__head { gap: 0.4rem; }
  .card__excess { width: 100%; justify-content: flex-start; }
  /* 5 格 KPI 在 2 欄下會留一格空白 → 手機改單欄橫式（label 左、值右） */
  .kpis, .kpis--flat { grid-template-columns: 1fr; }
  .kpi { display: flex; align-items: baseline; justify-content: space-between;
    gap: 0.75rem; padding: 0.6rem 1rem; }
  .kpi__k { flex: 1; }
  .kpi__v { font-size: 1.3rem; }
  .roles { grid-template-columns: 1fr; }
  .depts { font-size: 0.74rem; }
  .depts td:first-child { display: none; }   /* 部門代碼在手機上讓位給名稱 */
  footer { max-width: none; }
}
@media (max-width: 420px) {
  .masthead h1 { font-size: 1.9rem; }
  .trend-tbl { font-size: 0.74rem; }
  .trend-tbl th, .trend-tbl td { padding-left: 0.25rem; padding-right: 0.25rem; }
}

/* 月份切換 */
[data-month] { display: none; }
[data-month].is-on { display: block; }
@media (prefers-reduced-motion: no-preference) {
  [data-month].is-on { animation: fade 320ms ease backwards; }
  @keyframes fade { from { opacity: 0; } }
  .reveal { animation: rise 620ms cubic-bezier(0.16, 1, 0.3, 1) backwards; }
  @keyframes rise { from { opacity: 0; transform: translateY(10px); } }
}
@media print {
  body { background: #fff; }
  .card, .band, .list { box-shadow: none; break-inside: avoid; }
  details, .rail { display: none; }
  [data-month] { display: block !important; }
}
"""


def mfg_total(review_file, cfg):
    """被排除的製造人力總量 —— 必須明示，不可靜默過濾。"""
    bad = tuple(cfg["plan_exclusions"]["exclude_dept_prefix"])
    wb = openpyxl.load_workbook(review_file, data_only=True, read_only=True)
    total = 0.0
    for r in find_sheet(wb, r"\d{6}-ProjectCode人力").iter_rows(min_row=2, values_only=True):
        if r[0] and str(r[0]).startswith(bad) and isinstance(r[3], (int, float)):
            total += r[3]
    wb.close()
    return total


def render_month(d, cfg, S, lang):
    """單月區塊：編制曲線 + 超配 + plan=0。"""
    th = cfg["thresholds"]
    top_n = th["display"]["top_depts"]
    yyyymm = d["yyyymm"]
    year, mon = int(yyyymm[:4]), int(yyyymm[4:6])
    ym = S["ym"](year, mon)
    over, other, skipped = d["over"], d["other"], d["skipped"]

    hc_html = ""
    if d["headcount"]:
        hc = d["headcount"]
        est = hc["establishment"][0]
        gaps = [(m, g) for m, g in zip(hc["months"], hc["gap"]) if isinstance(g, (int, float))]
        gmap = dict(gaps)
        neg = [(m, g) for m, g in gaps if g < 0]
        first_neg = neg[0] if neg else None
        worst = min(gaps, key=lambda x: x[1]) if gaps else None
        cur_gap = gmap.get(mon, 0)
        hc_html = f"""
    <section class="band">
      <div class="band__head">
        <h2>{esc(S['hc_h'])}</h2>
        <p class="src">{S['hc_src'].format(est=est)}</p>
      </div>
      {chart_headcount(hc, yyyymm, S)}
      <div class="kpis">
        <div class="kpi"><span class="kpi__k">{esc(S['k_est'])}</span>
          <span class="kpi__v">{est:.0f}</span><span class="kpi__u">{esc(S['u_people'])}</span></div>
        <div class="kpi"><span class="kpi__k">{esc(S['k_planned'].format(ym=ym))}</span>
          <span class="kpi__v">{est - cur_gap:.1f}</span><span class="kpi__u">{esc(S['u_people'])}</span></div>
        <div class="kpi kpi--neg"><span class="kpi__k">{esc(S['k_gap'].format(ym=ym))}</span>
          <span class="kpi__v">{cur_gap:+.1f}</span><span class="kpi__u">{esc(S['u_people'])}</span></div>
        <div class="kpi kpi--neg"><span class="kpi__k">{esc(S['k_first_neg'])}</span>
          <span class="kpi__v">{S['month'](first_neg[0]) if first_neg else '—'}</span>
          <span class="kpi__u">{f'{first_neg[1]:+.1f}' if first_neg else ''}</span></div>
        <div class="kpi kpi--neg"><span class="kpi__k">{esc(S['k_worst'])}</span>
          <span class="kpi__v">{worst[1]:+.1f}</span>
          <span class="kpi__u">{S['month'](worst[0])}</span></div>
      </div>
    </section>"""

    cards = ""
    for i, it in enumerate(over):
        pct = it["actual"] / it["plan"] * 100
        sev = "sev--high" if it["excess"] >= 3 else ("sev--mid" if it["excess"] >= 1 else "sev--low")
        cards += f"""
      <article class="card {sev}">
        <header class="card__head">
          <div class="card__title"><span class="rank">{i+1:02d}</span><h3>{esc(it['name'])}</h3></div>
          <div class="card__excess">
            <span class="excess">+{fmt(it['excess'])}</span>
            <span class="excess__u">FTE</span>
            <span class="excess__pct">{fmt(it['plan'],1)} → {fmt(it['actual'])} · {pct:.0f}%</span>
          </div>
        </header>
        <div class="card__body">
          <div class="roles">{chart_roles(it['plan_roles'], it['actual_roles'])}</div>
          <details><summary>{esc(S['depts'])}</summary>
            <table class="depts"><tbody>{dept_rows(d['by_dept'], it['key'], d['dept_name'], top_n, S)}</tbody></table>
          </details>
        </div>
      </article>"""

    zeroed = [o for o in other if o["kind"] == "zeroed"]
    unplanned = [o for o in other if o["kind"] == "unplanned"]

    def li(items):
        return "".join(f'<li><span>{esc(o["name"])}</span><span>{fmt(o["actual"])}</span></li>'
                       for o in items)

    skipped_html = ""
    if skipped:
        skipped_html = '<p class="note">' + S["skipped"].format(
            t=fmt(th["over_allocation"]["min_excess_fte"], 1),
            items="、".join(f'{esc(s["name"])} +{fmt(s["excess"])}' for s in skipped)) + "</p>"

    cands = cfg["aliases"].get("candidates") or {}
    return f"""
  <div data-month="{yyyymm}">
  {hc_html}

  <section>
    <div class="sec__h"><span class="sec__n">01</span><h2>{esc(S['over_h'])}</h2></div>
    <p class="src">{S['over_src']}</p>
    {chart_over(over, S)}
    <div class="kpis kpis--flat">
      <div class="kpi"><span class="kpi__k">{esc(S['k_count'])}</span>
        <span class="kpi__v">{len(over)}</span><span class="kpi__u">{esc(S['u_projects'])}</span></div>
      <div class="kpi"><span class="kpi__k">{esc(S['k_plan_tot'])}</span>
        <span class="kpi__v">{fmt(sum(o['plan'] for o in over),1)}</span><span class="kpi__u">FTE</span></div>
      <div class="kpi"><span class="kpi__k">{esc(S['k_act_tot'])}</span>
        <span class="kpi__v">{fmt(sum(o['actual'] for o in over),1)}</span><span class="kpi__u">FTE</span></div>
      <div class="kpi kpi--neg"><span class="kpi__k">{esc(S['k_ex_tot'])}</span>
        <span class="kpi__v">+{fmt(sum(o['excess'] for o in over))}</span><span class="kpi__u">FTE</span></div>
    </div>
    <h3 class="sub">{esc(S['by_project'])}</h3>
    {cards}
    {skipped_html}
  </section>

  <section>
    <div class="sec__h"><span class="sec__n">02</span><h2>{esc(S['zero_h'])}</h2></div>
    <p class="src">{S['zero_src']}</p>
    <div class="two">
      <div class="list">
        <h3>{esc(S['zeroed_h'])}</h3>
        <ul>{li(zeroed)}</ul>
        <p>{S['total'].format(v=fmt(sum(o['actual'] for o in zeroed)))}</p>
      </div>
      <div class="list">
        <h3>{esc(S['unplanned_h'])}</h3>
        <ul>{li(unplanned)}</ul>
        <p>{S['total_pending'].format(v=fmt(sum(o['actual'] for o in unplanned)), n=len(cands))}</p>
      </div>
    </div>
  </section>
  </div>"""


def render_trend(months_data, S):
    """跨月：超出合計 + 逐專案 slope chart。"""
    if len(months_data) < 2:
        return ""
    months = [d["yyyymm"] for d in months_data]
    keys = {o["key"] for d in months_data for o in d["over"]}       # 任一月曾超配
    series = []
    for k in keys:
        vals = [(d["yyyymm"], (d["all"][k]["excess"] if k in d["all"] else None)) for d in months_data]
        if all(v is None for _, v in vals):
            continue
        name = next(d["all"][k]["name"] for d in months_data if k in d["all"])
        series.append({"key": k, "name": name, "values": vals})
    # 依最新月的超出量排序（None 排最後）
    series.sort(key=lambda s: -(s["values"][-1][1] if s["values"][-1][1] is not None else -99))

    movers = []
    for s in series:
        pts = [v for _, v in s["values"] if v is not None]
        if len(pts) >= 2:
            movers.append((s["name"], pts[-1] - pts[0]))
    up = max(movers, key=lambda x: x[1]) if movers else None
    down = min(movers, key=lambda x: x[1]) if movers else None

    return f"""
  <section class="reveal" style="animation-delay:100ms">
    <div class="sec__h"><span class="sec__n">00</span><h2>{esc(S['trend_h'])}</h2></div>
    <p class="src">{S['trend_src']}</p>
    <div class="band">
      <div class="band__head">
        <h2>{esc(S['totals_h'])}</h2>
        <p class="src">{esc(S['totals_src'])}</p>
      </div>
      {chart_totals(months_data, S)}
    </div>
    <div class="band" style="margin-top:1.15rem">
      {chart_trend(months, series, S)}
      {trend_table(months, series, S)}
      <div class="legend">
        <span><i class="i-up"></i>{esc(S['lg_up'])}</span>
        <span><i class="i-down"></i>{esc(S['lg_down'])}</span>
      </div>
      <div class="kpis">
        <div class="kpi kpi--neg"><span class="kpi__k">{esc(S['mover_up'])}</span>
          <span class="kpi__v">{esc(up[0]) if up else '—'}</span>
          <span class="kpi__u">{f'{up[1]:+.2f} FTE' if up else ''}</span></div>
        <div class="kpi"><span class="kpi__k">{esc(S['mover_down'])}</span>
          <span class="kpi__v">{esc(down[0]) if down else '—'}</span>
          <span class="kpi__u">{f'{down[1]:+.2f} FTE' if down else ''}</span></div>
      </div>
    </div>
  </section>"""


def render_all(months_data, cfg, lang, theme="editorial"):
    S = strings(lang)
    cur = months_data[-1]
    year, mon = int(cur["yyyymm"][:4]), int(cur["yyyymm"][4:6])
    ym = S["ym"](year, mon)
    cands = cfg["aliases"].get("candidates") or {}
    norm_n = len({k.lower() for k in (cfg["aliases"].get("confirmed") or {})})

    rail = "".join(
        f'<button role="tab" aria-selected="{"true" if d is cur else "false"}" '
        f'data-go="{d["yyyymm"]}">{S["month"](int(d["yyyymm"][4:6]))}</button>'
        for d in months_data)

    title = S["title"].format(ym=ym) if "{ym}" in S["title"] else S["title"]
    sub_ym = "" if "{ym}" in S["title"] else f'<em id="ym"> · {esc(ym)}</em>'

    return f"""<!doctype html>
<html lang="{S['html_lang']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(S['doc_title'].format(ym=ym))}</title>
<style>{CSS_BASE}
/* ── theme: {theme} ── */{theme_css(theme)}</style>
</head>
<body>
<div class="wrap">
  <header class="masthead reveal">
    <div class="kicker">{esc(S['kicker'])}</div>
    <h1>{esc(title)}{sub_ym}</h1>
    <p class="masthead__sub">{esc(S['source'])} {esc(cur['review_file'])} ·
       2026_plan.xlsx → 人力分攤-updated</p>
  </header>

  <nav class="rail reveal" role="tablist" aria-label="{esc(S['trend_h'])}" style="animation-delay:60ms">
    <span class="rail__y">{esc(S['rail_y'])}</span>
    {rail}
    <span class="rail__gap"></span>
    <span class="rail__note">{esc(S['rail_note'].format(n=len(months_data)))}</span>
  </nav>

  {render_trend(months_data, S)}

  {"".join(render_month(d, cfg, S, lang) for d in months_data)}

  <footer>
    <h4>{esc(S['method_h'])}</h4>
    <ul>
      <li>{S['m1'].format(ym='NNNN')}</li>
      <li>{S['m2'].format(p=mon-1, c=mon)}</li>
      <li>{S['m3']}</li>
      <li>{S['m4'].format(mfg=fmt(cur['excluded_mfg'],1))}</li>
    </ul>
    <h4>{esc(S['notes_h'])}</h4>
    <ul>
      <li>{S['n1'].format(n=norm_n, c=len(cands),
                          cands=esc(", ".join(f"{k}→{v}" for k, v in cands.items())))}</li>
      <li>{S['n2'].format(ym=ym)}</li>
    </ul>
    <p style="margin-top:1.4rem"><code>src/build_review.py --lang {lang}</code></p>
  </footer>
</div>
<script>
(function () {{
  var rail = document.querySelector('.rail');
  var panes = document.querySelectorAll('[data-month]');

  function show(m, scroll) {{
    panes.forEach(function (p) {{ p.classList.toggle('is-on', p.dataset.month === m); }});
    rail.querySelectorAll('button').forEach(function (b) {{
      b.setAttribute('aria-selected', String(b.dataset.go === m));
    }});
    var ym = document.getElementById('ym');
    var btn = rail.querySelector('[data-go="' + m + '"]');
    if (ym && btn) ym.textContent = ' · ' + btn.textContent + ' ' + m.slice(0, 4);
    // file:// 開啟時 replaceState 在部分瀏覽器會丟 SecurityError —— 收件人多半是雙擊開檔，
    // 不 catch 的話整個切換功能會死。網址記錄只是加分項，不值得為它賠掉主功能。
    try {{ history.replaceState(null, '', '#' + m); }} catch (e) {{}}

    // ⚠ 切換後必須捲到內容。月份區塊在趨勢區下方約 1000px 處 ——
    //   手機視窗只有 ~840px 高，不捲的話點下去畫面毫無變化，看起來就像「切換壞了」。
    //   功能是好的、回饋是壞的，比功能壞更難察覺。
    if (scroll) {{
      var pane = document.querySelector('[data-month="' + m + '"]');
      if (pane) {{
        var top = pane.getBoundingClientRect().top + window.pageYOffset - railHeight() - 8;
        try {{
          window.scrollTo({{ top: top, behavior: 'smooth' }});
        }} catch (e) {{
          window.scrollTo(0, top);          // 舊瀏覽器不支援 options 物件
        }}
      }}
    }}
  }}

  function railHeight() {{
    // 月份列在手機上是 sticky，捲動目標要扣掉它的高度，否則標題會被蓋住
    return getComputedStyle(rail).position === 'sticky' ? rail.offsetHeight : 0;
  }}

  rail.addEventListener('click', function (e) {{
    var b = e.target.closest('[data-go]');
    if (b) show(b.dataset.go, true);
  }});

  var init = location.hash.slice(1);
  show(document.querySelector('[data-month="' + init + '"]') ? init
       : panes[panes.length - 1].dataset.month, false);

  // 12 個月的長條圖在手機上要捲才看得完。預設停在最左（Jan），
  // 使用者只看到上半年、以為圖表被截斷 → 開場就捲到最右（近月）。
  function parkCharts() {{
    document.querySelectorAll('.chart-wrap').forEach(function (w) {{
      if (w.scrollWidth > w.clientWidth + 4) w.scrollLeft = w.scrollWidth;
    }});
  }}
  parkCharts();
  window.addEventListener('resize', parkCharts);
  rail.addEventListener('click', function () {{ setTimeout(parkCharts, 50); }});
}})();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="BU10 人力執行 review — 實際 vs 計畫")
    ap.add_argument("months", nargs="*", help="要納入的月份（預設：data/raw 裡全部）")
    ap.add_argument("--lang", default="zh", choices=["zh", "en"])
    ap.add_argument("--theme", default="editorial", choices=list(THEMES),
                    help="; ".join(f'{k}: {v["label"]}' for k, v in THEMES.items()))
    ap.add_argument("--all-themes", action="store_true", help="產出全部主題供比較")
    a = ap.parse_args()

    cfg = load_config()
    norm = Normalizer(cfg["aliases"])
    lang = a.lang
    months = a.months or available_months()
    if not months:
        raise SystemExit(f"{RAW} 裡找不到 NNNNNN_*.xlsx")

    months_data = [build_month(m, cfg, norm) for m in months]

    OUT.mkdir(exist_ok=True)
    lang_sfx = "" if lang == "zh" else f"_{lang}"
    themes = list(THEMES) if a.all_themes else [a.theme]
    dests = []
    for t in themes:
        t_sfx = "" if t == "editorial" and not a.all_themes else f"_{t}"
        dest = OUT / f"review{lang_sfx}{t_sfx}.html"
        dest.write_text(render_all(months_data, cfg, lang, t), encoding="utf-8")
        dests.append(dest)

    for d in months_data:
        tot = sum(o["excess"] for o in d["over"])
        print(f"[{d['yyyymm']}] over-plan {len(d['over'])} projects, total +{tot:.2f} FTE")
        for o in d["over"]:
            print(f"     {o['name']:<16}{o['plan']:6.1f} → {o['actual']:6.2f}  ({o['excess']:+.2f})")
    if len(months_data) >= 2:
        a, b = months_data[0], months_data[-1]
        print(f"\n{a['yyyymm']} → {b['yyyymm']} 超出合計 "
              f"{sum(o['excess'] for o in a['over']):+.2f} → {sum(o['excess'] for o in b['over']):+.2f}")
    for d in dests:
        print(f"→ {d}")


if __name__ == "__main__":
    main()
