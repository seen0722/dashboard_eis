"""單一專案 · 單月的工作清單（整理自人力明細『備註』欄）→ editorial 風格 HTML。

用法：python src/render_worklist.py [PROJECT] [YYYYMM]
  例：python src/render_worklist.py THORPE 202607
  預設 PROJECT=THORPE、YYYYMM=data/raw 裡最新月。

⚠ 含工號/姓名（個資）→ 輸出檔名帶 _internal + 紅色 PII banner，受 out/ gitignore 保護，勿外流。
"""
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "out"

PM_FUNCTIONS = {"PM", "ME PM", "RD PM", "RDPM", "RE PM", "NPI PM", "SYSTEM PM", "Sales PM"}
ROLE_ORDER = {"BU RD": 0, "BU PM": 1, "FU RD": 2}

TOKENS = """
:root {
  --paper:#faf7f2; --paper-2:#f2ece2; --surface:#fff;
  --ink:#2b2320; --ink-2:#6b5f58; --ink-3:#a2968d;
  --rule:#e6ded2; --rule-2:#cfc3b4;
  --accent:#a03823; --accent-2:#cf8f7e; --cool:#496a8f; --tint:#f4ece1;
  --serif:"Iowan Old Style","Palatino Linotype","Book Antiqua",Palatino,"Songti TC",Georgia,serif;
  --sans:-apple-system,BlinkMacSystemFont,"Helvetica Neue","PingFang TC",Arial,sans-serif;
  --mono:"SF Mono",ui-monospace,Menlo,monospace;
  --radius:12px; --radius-sm:7px;
  --shadow:0 1px 2px rgba(43,35,32,.04), 0 8px 24px -12px rgba(43,35,32,.1);
  --bg:radial-gradient(120% 80% at 50% -10%, var(--paper-2) 0%, transparent 58%), var(--paper);
}
"""

CSS = TOKENS + """
* { box-sizing: border-box; }
body { margin:0; color:var(--ink); background:var(--bg); font-family:var(--sans);
  font-size:15px; line-height:1.6; -webkit-font-smoothing:antialiased; }
.pii-banner { position:sticky; top:0; z-index:50; background:var(--accent); color:#fff;
  text-align:center; padding:0.5rem 1rem; font-size:0.8rem; font-weight:600;
  letter-spacing:0.03em; font-family:var(--sans); }
@media print { .pii-banner { position:static; } }
.wrap { max-width:1000px; margin:0 auto; padding:clamp(2rem,4vw,3.5rem) clamp(1rem,4vw,2rem) 6rem; }
.masthead { border-top:3px solid var(--ink); padding-top:1.1rem; margin-bottom:1.6rem; }
.kicker { font-size:0.66rem; letter-spacing:0.2em; text-transform:uppercase; color:var(--accent); font-weight:700; }
.masthead h1 { font-family:var(--serif); font-size:clamp(2rem,5vw,2.8rem); margin:0.5rem 0 0.5rem;
  line-height:1.08; letter-spacing:-0.022em; }
.masthead h1 em { font-style:normal; color:var(--ink-3); font-weight:400; }
.meta { color:var(--ink-2); font-size:0.82rem; font-family:var(--mono); }
.summary { background:var(--surface); border:1px solid var(--rule); border-left:4px solid var(--accent);
  border-radius:var(--radius-sm); padding:0.9rem 1.2rem; margin:1.4rem 0 2rem; font-size:0.88rem;
  box-shadow:var(--shadow); }
.summary b { color:var(--accent); }

.role-h { display:flex; align-items:baseline; gap:0.75rem; margin:2.6rem 0 0.3rem; }
.role-h .n { font-family:var(--serif); font-size:0.95rem; color:var(--accent); font-weight:600;
  border-bottom:2px solid var(--accent); padding-bottom:2px; }
.role-h h2 { font-family:var(--serif); font-size:1.5rem; margin:0; letter-spacing:-0.018em; }
.role-h .tot { margin-left:auto; font-family:var(--mono); font-size:0.78rem; color:var(--ink-3); }

.wl-wrap { overflow-x:auto; border:1px solid var(--rule); border-radius:var(--radius);
  box-shadow:var(--shadow); background:var(--surface); margin-top:0.8rem; }
table { width:100%; border-collapse:collapse; font-size:0.85rem; min-width:640px; }
thead th { background:var(--tint); text-align:left; font-family:var(--sans); font-size:0.64rem;
  letter-spacing:0.1em; text-transform:uppercase; color:var(--ink-2); font-weight:700;
  padding:0.6rem 0.85rem; border-bottom:1px solid var(--rule-2); white-space:nowrap; }
tbody td { padding:0.6rem 0.85rem; border-bottom:1px solid var(--rule); vertical-align:top; }
tbody tr:last-child td { border-bottom:none; }
tbody tr:hover { background:color-mix(in srgb, var(--tint) 45%, transparent); }
.c-id { font-family:var(--mono); font-size:0.78rem; color:var(--ink-3); white-space:nowrap; }
.c-name { white-space:nowrap; font-weight:600; }
.c-dept { color:var(--ink-2); font-size:0.8rem; }
.c-func { font-family:var(--mono); font-size:0.78rem; color:var(--ink-3); white-space:nowrap; }
.c-fte { text-align:right; font-family:var(--serif); font-variant-numeric:tabular-nums; white-space:nowrap; }
.c-note { line-height:1.5; }
.c-note.empty { color:var(--ink-3); font-style:italic; }
.c-note ol { margin:0; padding-left:1.1rem; }
.c-note .stage { display:inline-block; background:var(--accent); color:#fff; font-size:0.66rem;
  font-weight:700; padding:0.08rem 0.4rem; border-radius:3px; margin-right:0.3rem; font-family:var(--sans); }
footer { margin-top:3.5rem; padding-top:1.2rem; border-top:1px solid var(--rule-2);
  font-size:0.74rem; color:var(--ink-3); font-family:var(--mono); }
@media (max-width:640px){ .wrap{padding-left:1rem;padding-right:1rem;} .masthead h1{font-size:1.7rem;} }
@media print { body{background:#fff;} .wl-wrap,.summary{box-shadow:none;break-inside:avoid;} }
"""

MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
STAGE_RE = re.compile(r"\b(EVT\d?|DVT\s?\d?|PVT\d?|MVT\d?|MR\d?|MP\d?|FAI|DVT ?\d)\b", re.I)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def note_html(note):
    """把備註轉 HTML：保留換行；1. 2. 3. 轉成 ol；EVT/DVT/MR 等階段字上色。"""
    if not note:
        return '<span class="c-note empty">（未填）</span>'
    txt = esc(note)
    # 階段標記上色（DVT3 / MR4 / FAI …）
    txt = STAGE_RE.sub(lambda m: f'<span class="stage">{m.group(0)}</span>', txt)
    # 編號清單：拆 "1. ... 2. ..." 為 <ol>
    items = re.split(r"\n?\s*\d+[.、]\s+", txt)
    items = [i.strip() for i in items if i.strip()]
    if len(items) >= 2:
        return '<div class="c-note"><ol>' + "".join(f"<li>{i}</li>" for i in items) + "</ol></div>"
    return '<div class="c-note">' + txt.replace("\n", "<br>") + "</div>"


def latest_month():
    ms = sorted(re.match(r"(\d{6})", p.name).group(1)
                for p in RAW.glob("*.xlsx") if not p.name.startswith("~$")
                and re.match(r"\d{6}", p.name))
    return ms[-1] if ms else None


def extract(project, yyyymm):
    path = next(RAW.glob(f"{yyyymm}*.xlsx"))
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    pct = list(next(wb[s] for s in wb.sheetnames if re.search(r"\d{6}-百分比分攤", s))
               .iter_rows(values_only=True))
    ibu = list(pct[0]).index("BU")
    dept_org = {r[1]: r[ibu] for r in pct[1:] if r[1]}

    def is_external(dept, bu):
        org = dept_org.get(dept)
        return str(dept)[0] == "F" if org is None else org != bu

    ws = next(wb[s] for s in wb.sheetnames if re.search(r"\d{6}-人力明細", s))
    rows = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        dept, dname, emp, mem, func, fte, note, nm, bu = (
            r[0], r[1], r[2], r[3], r[5], r[6], r[8], r[10], r[13])
        if not isinstance(fte, (int, float)) or bu != "BU10":
            continue
        if str(dept).startswith("H") or not str(nm).upper().startswith(project.upper()):
            continue
        role = "FU RD" if is_external(dept, bu) else ("BU PM" if func in PM_FUNCTIONS else "BU RD")
        rows.append({"role": role, "dept": str(dname), "emp": str(emp), "name": str(mem),
                     "func": "" if func in (None, "None") else str(func), "fte": float(fte),
                     "note": (str(note).strip() if note not in (None, "") else "")})
    wb.close()
    rows.sort(key=lambda x: (ROLE_ORDER[x["role"]], -x["fte"]))
    return rows, path.name


def render(project, yyyymm):
    rows, fname = extract(project, yyyymm)
    y, m = int(yyyymm[:4]), int(yyyymm[4:6])
    ym = f"{MONTHS_EN[m-1]} {y}"
    filled = sum(1 for r in rows if r["note"])
    total_fte = sum(r["fte"] for r in rows)

    sections = ""
    for role in ["BU RD", "BU PM", "FU RD"]:
        rr = [r for r in rows if r["role"] == role]
        if not rr:
            continue
        n_filled = sum(1 for r in rr if r["note"])
        body = ""
        for r in rr:
            dept = r["dept"] if len(r["dept"]) <= 30 else "…" + r["dept"][-29:]
            body += (f'<tr><td class="c-id">{esc(r["emp"])}</td>'
                     f'<td class="c-name">{esc(r["name"])}</td>'
                     f'<td class="c-dept">{esc(dept)}</td>'
                     f'<td class="c-func">{esc(r["func"]) or "—"}</td>'
                     f'<td class="c-fte">{r["fte"]:.2f}</td>'
                     f'<td>{note_html(r["note"])}</td></tr>')
        sections += f"""
  <div class="role-h"><span class="n">{"01" if role=="BU RD" else "02" if role=="BU PM" else "03"}</span>
    <h2>{esc(role)}</h2>
    <span class="tot">{len(rr)} 人 · {sum(r['fte'] for r in rr):.2f} FTE · 備註 {n_filled}/{len(rr)}</span></div>
  <div class="wl-wrap"><table>
    <thead><tr><th>工號</th><th>成員</th><th>部門</th><th>職能</th><th>FTE</th><th>工作內容（備註）</th></tr></thead>
    <tbody>{body}</tbody>
  </table></div>"""

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(project)} 工作清單 {ym}</title>
<style>{CSS}</style>
</head>
<body>
<div class="pii-banner">⚠ 含個人資料（員工姓名／工號）· 限內部使用 · 請勿轉寄或公開</div>
<div class="wrap">
  <div class="masthead">
    <div class="kicker">BU10 · 專案工作清單</div>
    <h1>{esc(project)}<em> · {esc(ym)}</em></h1>
    <p class="meta">整理自 {esc(fname)} → 人力明細『備註』欄</p>
  </div>
  <div class="summary">
    共 <b>{len(rows)}</b> 人、<b>{total_fte:.2f}</b> FTE（僅 D 組逐人填報）·
    備註有填 <b>{filled}/{len(rows)}</b>（{filled/len(rows)*100:.0f}%）·
    未填多集中在外部支援（FU RD）。
  </div>
  {sections}
  <footer>由 src/render_worklist.py 產生 · python src/render_worklist.py {project} {yyyymm}</footer>
</div>
</body>
</html>
"""


def main():
    project = sys.argv[1] if len(sys.argv) > 1 else "THORPE"
    yyyymm = sys.argv[2] if len(sys.argv) > 2 else latest_month()
    OUT.mkdir(exist_ok=True)
    dest = OUT / f"worklist_{project}_{yyyymm}_internal.html"
    dest.write_text(render(project, yyyymm), encoding="utf-8")
    print(f"→ {dest}  ({dest.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
