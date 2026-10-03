"""產品類別圖示（2026-10-03，需求方交由我決定）：只放 Projects 列表的 Product 欄；對照表人工維護，對不上就不畫。"""
from src.portfolio.render.viz.category_icons import ICONS, category_icon


def test_every_category_in_the_briefing_has_an_icon():
    for c in ("Tablet", "NB", "Box PC", "Conference Component", "Photo Frame", "AI Card", "AI PC", "PCBA",
              "Industrial Component", "Dock", "Rugged Cell Phone", "POS", "AIO PC"):
        assert c in ICONS, c


def test_icon_is_decorative_inline_svg_in_the_ink_colour():
    svg = category_icon("Tablet")
    assert svg.startswith('<svg class="cat-ic"') and 'aria-hidden="true"' in svg and 'stroke="currentColor"' in svg
    assert category_icon("tablet") == svg                                                 # 大小寫不拘


def test_unknown_or_blank_category_draws_nothing():
    """自由填寫的欄位：對不上就不畫，不猜（AGENTS.md 第一守則）。"""
    assert category_icon("Smart Speaker") == "" and category_icon("") == "" and category_icon(None) == ""
