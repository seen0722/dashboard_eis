CSS = """
:root{--bg:#F3F5F8;--paper:#F3F5F8;--card:#FFFFFF;--ink:#1F2937;--ink-2:#5B6475;--ink-3:#9AA3AF;--rule:#E3E7EE;--side:#1E2735;--accent:#2563EB;--slate:#2563EB;--slate-2:#93C5FD;--teal:#0D9488;--signal:#E8590C;--bad:#DC2626;--warn:#F59E0B;--ok:#16A34A;--fs-xs:12px;--fs-sm:13px;--fs-base:14px;--fs-md:16px;--fs-lg:20px;--fs-xl:28px}
*{box-sizing:border-box}html{background:var(--bg)}
body{margin:0;color:var(--ink);background:var(--bg);font:var(--fs-base)/1.55 -apple-system,"SF Pro Text","Segoe UI","Helvetica Neue","PingFang TC","Microsoft JhengHei","Noto Sans TC",sans-serif;font-variant-numeric:tabular-nums}
a{color:var(--accent)}
.app{display:grid;grid-template-columns:224px minmax(0,1fr);min-height:100vh}
.side{background:var(--side);color:#CBD5E1;padding:20px 14px;position:sticky;top:0;height:100vh;overflow-y:auto}
.side a{display:flex;justify-content:space-between;align-items:center;gap:8px;color:#CBD5E1;text-decoration:none;padding:8px 10px;border-radius:6px;font-size:13px}
.side a:hover,.side a:focus-visible{background:rgba(255,255,255,.08);color:#fff}.side a.on{background:var(--accent);color:#fff;font-weight:600}
.side a.brand{color:#fff;font-weight:700;font-size:15px;padding:4px 10px 16px;background:none}
.side .badge{background:var(--signal);color:#fff;border-radius:9px;font-size:11px;font-weight:700;padding:0 7px;line-height:18px}
.side form{display:flex;gap:6px;align-items:end;margin:0 0 12px;padding:0 4px}.side .search{border-radius:8px;padding:7px 10px}.side label{color:#94A3B8;font-size:11px;display:flex;flex-direction:column;gap:4px;flex:1;min-width:0}
.side select,.side input{width:100%;min-width:0;font:13px inherit;padding:5px 8px;border:1px solid #334155;border-radius:6px;background:#0F172A;color:#E2E8F0}
.side button{font:12px inherit;padding:5px 10px;border:0;border-radius:6px;background:#334155;color:#fff;cursor:pointer}
.side .navt{position:absolute;opacity:0;width:1px;height:1px}.side .navbtn{display:none}.navt:focus-visible+.navbtn{outline:2px solid #fff}
.main{padding:28px 32px 64px;min-width:0;max-width:1480px}
header{display:flex;justify-content:space-between;align-items:flex-start;gap:24px;padding:0 0 16px;margin:0 0 18px;border-bottom:1px solid var(--rule)}
h1{font-size:var(--fs-xl);font-weight:700;margin:0;line-height:1.2;letter-spacing:-.01em}header p{margin:6px 0 0;color:var(--ink-2);max-width:70ch}
.tb{background:var(--card);border:1px solid var(--rule);border-radius:8px;font-size:12px;min-width:270px;overflow:hidden}.tb div{display:grid;grid-template-columns:112px 1fr;border-top:1px solid var(--rule)}.tb div:first-child{border-top:0}
.tb span{padding:5px 10px}.tb span:first-child{color:var(--ink-2);border-right:1px solid var(--rule)}
section{padding:4px 0 18px}
h2{font-size:var(--fs-lg);font-weight:700;margin:20px 0 4px;letter-spacing:-.005em}.lead{margin:0 0 14px;color:var(--ink-2);max-width:80ch}
.kpis{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:14px;margin:0 0 14px}.kpis.four{grid-template-columns:repeat(4,minmax(0,1fr))}
.kpi{display:flex;flex-direction:column;gap:2px;min-width:0;background:var(--card);border:1px solid var(--rule);border-top:3px solid var(--accent);border-radius:10px;padding:12px 16px;color:var(--ink);text-decoration:none}
a.kpi:hover,a.kpi:focus-visible{box-shadow:0 4px 14px rgba(15,23,42,.10);outline:none}
.kpi.bad{border-top-color:var(--bad)}.kpi.bad .k-value{color:var(--bad)}
.k-label{font-size:var(--fs-xs);color:var(--ink-2)}.k-value{font-size:26px;font-weight:700;line-height:1.2;overflow-wrap:anywhere}.k-sub{font-size:var(--fs-xs);color:var(--ink-3)}
.status{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.4fr);gap:14px;margin:0 0 14px}.status-card{display:block;min-width:0;background:var(--card);border:1px solid var(--rule);border-top:4px solid var(--bad);border-radius:12px;padding:16px 20px;color:var(--ink);text-decoration:none}.status-card.dec{border-top-color:var(--signal)}a.status-card:hover,a.status-card:focus-visible{box-shadow:0 4px 16px rgba(15,23,42,.10);outline:none}.s-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px}.s-label{font-size:var(--fs-md);font-weight:650}.s-num{font-size:40px;font-weight:700;line-height:1;letter-spacing:-.02em}.risk .s-num{color:var(--bad)}.dec .s-num{color:var(--signal)}.chips{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 4px}.chip{font-size:var(--fs-sm);font-weight:600;padding:3px 10px;border-radius:999px;background:#FEE2E2;color:#B91C1C;text-decoration:none}a.chip:hover,a.chip:focus-visible{background:#FECACA}.s-list{margin:10px 0 0;padding-left:20px;font-size:var(--fs-sm);color:var(--ink-2)}.s-list li{margin:3px 0}.s-list li::marker{color:var(--signal);font-weight:700}.kpis.strip{grid-template-columns:repeat(5,minmax(0,1fr))}.kpis.strip .kpi{border-top:1px solid var(--rule);padding:10px 14px}.kpis.strip .k-value{font-size:22px}.grid-2,.grid-3{display:grid;gap:14px;margin:0 0 14px}.grid-2{grid-template-columns:repeat(2,minmax(0,1fr))}.grid-3{grid-template-columns:repeat(3,minmax(0,1fr))}
.card{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:14px 16px;min-width:0;margin:0 0 14px}.grid-2>.card,.grid-3>.card{margin:0}
.card-h{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin:0 0 8px}.card-h h3{font-size:var(--fs-md);font-weight:650;margin:0}.card-sub{font-size:var(--fs-sm);color:var(--ink-2)}
.chart{width:100%}.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}.note{font-size:var(--fs-xs);color:var(--ink-2);margin:6px 0 0}
label.pick{font-size:12px;color:var(--ink-2);display:inline-flex;gap:6px;align-items:center;margin:0 0 6px}
.pill{display:inline-block;font-size:11px;font-weight:600;padding:1px 8px;border-radius:9px;white-space:nowrap}
.pill.bad{background:#FEE2E2;color:#B91C1C}.pill.warn{background:#FEF3C7;color:#92400E}.pill.ok{background:#DCFCE7;color:#166534}.pill.mute{background:#EEF1F5;color:var(--ink-2)}
ol.ex{list-style:none;margin:0;padding:0}ol.ex li{display:grid;grid-template-columns:44px 1fr;gap:12px;padding:14px 0;border-top:1px solid var(--rule)}ol.ex li:first-child{border-top:0}
ol.ex .n{font-size:26px;font-weight:700;color:var(--signal);line-height:1}ol.ex b{font-weight:600;font-size:15px}
ol.ex .body{color:var(--ink-2);margin:4px 0 0;max-width:110ch}ol.ex .ask{margin-top:6px}ol.ex .ask em{font-style:normal;color:var(--signal);font-weight:600}ol.ex .src{color:var(--ink-3);font-size:12px;margin-top:2px}
.two{display:grid;grid-template-columns:320px 1fr;gap:36px}
table{border-collapse:collapse;width:100%}th{text-align:left;font-weight:600;font-size:12px;color:var(--ink-2);padding:6px 8px 6px 0;border-bottom:1px solid var(--rule)}
td{padding:7px 8px 7px 0;border-bottom:1px solid var(--rule);vertical-align:top}td.num,th.num{text-align:right}
.sig{color:var(--signal);font-weight:600}.dim{color:var(--ink-3)}
.stages{display:flex;gap:28px;margin:0 0 22px;flex-wrap:wrap}.stages div b{display:block;font-size:24px;font-weight:600;line-height:1.1}.stages div span{font-size:12px;color:var(--ink-2)}
.legend{display:flex;gap:18px;font-size:12px;color:var(--ink-2);margin-top:10px;flex-wrap:wrap}.legend i{display:inline-block;width:10px;height:10px;margin-right:6px;vertical-align:-1px;background:var(--slate)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:8px;vertical-align:1px}.dot.d{background:var(--signal)}.dot.t{background:var(--slate)}.dot.o{background:var(--ink-3)}
select{font:14px inherit;padding:6px 10px;border:1px solid var(--rule);background:#fff;border-radius:6px}select:focus{outline:2px solid var(--accent);outline-offset:2px}
.ms{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:12px 0 18px}.ms div{background:var(--bg);border-radius:8px;padding:10px 12px;min-width:0}
.ms b{display:block;font-size:18px;font-weight:700}.ms small{color:var(--ink-2)}
details{border-top:1px solid var(--rule)}details summary{cursor:pointer;padding:10px 0;list-style:none;display:flex;justify-content:space-between}
details summary::-webkit-details-marker{display:none}details summary:focus-visible{outline:2px solid var(--accent)}
details summary::after{content:attr(data-expand);color:var(--accent);font-size:12px}details[open] summary::after{content:attr(data-collapse)}
details.data{margin-top:8px}details.data summary{padding:6px 0;font-size:12px;color:var(--ink-2)}
details td.desc{white-space:pre-line;max-width:70ch;color:var(--ink-2);font-size:13px}
.proj{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:14px 16px;margin-top:12px}
.pva{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.pva>div{min-width:0}.pva h4{margin:0 0 4px;font-size:13px;font-weight:700}.pva .s{font-size:12px;color:var(--ink-2)}
.wide{overflow-x:auto}
footer{color:var(--ink-3);font-size:12px;margin-top:24px;max-width:80ch}footer p{margin:4px 0}
svg text{font-family:inherit}
@media(max-width:1200px){.kpis,.kpis.strip{grid-template-columns:repeat(3,minmax(0,1fr))}.grid-3{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:900px){.app{grid-template-columns:minmax(0,1fr)}.side{position:static;height:auto;padding:12px 14px}.side a.brand{display:inline-flex;padding:4px 6px}
.side .navbtn{display:inline-block;float:right;color:#fff;font-size:13px;padding:4px 10px;border:1px solid #475569;border-radius:6px;cursor:pointer}.side .links{display:none;padding-top:10px}.navt:checked~.links{display:block}
.main{padding:18px 16px 48px}.status{grid-template-columns:minmax(0,1fr)}header{flex-direction:column}.tb{min-width:0;width:100%}.grid-2,.grid-3{grid-template-columns:minmax(0,1fr)}.pva{grid-template-columns:minmax(0,1fr)}.ms{grid-template-columns:repeat(2,minmax(0,1fr))}.two{grid-template-columns:1fr}}
@media(max-width:640px){.kpis,.kpis.four,.kpis.strip{grid-template-columns:repeat(2,minmax(0,1fr))}.k-value{font-size:22px}}
@media (prefers-reduced-motion: reduce){*{transition:none!important}}
"""
