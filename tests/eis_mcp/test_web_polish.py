"""2026-10-03 make-interfaces-feel-better review：焦點、點擊範圍、狀態轉換、按下回饋、斷行、圓角、字體平滑。"""
import re
import pytest
from tests.eis_mcp.test_web import html


def css() -> str:
    from src.portfolio.render.css import CSS
    from src.eis_mcp.web.shell import WEB_CSS
    return CSS + WEB_CSS


def test_clickable_cards_show_a_visible_focus_ring_not_only_a_shadow():
    c = css()
    assert "outline:none" not in c
    assert "a.kpi:focus-visible,a.status-card:focus-visible{outline:2px solid var(--accent);outline-offset:2px}" in c


def test_state_changes_transition_named_properties_only():
    c = css()
    assert "transition:all" not in c.replace(" ", "") and "will-change" not in c
    assert "transition-property:box-shadow,background-color,border-color,color,transform;transition-duration:150ms" in c


def test_buttons_and_cards_respond_when_pressed():
    c = css()
    assert "button:active{transform:scale(.97)}" in c and "a.kpi:active,a.status-card:active{" in c
    assert re.search(r"prefers-reduced-motion: reduce\)\{[^}]*transform:none", c)


def test_headings_balance_and_short_text_wraps_pretty():
    c = css()
    assert "h1,h2,h3{text-wrap:balance}" in c and ".k-sub,.lead,.note,.card-sub{text-wrap:pretty}" in c


def test_radius_comes_from_three_tokens():
    c = css()
    assert "--r-ctl:6px;--r-card:10px;--r-pill:999px" in c
    raw = set(re.findall(r"border-radius:(\d+)px", c))
    assert raw <= {"2"}, raw                                                              # 只剩圖例色票的 2px


def test_macos_font_smoothing():
    assert "html{-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}" in css()


@pytest.mark.parametrize("path, sel, min_h", [
    ("/projects", "a.sort", 32), ("/health", "details.more>summary", 32), ("/decisions", "a.chip", 30)])
def test_small_controls_have_usable_hit_areas(ingested, path, sel, min_h):
    """量的是 CSS 撐出來的可點高度；用真瀏覽器量在 test 之外（scratchpad 腳本），這裡鎖住 CSS 規則存在。"""
    c = css()
    rule = {"a.sort": "table.plist a.sort{display:block;padding:10px 0;margin:-10px 0}",
            "details.more>summary": "details.more summary{display:inline;padding:10px 4px;margin:-10px -4px;",
            "a.chip": "a.chip{display:inline-flex;align-items:center;min-height:30px}"}[sel]
    assert rule in c


def test_every_page_and_the_report_carry_the_site_icon(ingested):
    """2026-10-03 需求方：瀏覽器分頁沒有圖示。內嵌 SVG（data URI），不另放靜態檔，轉寄出去的月報也帶得到。"""
    from src.eis_mcp.web.icon import FAVICON
    assert FAVICON.startswith('<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,')
    assert "%232563EB" in FAVICON                                                          # 主色（# 已 URL 編碼）
    for path in ("/ui/", "/ui/202609/", "/ui/202609/projects"):
        assert FAVICON in html(ingested, path), path
    assert FAVICON in ingested.state.eis.store.report_html("202609")                       # ingest 產生的月報檔


def test_safari_gets_a_png_touch_icon_as_well(ingested):
    """2026-10-03 需求方截圖：Safari 起始頁顯示 IP 字母圓圈——它用 apple-touch-icon（PNG），不吃 SVG。
    PNG 走靜態檔、不內嵌：base64 隨機字串可能被 PII 檢查誤判（測試曾撞到 "Bob"）。"""
    from tests.eis_mcp.test_web import get
    from src.portfolio.render.icon import PNG_180, WEB_FAVICON
    assert PNG_180[:8] == b"\x89PNG\r\n\x1a\n"
    assert '<link rel="apple-touch-icon" href="/ui/static/icon-180.png">' in WEB_FAVICON
    assert WEB_FAVICON in html(ingested, "/ui/") and "data:image/png;base64" not in html(ingested, "/ui/")
    r = get(ingested, "/ui/static/icon-180.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content == PNG_180
    assert "data:image/png;base64" not in ingested.state.eis.store.report_html("202609")  # 月報只帶 SVG


def test_product_cell_shows_the_category_icon_and_skips_unknown_ones(ingested):
    import json
    store = ingested.state.eis.store
    f = store.snapshot_dir("202609") / "portfolio.json"
    snap = json.loads(f.read_text(encoding="utf-8"))
    base = snap["projects"][0]
    snap["projects"] += [dict(base, code="BR0000000021", name="Tabby", category="Tablet"),
                         dict(base, code="BR0000000022", name="Oddity", category="Smart Speaker")]
    f.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8"); store.invalidate()
    t = html(ingested, "/ui/202609/projects")
    row = lambda n: t[t.index(f'">{n}</a>'):][:t[t.index(f'">{n}</a>'):].index("</tr>")]   # noqa: E731
    assert '<div class="prod"><svg class="cat-ic"' in row("Tabby")
    assert "cat-ic" not in row("Oddity") and "Smart Speaker" in row("Oddity")             # 對不上：只有文字
