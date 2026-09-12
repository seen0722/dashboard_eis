CSS = """
:root{--paper:#F5F6F4;--ink:#22262A;--ink-2:#5B6167;--ink-3:#9AA3AB;--rule:#D5D9D6;--slate:#3D5A80;--slate-2:#A9B8CC;--teal:#5C8D89;--signal:#E8590C}
*{box-sizing:border-box}html{background:var(--paper)}
body{margin:0 auto;max-width:1280px;padding:36px 40px 80px;color:var(--ink);font:14px/1.55 -apple-system,"SF Pro Text","Segoe UI","Helvetica Neue","PingFang TC","Microsoft JhengHei","Noto Sans TC",sans-serif;font-variant-numeric:tabular-nums}
header{display:flex;justify-content:space-between;align-items:flex-start;gap:32px;padding-bottom:22px;border-bottom:1px solid var(--ink)}
h1{font-size:28px;font-weight:600;margin:0;line-height:1.2}header p{margin:8px 0 0;color:var(--ink-2);max-width:60ch}
.tb{border:1px solid var(--ink);font-size:12px;min-width:270px}.tb div{display:grid;grid-template-columns:112px 1fr;border-top:1px solid var(--rule)}.tb div:first-child{border-top:0}
.tb span{padding:5px 10px}.tb span:first-child{color:var(--ink-2);border-right:1px solid var(--rule)}
section{padding:30px 0 6px;border-bottom:1px solid var(--rule)}section:last-of-type{border-bottom:0}
h2{font-size:20px;font-weight:600;margin:0 0 4px}.lead{margin:0 0 18px;color:var(--ink-2);max-width:70ch}
ol.ex{list-style:none;margin:0;padding:0}ol.ex li{display:grid;grid-template-columns:44px 1fr;gap:12px;padding:14px 0;border-top:1px solid var(--rule)}ol.ex li:first-child{border-top:0}
ol.ex .n{font-size:28px;font-weight:600;color:var(--signal);line-height:1}ol.ex b{font-weight:600;font-size:15px}
ol.ex .body{color:var(--ink-2);margin:4px 0 0;max-width:110ch}ol.ex .ask{margin-top:6px}ol.ex .ask em{font-style:normal;color:var(--signal);font-weight:600}ol.ex .src{color:var(--ink-3);font-size:12px;margin-top:2px}
.two{display:grid;grid-template-columns:320px 1fr;gap:36px}@media(max-width:900px){.two{grid-template-columns:1fr}}
table{border-collapse:collapse;width:100%}th{text-align:left;font-weight:600;font-size:12px;color:var(--ink-2);padding:6px 8px 6px 0;border-bottom:1px solid var(--ink)}
td{padding:7px 8px 7px 0;border-bottom:1px solid var(--rule);vertical-align:top}td.num,th.num{text-align:right}
.sig{color:var(--signal);font-weight:600}.dim{color:var(--ink-3)}
.stages{display:flex;gap:28px;margin:0 0 22px;flex-wrap:wrap}.stages div b{display:block;font-size:24px;font-weight:600;line-height:1.1}.stages div span{font-size:12px;color:var(--ink-2)}
.tl{overflow-x:auto}.tl table td{padding:0 8px 0 0;height:32px;white-space:nowrap}
.legend{display:flex;gap:18px;font-size:12px;color:var(--ink-2);margin-top:10px;flex-wrap:wrap}.legend i{display:inline-block;width:10px;height:10px;margin-right:6px;vertical-align:-1px;background:var(--slate)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:8px;vertical-align:1px}.dot.d{background:var(--signal)}.dot.t{background:var(--slate)}.dot.o{background:var(--ink-3)}
select{font:14px inherit;padding:6px 10px;border:1px solid var(--ink);background:#fff;border-radius:0}select:focus{outline:2px solid var(--slate);outline-offset:2px}
.ms{display:grid;grid-template-columns:repeat(5,1fr);margin:16px 0 20px;border-top:1px solid var(--ink)}.ms div{padding:10px 0;border-right:1px solid var(--rule)}.ms div:last-child{border-right:0}
.ms b{display:block;font-size:20px;font-weight:600}.ms small{color:var(--ink-2)}
details{border-top:1px solid var(--rule)}details summary{cursor:pointer;padding:10px 0;list-style:none;display:flex;justify-content:space-between}
details summary::-webkit-details-marker{display:none}details summary:focus-visible{outline:2px solid var(--slate)}
details summary::after{content:attr(data-expand);color:var(--slate);font-size:12px}details[open] summary::after{content:attr(data-collapse)}
details td.desc{white-space:pre-line;max-width:70ch;color:var(--ink-2);font-size:13px}
.pva{display:grid;grid-template-columns:1fr 1fr 1fr;gap:24px}.pva h4{margin:0 0 4px;font-size:13px;font-weight:600}.pva .s{font-size:12px;color:var(--ink-2)}
footer{color:var(--ink-3);font-size:12px;margin-top:30px;max-width:80ch}footer p{margin:4px 0}
svg text{font-family:inherit}
@media (prefers-reduced-motion: reduce){*{transition:none!important}}
"""
