"""網站圖示（瀏覽器分頁、書籤）：主色圓角方塊＋白色星號（Timeline 上的 MP 符號）。
內嵌成 data URI：不需要靜態檔，轉寄出去的單檔月報也帶得到（需求方 2026-10-03）。"""
from urllib.parse import quote
from .viz import tokens as T

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
       f'<rect width="32" height="32" rx="7" fill="{T.ACCENT}"/>'
       '<polygon points="16.0,6.8 18.5,13.4 25.5,13.7 20.0,18.1 21.9,24.9 16.0,21.0 10.1,24.9 12.0,18.1 6.5,13.7 13.5,13.4" fill="#fff" stroke="#fff" stroke-width="1.2" stroke-linejoin="round"/></svg>')
FAVICON = f'<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,{quote(SVG, safe=" /=:,.")}">'
