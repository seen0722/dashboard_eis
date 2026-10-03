"""網站圖示（瀏覽器分頁、書籤）：主色圓角方塊＋白色星號（Timeline 上的 MP 符號）。
內嵌成 data URI：不需要靜態檔，轉寄出去的單檔月報也帶得到（需求方 2026-10-03）。"""
from pathlib import Path
from urllib.parse import quote
from .viz import tokens as T

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
       f'<rect width="32" height="32" rx="7" fill="{T.ACCENT}"/>'
       '<polygon points="16.0,6.8 18.5,13.4 25.5,13.7 20.0,18.1 21.9,24.9 16.0,21.0 10.1,24.9 12.0,18.1 6.5,13.7 13.5,13.4" fill="#fff" stroke="#fff" stroke-width="1.2" stroke-linejoin="round"/></svg>')
FAVICON = f'<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,{quote(SVG, safe=" /=:,.")}">'

# Safari 起始頁／我的最愛方塊與舊版 Safari 分頁不吃 SVG：另附 180×180 PNG（同一個 SVG 渲染、滿版正方形，Apple 自己裁圓角）。
# PNG 走 /ui/static 靜態檔，不內嵌 base64：隨機字串可能碰巧像工號或姓名，讓月報的 PII 檢查擋下整個月（2026-10-03 測試就撞到 "Bob"）。
# 2026-10-03 VM 部署事故：這個檔被 .gitignore 的 *.png 擋掉，git pull 拿不到，import 時讀檔失敗讓 server 起不來。
# 現在 .gitignore 已放行；讀不到時只少 PNG 圖示（路由 404、不輸出 <link>），網站照常。


def load_png(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


PNG_180 = load_png(Path(__file__).with_name("icon-180.png"))
PNG_PATH = "/ui/static/icon-180.png"
WEB_FAVICON = FAVICON + (f'<link rel="icon" type="image/png" sizes="180x180" href="{PNG_PATH}"><link rel="apple-touch-icon" href="{PNG_PATH}">'
                         if PNG_180 else "")
