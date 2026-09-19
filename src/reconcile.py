"""驗證關卡 —— 每月重跑後必看。

設計原則（來自 AGENTS.md 第一守則）：
  1. 失敗要大聲：未對照的專案不得靜默丟棄，須彙總顯示。
  2. 只警告、不擋建置（需求方決定 2026-07-15）。
  3. 每個 fallback／預設值都是「編出來的東西」的入口 —— 必須能回答「這條路被走過幾次」。
  4. plan 側必須有對等的驗證：三項 actual 側迴歸測試全過，但六次結論翻轉全在 plan 側。

用法：由 build_review.py 自動呼叫，輸出 out/recon_YYYYMM.md
"""
import re
from collections import defaultdict

import openpyxl

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


class Check:
    """一個驗證關卡的結果。"""

    def __init__(self, name, status, summary, detail=None, why=None):
        self.name = name
        self.status = status
        self.summary = summary
        self.detail = detail or []
        self.why = why          # 為何這個關卡存在（踩過的坑）

    @property
    def icon(self):
        return {PASS: "✅", WARN: "⚠️", FAIL: "❌"}[self.status]


# ── actual 側 ────────────────────────────────────────────────

def check_fu_pivot(wb, yyyymm, fu_by_project):
    """FU 側迴歸：用 dashboard 的 unit_role 規則算出的 FU RD，須與人工樞紐完全吻合。

    這是本專案最有價值的關卡 —— 樞紐是現有人工流程的產物，
    是**別人用不同方法算出的同一個答案**。202606 首次驗證為 19/19、誤差 0。

    ⚠ 比對的是 `dept_org != project_bu` 這條規則的結果，不是「讀不讀得對某張表」。
      會出錯的是規則，不是讀取。已實測本關卡能抓到兩種曾犯過的錯誤規則：
        - 用「來源分頁」推斷 → 誤判 3.9 FTE
        - 用「部門首字 F」推斷 → Foxtrot14 少算 3.55、Delta3-7 少算 0.55（漏掉其他 BU 的支援）
    """
    sheet = None
    for n in wb.sheetnames:
        if re.match(r"\s*Project \d+ vs\.?\s*\d+", n):
            sheet = wb[n]
            break
    if sheet is None:
        return Check("FU 側迴歸（對照人工樞紐）", WARN,
                     "找不到 `Project N vs.N+1` 分頁 —— 本月無法對照",
                     why="分頁名每月變動且格式不一（有的多空格）")

    pivot = {}
    for r in sheet.iter_rows(min_row=5, values_only=True):
        if r[0] and str(r[0]).strip() != "總計" and isinstance(r[1], (int, float)):
            pivot[str(r[0]).strip()] = r[1]
    if not pivot:
        return Check("FU 側迴歸（對照人工樞紐）", WARN, "樞紐分頁讀不到資料")

    diffs = []
    for name, want in pivot.items():
        got = fu_by_project.get(name, 0.0)
        if abs(got - want) > 0.01:
            diffs.append(f"`{name}`：樞紐 {want:.4f} vs 本管線 {got:.4f}（差 {got-want:+.4f}）")
    n = len(pivot)
    if diffs:
        return Check("FU 側迴歸（對照人工樞紐）", FAIL,
                     f"**{len(diffs)}/{n} 筆不符** —— ingest 的 FU 讀取邏輯可能壞了",
                     diffs[:10],
                     why="人工樞紐是別人用不同方法算的同一個答案，不符即代表其中一方錯了")
    return Check("FU 側迴歸（對照人工樞紐）", PASS,
                 f"{n}/{n} 逐筆吻合，誤差 0（合計 {sum(pivot.values()):.2f} FTE）",
                 why="人工樞紐是別人用不同方法算的同一個答案")


def check_bu_detail(wb, yyyymm):
    """BU 側迴歸：`人力明細` 聚合須等於 `ProjectCode人力` 的 D 組。

    兩張表由 EIS 各自產出，理應一致。202606 首次驗證為 2,890/2,890、合計 1,737.00。
    """
    det = defaultdict(float)
    for r in wb[f"{yyyymm}-人力明細"].iter_rows(min_row=2, values_only=True):
        if r[0] and r[4] and isinstance(r[6], (int, float)):
            det[(r[0], r[4])] += r[6]
    pc = defaultdict(float)
    for r in wb[f"{yyyymm}-ProjectCode人力"].iter_rows(min_row=2, values_only=True):
        if r[0] and r[2] and isinstance(r[3], (int, float)) and r[6] == "D":
            pc[(r[0], r[2])] += r[3]

    only_det = set(det) - set(pc)
    only_pc = set(pc) - set(det)
    diffs = [k for k in set(det) & set(pc) if abs(det[k] - pc[k]) > 0.005]
    if only_det or only_pc or diffs:
        d = []
        if only_det:
            d.append(f"只在 `人力明細`：{len(only_det)} 組")
        if only_pc:
            d.append(f"只在 `ProjectCode人力` D 組：{len(only_pc)} 組")
        if diffs:
            d += [f"`{k[0]}`／`{k[1]}`：明細 {det[k]:.3f} vs D組 {pc[k]:.3f}" for k in diffs[:6]]
        return Check("BU 側迴歸（明細 vs ProjectCode人力 D 組）", FAIL,
                     f"兩表不一致（明細 {sum(det.values()):.2f} vs D組 {sum(pc.values()):.2f} FTE）", d)
    return Check("BU 側迴歸（明細 vs ProjectCode人力 D 組）", PASS,
                 f"{len(det)}/{len(det)} 逐筆吻合，合計 {sum(det.values()):.2f} FTE",
                 why="兩張表由 EIS 各自產出，理應一致")


def check_alloc_formula(wb, yyyymm):
    """分攤邏輯：Y 組的『分攤合計 ÷ 主管填寫人力』須為 1.00。

    證明一個部門的人力攤到各專案後加總 = 它的人數，即沒有重複計算。
    """
    pct = list(wb[f"{yyyymm}-百分比分攤"].iter_rows(values_only=True))
    hdr = list(pct[0])
    im, imx = hdr.index("主管填寫人力"), hdr.index("明細")
    mp = {r[1]: r[im] for r in pct[1:] if r[1] and r[imx] == "Y"}
    y = defaultdict(float)
    for r in wb[f"{yyyymm}-ProjectCode人力"].iter_rows(min_row=2, values_only=True):
        if r[0] and isinstance(r[3], (int, float)) and r[6] == "Y":
            y[r[0]] += r[3]

    bad, n = [], 0
    for d, m in mp.items():
        if not isinstance(m, (int, float)) or m <= 0:
            continue
        n += 1
        ratio = y.get(d, 0) / m
        if abs(ratio - 1.0) > 0.02:
            bad.append(f"`{d}`：分攤 {y.get(d,0):.3f} ÷ 主管填寫 {m} = {ratio:.3f}")
    if bad:
        return Check("Y 組分攤公式（無重複計算）", WARN,
                     f"{len(bad)}/{n} 個部門的比值 ≠ 1.00", bad[:8])
    return Check("Y 組分攤公式（無重複計算）", PASS, f"{n}/{n} 個部門比值皆為 1.00",
                 why="證明部門人力攤到各專案後加總 = 它的人數，沒有重複計算")


def check_fallback(wb, yyyymm, bu):
    """Fallback 曝險：多少 FTE 的角色是靠『部門首字 F』猜的？

    ⚠ 這條 fallback 平常不發作、發作時無聲。若某部門從 `百分比分攤` 消失，
      它會默默接手判定而不報錯。程式裡的每條 fallback 都是「編出來的東西」的入口。
    """
    pct = list(wb[f"{yyyymm}-百分比分攤"].iter_rows(values_only=True))
    orgs = {r[1] for r in pct[1:] if r[1]}
    total, fb = 0.0, defaultdict(float)
    for r in wb[f"{yyyymm}-人力明細"].iter_rows(min_row=2, values_only=True):
        if r[10] and isinstance(r[6], (int, float)) and r[13] == bu and not str(r[0]).startswith("H"):
            total += r[6]
            if r[0] not in orgs:
                fb[(r[0], str(r[1])[:30])] += r[6]
    for r in wb[f"{yyyymm}-ProjectCode人力"].iter_rows(min_row=2, values_only=True):
        if r[6] == "Y" and r[7] and isinstance(r[3], (int, float)) and r[10] == bu \
                and not str(r[0]).startswith("H"):
            total += r[3]
            if r[0] not in orgs:
                fb[(r[0], str(r[1])[:30])] += r[3]

    amt = sum(fb.values())
    pctg = amt / total * 100 if total else 0
    why = "fallback 平常不發作、發作時無聲；若部門從 `百分比分攤` 消失，它會默默接手判定"
    if not fb:
        return Check("Fallback 曝險（角色判定）", PASS,
                     f"**零 fallback** —— {bu} 的 {total:.2f} FTE 角色判定全部有據", why=why)
    detail = [f"`{d}` {n} → 首字 `{d[0]}` → 判為 {'FU RD' if d[0]=='F' else 'BU RD/PM'}：{v:.3f} FTE"
              for (d, n), v in sorted(fb.items(), key=lambda x: -x[1])[:8]]
    st = FAIL if pctg > 5 else WARN
    return Check("Fallback 曝險（角色判定）", st,
                 f"**{amt:.2f} FTE（{pctg:.1f}%）靠部門首字猜的** —— 這些部門不在 `百分比分攤` 表中",
                 detail, why=why)


# ── plan 側（歷來的盲區）─────────────────────────────────────

def check_plan_internal(plan_path, yyyymm):
    """plan 側自我驗證。

    ⚠ 三項 actual 側迴歸測試全過，但六次結論翻轉全在 plan 側 ——
      護城河曾挖在城堡的另一邊。這組關卡就是補那一側。
    """
    wb = openpyxl.load_workbook(plan_path, data_only=True)
    ws = wb["人力分攤-updated"]
    rows = list(ws.iter_rows(values_only=True))
    hdr = list(rows[0])
    want = f"{yyyymm[:4]}-{yyyymm[4:6]}"
    ci = next((j for j, h in enumerate(hdr) if h and want in str(h)), None)
    if ci is None:
        wb.close()
        return [Check("plan 月份欄位", FAIL, f"找不到 {want} 的欄位")]

    checks = []

    # A. 列122（全專案加總）== 列128（三層加總）
    # ⚠ 搜尋須從資料列之後開始：C 欄是『人力分攤單位』，每個專案列都有 FU RD/BU RD/BU PM，
    #   從列 115 起搜「BU PM」會命中最後一個專案列而非彙總列。
    def row_by_label(lbl, start=120):
        for r in range(start, 175):
            if str(ws.cell(r, 3).value or "").strip() == lbl:
                return r
        return None

    r122 = row_by_label("Total 人力", 118)
    r128 = None
    for r in range(r122 + 1 if r122 else 120, 140):
        if str(ws.cell(r, 3).value or "").strip() == "Total 人力":
            r128 = r
            break
    if r122 and r128:
        a, b = ws.cell(r122, ci + 1).value, ws.cell(r128, ci + 1).value
        ok = isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) < 0.02
        checks.append(Check(
            f"plan 自我驗證：列{r122}（全專案加總）== 列{r128}（三層加總）",
            PASS if ok else FAIL,
            f"{a:.2f} vs {b:.2f}" if ok else f"**不符**：{a} vs {b}",
            why="plan 檔自己的兩個總計欄位，不符即代表專案列或三層 SUMIF 有問題"))

    # B. 產品別小計 == 該產品別各專案加總
    SUB = {"dior", "unicorn", "trenton", "new segment", "bd", "dms", "others"}
    byprod, subtot = defaultdict(float), defaultdict(float)
    for r in rows[1:]:
        if not r[1] or not r[2] or r[2] == "人力編列 BU RD+PM":
            continue
        n = str(r[1]).strip()
        v = r[ci] if isinstance(r[ci], (int, float)) else 0
        if n.lower() in SUB:
            subtot[n] += v
        elif r[0]:
            byprod[str(r[0]).strip().lower()] += v

    bad = []
    for k, v in subtot.items():
        calc = byprod.get(k.lower(), 0)
        if abs(calc - v) > 0.02:
            bad.append(f"`{k}`：小計 **{v:.2f}** vs 各專案加總 **{calc:.2f}**（差 {v-calc:+.2f}）")
    why_b = ("小計列是 `=[1]人力樞紐!H36` 這類**指向另一個活頁簿的外部參照**；"
             "專案列加了新專案後該參照不會自動更新")
    if bad:
        checks.append(Check("plan 自我驗證：產品別小計 == 各專案加總", WARN,
                            f"**{len(bad)}/{len(subtot)} 個產品別對不上** —— 小計列已過時，"
                            f"見 `docs/open-questions.md` C4",
                            bad + ["", "**本 dashboard 用專案列**（與 `25 vs. 26 人力` 分頁一致），"
                                   "不受此影響。"], why=why_b))
    else:
        checks.append(Check("plan 自我驗證：產品別小計 == 各專案加總", PASS,
                            f"{len(subtot)}/{len(subtot)} 相符", why=why_b))

    # C. 編制檢核區塊：列130 == 列126+列127、列131 == 列129-列130
    r129, r130, r131 = (row_by_label("BU RD+ PM 人力"), row_by_label("人力編列 BU RD+PM"),
                        row_by_label("不足/超出人力"))
    if r129 and r130 and r131:
        est = ws.cell(r129, ci + 1).value
        planned = ws.cell(r130, ci + 1).value
        gap = ws.cell(r131, ci + 1).value
        ok = all(isinstance(x, (int, float)) for x in (est, planned, gap)) \
            and abs((est - planned) - gap) < 0.02
        checks.append(Check(
            f"plan 自我驗證：列{r131}（不足/超出）== 列{r129}（編制）− 列{r130}（編列）",
            PASS if ok else FAIL,
            f"{gap:+.2f} = {est} − {planned:.2f}" if ok else f"**不符**：{est} − {planned} ≠ {gap}",
            why=("初版把列130『人力**編列**』誤當編制，得出「編制已貼滿 205.8/205.7」"
                 "—— 那是把 205.75 減 205.75。列129 硬編的 203 才是編制。")))
    wb.close()
    return checks


# ── 涵蓋率 ───────────────────────────────────────────────────

def check_coverage(over, other, skipped, cands, excluded_mfg):
    """未對照專案與排除量 —— 失敗要大聲，不可靜默丟棄。"""
    checks = []
    unplanned = [o for o in other if o["kind"] == "unplanned"]
    amt = sum(o["actual"] for o in unplanned)
    checks.append(Check(
        "未對照專案（plan 找不到）", WARN if unplanned else PASS,
        f"**{len(unplanned)} 個專案、{amt:.2f} FTE** 在 plan 裡找不到" if unplanned
        else "全部專案都對得上 plan",
        [f"`{o['name']}`：{o['actual']:.2f} FTE" for o in unplanned[:10]],
        why=("`人力分攤-updated` 無 `PROJECTCODE` 欄，plan 與 actual 以名稱比對。"
             "名字對不上的專案會假性落入此清單 —— 根治方法見 open-questions C3。")))

    if cands:
        checks.append(Check(
            "待確認別名", WARN,
            f"**{len(cands)} 條候選別名未套用** —— 上面的未對照清單可能因此虛胖",
            [f"`{k}` → `{v}`" for k, v in cands.items()],
            why="KILO10/12 曾因未對照而被判為「編了 27 人卻沒動」的頭號異常，實為正常執行 77%/81%"))

    checks.append(Check(
        "製造排除量（須明示）", PASS,
        f"已排除 **{excluded_mfg:.2f} FTE**（部門代碼 H 開頭，產線）",
        why="排除量必須明示，不可靜默過濾"))
    return checks


# ── 報告 ─────────────────────────────────────────────────────

def run(review_path, plan_path, yyyymm, ctx):
    """跑完所有關卡，回傳 (checks, markdown)。"""
    wb = openpyxl.load_workbook(review_path, data_only=True)
    checks = [
        check_fu_pivot(wb, yyyymm, ctx["fu_by_project"]),
        check_bu_detail(wb, yyyymm),
        check_alloc_formula(wb, yyyymm),
        check_fallback(wb, yyyymm, ctx["bu"]),
    ]
    wb.close()
    checks += check_plan_internal(plan_path, yyyymm)
    checks += check_coverage(ctx["over"], ctx["other"], ctx["skipped"],
                             ctx["candidates"], ctx["excluded_mfg"])
    return checks, to_markdown(checks, yyyymm)


def to_markdown(checks, yyyymm):
    n_fail = sum(1 for c in checks if c.status == FAIL)
    n_warn = sum(1 for c in checks if c.status == WARN)
    n_pass = sum(1 for c in checks if c.status == PASS)
    ym = f"{yyyymm[:4]}/{yyyymm[4:6]}"

    L = [f"# 驗證報告 — {ym}", ""]
    L.append(f"**{n_pass} 通過 · {n_warn} 警告 · {n_fail} 失敗**")
    L.append("")
    if n_fail:
        L.append("> ❌ **有失敗的關卡 —— 數字可能是錯的，先查清楚再用。**")
    elif n_warn:
        L.append("> ⚠️ 有警告。警告不擋建置（需求方決定 2026-07-15），但每一條都該看過。")
    else:
        L.append("> ✅ 全部通過。")
    L += ["", "| | 關卡 | 結果 |", "|---|---|---|"]
    for c in checks:
        L.append(f"| {c.icon} | {c.name} | {c.summary} |")
    L += ["", "---", ""]

    for c in checks:
        if c.status == PASS and not c.detail:
            continue
        L.append(f"## {c.icon} {c.name}")
        L.append("")
        L.append(c.summary)
        if c.detail:
            L.append("")
            for d in c.detail:
                L.append(f"- {d}" if d else "")
        if c.why:
            L += ["", f"> **為何有這個關卡**：{c.why}"]
        L.append("")

    L += ["---", "",
          "本報告由 `src/reconcile.py` 產生。資料語意與踩過的坑見 `AGENTS.md`；",
          "未答問題見 `docs/open-questions.md`。"]
    return "\n".join(L)
