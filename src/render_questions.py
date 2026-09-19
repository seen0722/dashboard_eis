"""把 docs/open-questions.md 轉成 editorial 風格的自足單頁 HTML。

用法：python src/render_questions.py
輸出：out/open-questions.html（自足、無外部依賴，可本機開或寄出）

每月更新完 open-questions.md 後重跑即可。風格對齊 dashboard 的 editorial 主題。
"""
import re
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "open-questions.md"
OUT = ROOT / "out" / "open-questions.html"

# editorial 色彩 token（與 dashboard 一致；直接內嵌避免跨檔耦合）
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
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; color: var(--ink); background: var(--bg); font-family: var(--sans);
  font-size: 15px; line-height: 1.68; -webkit-font-smoothing: antialiased; }
.wrap { max-width: 1040px; margin: 0 auto;
  padding: clamp(2.25rem,5vw,4.5rem) clamp(1rem,4vw,2rem) 7rem; }

/* Masthead */
.masthead { border-top: 3px solid var(--ink); padding-top: 1.1rem; margin-bottom: 2.2rem; }
.kicker { font-size: 0.66rem; letter-spacing: 0.2em; text-transform: uppercase;
  color: var(--accent); font-weight: 700; }
.masthead h1 { font-family: var(--serif); font-size: clamp(2.1rem,5vw,3rem);
  margin: 0.5rem 0 0.6rem; line-height: 1.06; letter-spacing: -0.022em; }
.meta { color: var(--ink-2); font-size: 0.8rem; font-family: var(--mono);
  line-height: 1.8; letter-spacing: -0.01em; }
.meta code { color: var(--ink); }

/* 一般文字 */
h2, h3 { font-family: var(--serif); }
p { max-width: 74ch; }
a { color: var(--accent); }
code { font-family: var(--mono); font-size: 0.9em;
  background: var(--tint); padding: 0.08em 0.4em; border-radius: 4px; color: var(--ink); }
del { color: var(--ink-3); }

/* 章節標題（A. B. C. …）—— serif 編號 + accent 底線 */
h2 { font-size: 1.5rem; letter-spacing: -0.018em; margin: 3.4rem 0 1.1rem;
  padding-bottom: 0.4rem; border-bottom: 2px solid var(--accent); display: inline-block; }
h2::after { content: ""; }

/* 優先順序 callout（blockquote） */
blockquote { margin: 1.6rem 0; padding: 1.15rem 1.4rem;
  background: var(--surface); border: 1px solid var(--rule); border-left: 4px solid var(--accent);
  border-radius: var(--radius-sm); box-shadow: var(--shadow); }
blockquote p { margin: 0.35rem 0; max-width: none; }
blockquote p:first-child { margin-top: 0; }
blockquote p:last-child { margin-bottom: 0; }

hr { border: 0; border-top: 1px solid var(--rule-2); margin: 2.5rem 0; }

/* 表格 —— 卡片式，狀態欄上色 */
.tbl-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; margin: 1rem 0 1.5rem;
  border: 1px solid var(--rule); border-radius: var(--radius); box-shadow: var(--shadow);
  background: var(--surface); }
table { width: 100%; border-collapse: collapse; font-size: 0.86rem; min-width: 640px; }
thead th { background: var(--tint); text-align: left; font-family: var(--sans);
  font-size: 0.66rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--ink-2);
  font-weight: 700; padding: 0.7rem 0.9rem; border-bottom: 1px solid var(--rule-2);
  white-space: nowrap; }
tbody td { padding: 0.7rem 0.9rem; border-bottom: 1px solid var(--rule); vertical-align: top; }
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover { background: color-mix(in srgb, var(--tint) 45%, transparent); }
/* 第一欄（編號 A1/B2…）等寬、accent */
tbody td:first-child { font-family: var(--mono); font-weight: 700; color: var(--accent);
  white-space: nowrap; font-size: 0.82rem; }
td strong, th strong { color: var(--ink); }
td .num, table code { font-variant-numeric: tabular-nums; }

/* 狀態徽章（JS 依文字上色） */
.st { display: inline-block; font-family: var(--sans); font-size: 0.7rem; font-weight: 700;
  letter-spacing: 0.02em; padding: 0.15rem 0.5rem; border-radius: 999px; white-space: nowrap; }
.st--hot { background: var(--accent); color: #fff; }
.st--open { background: var(--tint); color: var(--ink-2); border: 1px solid var(--rule-2); }
.st--done { background: color-mix(in srgb, var(--cool) 14%, var(--surface)); color: var(--cool); }
.st--void { background: repeating-linear-gradient(45deg, var(--rule-2) 0 3px, transparent 3px 6px);
  color: var(--ink-3); }

/* 已結案區塊：整體淡化 */
.closed { opacity: 0.82; }
.closed h2 { border-bottom-color: var(--rule-2); color: var(--ink-2); }

footer { margin-top: 4rem; padding-top: 1.3rem; border-top: 1px solid var(--rule-2);
  font-size: 0.74rem; color: var(--ink-3); font-family: var(--mono); }

@media (max-width: 640px) {
  .wrap { padding-left: 1rem; padding-right: 1rem; }
  .masthead h1 { font-size: 1.8rem; }
}
@media print {
  body { background: #fff; }
  .tbl-wrap, blockquote { box-shadow: none; break-inside: avoid; }
}
"""

# 狀態文字 → 徽章 class（JS 用；此處僅供對照文件）
STATUS_JS = """
(function () {
  var rules = [
    [/最優先|最高\\s*ROI|最急|爆增/, 'st--hot'],
    [/作廢/, 'st--void'],
    [/確認|已結案|結案|已收尾|實作|不成立|錯誤發現/, 'st--done'],
    [/未答|未提報|未提|待確認|待回顧|新增/, 'st--open'],
  ];
  // 只處理表格最後一欄（狀態欄）
  document.querySelectorAll('table').forEach(function (t) {
    var heads = [].map.call(t.querySelectorAll('thead th'), function (th) {
      return th.textContent.trim();
    });
    var statusIdx = heads.indexOf('狀態');
    if (statusIdx < 0) return;
    t.querySelectorAll('tbody tr').forEach(function (tr) {
      var cell = tr.children[statusIdx];
      if (!cell) return;
      var txt = cell.textContent.trim();
      if (!txt) return;
      var cls = null;
      for (var i = 0; i < rules.length; i++) {
        if (rules[i][0].test(txt)) { cls = rules[i][1]; break; }
      }
      if (cls) {
        // 保留原本可能有的粗體語意，只把整格包成徽章
        var span = document.createElement('span');
        span.className = 'st ' + cls;
        span.textContent = txt.replace(/\\*\\*/g, '');
        cell.innerHTML = '';
        cell.appendChild(span);
      }
    });
  });
})();
"""


def convert() -> str:
    md_text = SRC.read_text(encoding="utf-8")
    lines = md_text.splitlines()

    # 1) 去掉第一行 H1（masthead 已有標題），避免重複
    if lines and lines[0].startswith("# "):
        lines = lines[1:]

    # 2) 抽出開頭的 meta 清單（連續的「- 」行），改用 .meta 呈現而非 bullet list
    meta_items = []
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    while i < len(lines) and lines[i].lstrip().startswith("- "):
        meta_items.append(lines[i].lstrip()[2:])
        i += 1
    rest = "\n".join(lines[i:])

    # markdown 核心不支援 ~~刪除線~~ —— 前處理轉成 <del>（tables 擴充會保留內嵌 HTML）
    strike = lambda t: re.sub(r"~~(.+?)~~", r"<del>\1</del>", t)
    rest = strike(rest)

    md = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists", "md_in_html"])
    meta_html = ""
    if meta_items:
        rendered = [markdown.markdown(m, extensions=["tables"]).replace("<p>", "").replace("</p>", "")
                    for m in meta_items]
        meta_html = '<div class="meta">' + "<br>".join(rendered) + "</div>"
    body_html = meta_html + md.convert(rest)

    # 每個 <table> 包一層可橫捲容器
    body_html = re.sub(r"<table>", '<div class="tbl-wrap"><table>', body_html)
    body_html = re.sub(r"</table>", "</table></div>", body_html)

    # 「已結案」的 h2 之後整段加 closed class：用標記包起來
    body_html = body_html.replace(
        "<h2>已結案</h2>", '<div class="closed"><h2>已結案</h2>'
    )
    # closed 區塊延伸到文件結尾 —— 補收尾 </div>
    if '<div class="closed">' in body_html:
        body_html += "</div>"

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BU10 待釐清問題清單</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="masthead">
    <div class="kicker">BU10 · Open Questions</div>
    <h1>待釐清問題清單</h1>
  </div>
  {body_html}
  <footer>由 src/render_questions.py 從 docs/open-questions.md 產生 · 每月更新後重跑</footer>
</div>
<script>{STATUS_JS}</script>
</body>
</html>
"""


def main() -> None:
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(convert(), encoding="utf-8")
    print(f"→ {OUT}  ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
