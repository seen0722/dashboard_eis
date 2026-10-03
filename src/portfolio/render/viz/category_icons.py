"""產品類別線條圖示（2026-10-03）：24 格、1.5px 線寬、圓角線頭，顏色跟文字走（currentColor）。
只用在 Projects 列表的 Product 欄。Briefing 的 Category 是自由填寫欄位：對照表人工維護，對不上就不畫，不猜。"""
from __future__ import annotations

# 類別（Briefing 原文）→ SVG 內容。容易在小尺寸混淆的幾個刻意拉開外形：
# AI Card＝側面 PCIe 卡（擋板＋風扇）、AI PC＝處理器晶片＋星芒、AIO PC＝螢幕＋厚下巴＋弧形支架、Photo Frame＝直立相框＋腳架。
ICONS = {
    "Tablet": '<rect x="5" y="2.5" width="14" height="19" rx="2.2"/><path d="M10.5 18.5h3"/>',
    "NB": '<rect x="4.5" y="5" width="15" height="10.5" rx="1.5"/><path d="M2.5 18.5h19l-1.5-3H4z"/>',
    "Box PC": '<rect x="3" y="7" width="18" height="10" rx="2"/><path d="M6.5 10.5v3M9 10.5v3M11.5 10.5v3"/><circle cx="17" cy="12" r="1.2"/>',
    "Conference Component": '<rect x="2.5" y="8.5" width="19" height="7" rx="3.5"/><circle cx="12" cy="12" r="2.6"/><circle cx="12" cy="12" r=".6"/>'
                            '<path d="M6 12h.01M18 12h.01"/>',
    "Photo Frame": '<rect x="6" y="2.5" width="12" height="16" rx="1.2"/><rect x="8.5" y="5" width="7" height="8" rx=".6"/><path d="M14 18.5l2.5 3"/>',
    "AI Card": '<path d="M3 5.5v13"/><path d="M3 7h17a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H3"/><circle cx="14" cy="11.5" r="2.8"/>'
               '<path d="M6.5 16v2.5h5V16"/>',
    "AI PC": '<rect x="6" y="6" width="12" height="12" rx="1.6"/><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3"/>'
             '<path d="M12 9.2l.8 1.9 1.9.9-1.9.9-.8 1.9-.8-1.9-1.9-.9 1.9-.9z"/>',
    "PCBA": '<rect x="3" y="3" width="18" height="18" rx="2"/><rect x="9" y="9" width="6" height="6" rx=".8"/><path d="M12 3v6M12 15v6M3 12h6M15 12h6"/>',
    "Industrial Component": '<path d="M12 2.8l7.8 4.6v9.2L12 21.2l-7.8-4.6V7.4z"/><circle cx="12" cy="12" r="3.2"/>',
    "Dock": '<rect x="3" y="12.5" width="18" height="6.5" rx="2"/><path d="M6.5 15.75h2M10.5 15.75h1.5M14 15.75h1M17 15.75h.5"/>'
            '<path d="M8 12.5V6.5a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v6"/>',
    "Rugged Cell Phone": '<rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M5.5 5v3M5.5 16v3M18.5 5v3M18.5 16v3"/><path d="M10.5 18.5h3"/>',
    "POS": '<rect x="6" y="3" width="12" height="9" rx="1.5"/><path d="M4.5 21l2-7h11l2 7z"/><path d="M9 17.5h6"/>',
    "AIO PC": '<rect x="2.5" y="3" width="19" height="14" rx="1.5"/><path d="M2.5 13.5h19"/><path d="M10.5 17c0 2-1 3.5-3 4h9c-2-.5-3-2-3-4"/>',
}
_BY_KEY = {k.casefold(): v for k, v in ICONS.items()}


def category_icon(category: str | None, size: int = 20) -> str:
    """類別圖示的 inline SVG；對不上回空字串。裝飾用（aria-hidden），旁邊一定有文字。"""
    body = _BY_KEY.get((category or "").strip().casefold())
    if not body:
        return ""
    return (f'<svg class="cat-ic" width="{size}" height="{size}" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" '
            f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
