"""視覺主題。

結構 CSS 在 build_review.py 的 CSS_BASE；這裡只放「風格」——
tokens ＋ 讓該風格成立的性格覆寫。

每個主題都是一個完整、徹底執行的方向，不是換色盤。
四個都是淺色系。
"""

THEMES = {
    # ─────────────────────────────────────────────────────────────
    "editorial": {
        "label": "Editorial — 暖白紙面，印刷報告感",
        "css": """
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
  --shadow-sm:0 1px 2px rgba(43,35,32,.03);
  --bg:radial-gradient(120% 80% at 50% -10%, var(--paper-2) 0%, transparent 58%), var(--paper);
  --head-bg:var(--tint); --bar-neutral:#d6cec3;
}
h1,h2,h3 { font-family:var(--serif); }
.masthead { border-top:3px solid var(--ink); }
.kicker { letter-spacing:.2em; }
.masthead h1 { letter-spacing:-.022em; }
.kpi__v,.excess,.num,.rl__v,.list li span:last-child { font-family:var(--serif); }
.sec__n { font-family:var(--serif); border-bottom:2px solid var(--accent); }
""",
    },
    # ─────────────────────────────────────────────────────────────
    "swiss": {
        "label": "Swiss — 網格嚴謹，Helvetica，零圓角零陰影",
        "css": """
:root {
  --paper:#fff; --paper-2:#fff; --surface:#fff;
  --ink:#000; --ink-2:#4d4d4d; --ink-3:#8c8c8c;
  --rule:#d9d9d9; --rule-2:#000;
  --accent:#d40511; --accent-2:#f08d94; --cool:#0057b8; --tint:#f2f2f2;
  --serif:"Helvetica Neue",Helvetica,"PingFang TC",Arial,sans-serif;
  --sans:"Helvetica Neue",Helvetica,"PingFang TC",Arial,sans-serif;
  --mono:"SF Mono",ui-monospace,Menlo,monospace;
  --radius:0; --radius-sm:0; --shadow:none; --shadow-sm:none;
  --bg:var(--paper); --head-bg:var(--tint); --bar-neutral:#c4c4c4;
}
h1,h2,h3 { font-family:var(--sans); font-weight:700; letter-spacing:-.03em; }
body { font-size:14.5px; }
.masthead { border-top:6px solid var(--ink); border-bottom:1px solid var(--ink); }
.kicker { color:var(--ink); letter-spacing:.08em; font-weight:700; }
.masthead h1 { letter-spacing:-.035em; font-weight:700; }
.masthead h1 em { color:var(--ink-3); }
.card,.band,.list { border-color:var(--rule); }
.card { border-left-width:6px; }
.sec__h { align-items:baseline; gap:1rem; border-bottom:2px solid var(--ink); padding-bottom:.4rem; }
.sec__n { font-family:var(--sans); font-weight:700; border-bottom:0; color:var(--ink);
  font-size:1.5rem; }
.sec__h h2 { font-size:1.5rem; }
.band__head { background:var(--tint); border-bottom:1px solid var(--ink); }
.kpi__v,.excess { font-family:var(--sans); font-weight:700; letter-spacing:-.04em; }
.excess { color:var(--accent); }
h3.sub { letter-spacing:.1em; border-bottom:1px solid var(--ink); }
.list h3 { background:var(--tint); border-bottom:1px solid var(--ink); }
.rail button[aria-selected="true"] { border-bottom-width:3px; }
.chart .lbl,.chart .colm { font-family:var(--sans); }
.chart .val,.chart .tv,.chart .ex,.chart .tnum { font-family:var(--sans); font-weight:700; }
""",
    },
    # ─────────────────────────────────────────────────────────────
    "technical": {
        "label": "Technical — 工程規格書，方格紙底，等寬字為主",
        "css": """
:root {
  --paper:#f4f6f7; --paper-2:#eaeef0; --surface:#fbfcfc;
  --ink:#1b2327; --ink-2:#4a585f; --ink-3:#8b979d;
  --rule:#d3dbdf; --rule-2:#9fadb4;
  --accent:#b4590a; --accent-2:#e0a878; --cool:#2b6b78; --tint:#e8edef;
  --serif:"SF Mono",ui-monospace,Menlo,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Helvetica Neue","PingFang TC",Arial,sans-serif;
  --mono:"SF Mono",ui-monospace,Menlo,monospace;
  --radius:2px; --radius-sm:2px; --shadow:none;
  --shadow-sm:inset 0 0 0 1px rgba(255,255,255,.6);
  /* 方格紙 */
  --bg:
    linear-gradient(var(--rule) 1px, transparent 1px) 0 0/100% 24px,
    linear-gradient(90deg, var(--rule) 1px, transparent 1px) 0 0/24px 100%,
    var(--paper);
  --head-bg:var(--tint); --bar-neutral:#c2ccd1;
}
body { background-attachment:fixed; }
body::before { content:""; position:fixed; inset:0; pointer-events:none;
  background:linear-gradient(180deg, rgba(244,246,247,.72), rgba(244,246,247,.94)); }
.wrap { position:relative; }
h1,h2,h3 { font-family:var(--sans); font-weight:600; letter-spacing:-.02em; }
body { font-size:14px; }
.masthead { border-top:1px solid var(--ink); border-bottom:1px solid var(--rule-2);
  background:var(--surface); padding-left:1rem; padding-right:1rem; }
.kicker { font-family:var(--mono); letter-spacing:.1em; font-weight:500; }
.masthead__sub { font-size:.72rem; }
.card,.band,.list,.kpis--flat,.roles { border-color:var(--rule-2); }
.card { border-left-width:3px; background:var(--surface); }
.band,.list { background:var(--surface); }
.sec__h { border-bottom:1px solid var(--rule-2); padding-bottom:.35rem; }
.sec__n { font-family:var(--mono); border-bottom:0; color:var(--ink-3); font-size:.8rem; }
.sec__n::before { content:"["; } .sec__n::after { content:"]"; }
.src,.note { font-family:var(--mono); font-size:.72rem; }
.kpi__k { font-family:var(--mono); text-transform:uppercase; letter-spacing:.06em; font-size:.62rem; }
.kpi__v,.excess,.num,.rl__v { font-family:var(--mono); font-variant-numeric:tabular-nums; }
.excess { font-weight:600; letter-spacing:-.02em; }
.card__title h3 { font-family:var(--mono); font-size:1.05rem; }
h3.sub { font-family:var(--mono); letter-spacing:.12em; }
.list h3 { font-family:var(--mono); font-size:.85rem; }
.rail button { font-family:var(--mono); font-size:.86rem; }
.chart .lbl { font-family:var(--mono); font-size:11.5px; }
.chart .val,.chart .tv,.chart .ex,.chart .tnum,.chart .colm { font-family:var(--mono); }
""",
    },
    # ─────────────────────────────────────────────────────────────
    "quiet": {
        "label": "Quiet — 董事會簡報，低對比、大留白、深綠 accent",
        "css": """
:root {
  --paper:#f7f6f3; --paper-2:#eeece6; --surface:#fdfcfa;
  --ink:#26282a; --ink-2:#63666a; --ink-3:#a3a6a3;
  --rule:#e4e2dc; --rule-2:#cbc8c0;
  --accent:#5c6b3f; --accent-2:#a8b48c; --cool:#6b7f8c; --tint:#f0eee8;
  --serif:"Iowan Old Style",Palatino,"Songti TC",Georgia,serif;
  --sans:-apple-system,BlinkMacSystemFont,"Helvetica Neue","PingFang TC",Arial,sans-serif;
  --mono:"SF Mono",ui-monospace,Menlo,monospace;
  --radius:3px; --radius-sm:3px; --shadow:none; --shadow-sm:none;
  --bg:linear-gradient(180deg, var(--paper) 0%, var(--paper-2) 100%) fixed;
  --head-bg:transparent; --bar-neutral:#dad7cf;
}
h1,h2,h3 { font-family:var(--serif); font-weight:400; }
body { font-size:15.5px; line-height:1.75; }
.wrap { max-width:880px; padding-top:clamp(3rem,8vw,6rem); }
section { margin:5.5rem 0; }
.masthead { border-top:0; border-bottom:1px solid var(--rule-2); padding-bottom:2rem; }
.kicker { color:var(--ink-3); letter-spacing:.24em; font-weight:400; font-size:.6rem; }
.masthead h1 { font-size:clamp(2.4rem,6vw,3.6rem); font-weight:400; letter-spacing:-.015em;
  margin-top:1rem; }
.masthead h1 em { color:var(--ink-3); }
/* 用留白與細線取代卡片 */
.card,.band,.list { border:0; border-top:1px solid var(--rule); background:transparent;
  border-radius:0; }
.card { border-left:0; padding-left:0; margin-bottom:2.2rem; }
.card__head,.card__body { padding-left:0; padding-right:0; }
.band__head { background:transparent; border-bottom:1px solid var(--rule); padding-left:0;
  padding-right:0; }
.chart { padding-left:0; padding-right:0; }
.roles { border:0; background:transparent; gap:1.5rem; }
.rl { background:transparent; padding-left:0; }
.rl--over,.rl--under { background:transparent; }
.kpis,.kpis--flat { background:transparent; border:0; border-top:1px solid var(--rule);
  gap:0; border-radius:0; }
.kpi { background:transparent; padding-left:0; }
.kpis .kpi + .kpi { border-left:1px solid var(--rule); padding-left:1.4rem; }
.kpi__v { font-weight:400; font-size:1.75rem; }
.excess { font-weight:400; font-size:2.1rem; color:var(--accent); }
.sec__n { color:var(--ink-3); border-bottom:1px solid var(--rule-2); font-weight:400; }
.sec__h h2 { font-weight:400; }
.list h3 { background:transparent; font-weight:400; padding-left:0; }
.list ul,.list li,.list p { padding-left:0; }
.card__title h3 { font-weight:400; }
h3.sub { font-weight:400; letter-spacing:.18em; color:var(--ink-3); }
""",
    },
}


def theme_css(name):
    if name not in THEMES:
        raise KeyError(f"未知主題 {name}；可用：{list(THEMES)}")
    return THEMES[name]["css"]
