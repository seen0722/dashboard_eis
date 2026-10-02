import json
import math
import re
import pytest
from src.portfolio.render.strings import STRINGS
from src.portfolio.render.viz.embed import ECHARTS_JS, INIT_JS, STATIC_URL, Chart, chart_html, echarts_source, echarts_tag, scripts, to_json


def ch(**kw):
    base = dict(id="stage", title="Projects by stage", option={"series": [{"type": "pie", "data": [{"name": "MP", "value": 3}]}]},
                headers=("Stage", "Projects"), rows=(("MP", 3), ("POC", None)))
    base.update(kw)
    return Chart(**base)


def test_vendored_echarts_is_the_pinned_build():
    assert ECHARTS_JS.is_file() and (ECHARTS_JS.parent / "VERSION").read_text().strip() == "5.6.0"
    src = echarts_source()
    assert "Apache Software Foundation" in src[:400] and "</script" not in src


def test_to_json_cannot_close_script_and_nan_is_null():
    s = to_json({"name": "</script><!--x", "v": math.nan, "w": [math.inf, 1.5]})
    assert "<" not in s                                   # 所有 < 都寫成 \u003c，script 內容不可能出現任何標籤
    assert json.loads(s) == {"name": "</script><!--x", "v": None, "w": [None, 1.5]}


def test_chart_html_has_div_payload_noscript_and_table():
    h = chart_html(ch(note="Budget covers 1 / 2"), "en")
    assert '<div class="chart" id="c-stage" data-chart style="height:280px" role="img" aria-label="Projects by stage">' in h
    payload = re.search(r'<script type="application/json" id="c-stage-data">(.*?)</script>', h).group(1)
    assert json.loads(payload)["option"]["series"][0]["data"][0]["value"] == 3
    assert "<noscript>" in h and "needs JavaScript" in h and "Budget covers 1 / 2" in h
    table = h[h.index('<details class="data">'):]
    assert "<td>MP</td><td>3</td>" in table and "<td>POC</td><td>–</td>" in table
    assert "data-variant-for" not in h


def test_variants_render_a_customer_filter():
    h = chart_html(ch(id="gantt", variants={"Dell": {"series": []}, "Trimble": {"series": []}}), "en")
    assert '<select data-variant-for="c-gantt">' in h and '<option value="Dell">Dell</option>' in h and '<option value="">All</option>' in h


def test_echarts_tags_and_init_script():
    assert echarts_tag("static") == f'<script src="{STATIC_URL}"></script>'
    assert echarts_tag("inline").startswith("<script>") and len(echarts_tag("inline")) > 1_000_000   # min.js 第一個字元是換行
    with pytest.raises(ValueError):
        echarts_tag("cdn")
    assert "window.eisCharts" in INIT_JS and "offsetParent" in INIT_JS and "$fn" in INIT_JS
    assert scripts("static").endswith(f"<script>{INIT_JS}</script>")


def test_new_strings_exist_in_both_languages():
    v_en = {k for k in STRINGS["en"] if k.startswith("v_")}
    assert v_en and v_en == {k for k in STRINGS["zh"] if k.startswith("v_")}


def test_min_width_chart_scrolls_inside_its_card():
    h = chart_html(ch(min_width=720), "en")
    assert '<div class="wide"><div class="chart" id="c-stage" data-chart style="height:280px;min-width:720px"' in h
    assert '<div class="wide"><div class="chart"' not in chart_html(ch(), "en")
