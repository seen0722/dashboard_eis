"""ECharts 嵌入。圖的數字在 Python 算好，以 JSON 放進頁面，JS 只負責畫；沒有 JS 時同一份數字在 <details> 表格裡。"""
from __future__ import annotations
import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from html import escape as e
from pathlib import Path
from ..strings import t

ECHARTS_DIR = Path(__file__).resolve().parents[4] / "vendor" / "echarts"
ECHARTS_JS = ECHARTS_DIR / "echarts.min.js"
STATIC_URL = "/ui/static/echarts.min.js"


@dataclass(frozen=True)
class Chart:
    id: str                                   # 頁內唯一，只用 [a-z0-9-]
    title: str
    option: dict                              # ECharts option；函式寫成 {"$fn": 名稱}，由 INIT_JS 換成 FN 表裡的函式
    headers: tuple[str, ...]                  # 資料表欄名
    rows: tuple[tuple, ...]                   # 資料表內容，與 option 同一份計算結果
    height: int = 280
    variants: dict = field(default_factory=dict)   # {篩選標籤: option}；空 = 不提供篩選
    note: str = ""                            # 圖下方一行口徑／缺口說明


INIT_JS = """(function(){
if(typeof echarts==='undefined')return;
var FN={ganttBar:function(params,api){var s=api.coord([api.value(1),api.value(0)]),f=api.coord([api.value(2),api.value(0)]),h=api.size([0,1])[1]*0.3;
return{type:'rect',shape:{x:s[0],y:s[1]-h/2,width:Math.max(f[0]-s[0],2),height:h},style:{fill:api.visual('color'),opacity:0.3}};}};
function revive(o){if(Array.isArray(o))return o.map(revive);if(o&&typeof o==='object'){if(typeof o.$fn==='string')return FN[o.$fn];var r={};for(var k in o)r[k]=revive(o[k]);return r;}return o;}
var live=[];
function init(root){(root||document).querySelectorAll('[data-chart]').forEach(function(el){
if(el._ec||el.offsetParent===null)return;
var d=JSON.parse(document.getElementById(el.id+'-data').textContent);
el._d=d;el._ec=echarts.init(el,null,{renderer:'svg'});el._ec.setOption(revive(d.option));live.push(el._ec);});}
document.addEventListener('change',function(ev){var s=ev.target;if(!s||!s.getAttribute||!s.getAttribute('data-variant-for'))return;
var el=document.getElementById(s.getAttribute('data-variant-for'));if(!el||!el._ec)return;
el._ec.setOption(revive((s.value&&el._d.variants[s.value])||el._d.option),true);});
window.addEventListener('resize',function(){live.forEach(function(c){c.resize();});});
window.eisCharts={init:init};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',function(){init();});else init();
})();"""


@lru_cache(maxsize=1)
def echarts_source() -> str:
    if not ECHARTS_JS.is_file():
        raise FileNotFoundError(f"ECharts bundle missing: {ECHARTS_JS}")
    return ECHARTS_JS.read_text(encoding="utf-8")


def echarts_tag(mode: str) -> str:
    if mode == "inline":
        return f"<script>{echarts_source()}</script>"
    if mode == "static":
        return f'<script src="{STATIC_URL}"></script>'
    raise ValueError(f"unknown echarts mode: {mode}")


def scripts(mode: str) -> str:
    return echarts_tag(mode) + f"<script>{INIT_JS}</script>"


def _clean(v):
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    return v


def to_json(obj) -> str:
    """嵌進 <script type="application/json"> 的 JSON：NaN/inf 轉 null；「</」與「<!--」跳脫，資料無法提前關閉 script。"""
    s = json.dumps(_clean(obj), ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return s.replace("</", "<\\/").replace("<!--", "\\u003c!--")


def _cell(v) -> str:
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return e(str(v))


def chart_html(ch: Chart, lang: str) -> str:
    pick = ""
    if ch.variants:
        opts = "".join(f'<option value="{e(k)}">{e(k)}</option>' for k in ch.variants)
        pick = (f'<label class="pick">{e(t(lang, "v_filter_customer"))} <select data-variant-for="c-{ch.id}">'
                f'<option value="">{e(t(lang, "v_filter_all"))}</option>{opts}</select></label>')
    note = f'<p class="note">{e(ch.note)}</p>' if ch.note else ""
    head = "".join(f"<th>{e(h)}</th>" for h in ch.headers)
    body = "".join("<tr>" + "".join(f"<td>{_cell(v)}</td>" for v in r) + "</tr>" for r in ch.rows)
    return (f'{pick}<div class="chart" id="c-{ch.id}" data-chart style="height:{ch.height}px" role="img" aria-label="{e(ch.title)}"></div>'
            f'<script type="application/json" id="c-{ch.id}-data">{to_json({"option": ch.option, "variants": ch.variants})}</script>'
            f'<noscript><p class="note">{e(t(lang, "v_need_js"))}</p></noscript>{note}'
            f'<details class="data"><summary data-expand="{e(t(lang, "expand"))}" data-collapse="{e(t(lang, "collapse"))}"><span>{e(t(lang, "v_data_table"))}</span></summary>'
            f'<div class="wide"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></details>')
