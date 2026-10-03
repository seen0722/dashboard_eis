"""版面實測：每頁在 1440 與 375 寬度下無橫向溢出、每個 [data-chart] 都畫出 <svg>、沒有 console error，並截圖。
python scripts/check_layout.py --base http://127.0.0.1:8796 --month 202609 --code BR0000015346 --report out/report.html --out /tmp/shots"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

WIDTHS = (1440, 375)


def check(page, url: str, name: str, out: Path) -> list[str]:
    errs: list[str] = []
    page.on("console", lambda m: errs.append(f"{name}: console {m.type}: {m.text}") if m.type == "error" else None)
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(600)
    fails = []
    for w in WIDTHS:
        page.set_viewport_size({"width": w, "height": 900})
        page.wait_for_timeout(400)
        sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        if sw > iw:
            fails.append(f"{name} @{w}: horizontal overflow {sw} > {iw}")
        empty = page.evaluate("""[...document.querySelectorAll('[data-chart]')].filter(el => el.offsetParent !== null && !el.querySelector('svg')).map(el => el.id)""")
        if empty:
            fails.append(f"{name} @{w}: charts not drawn {empty}")
        page.screenshot(path=str(out / f"{name}_{w}.png"), full_page=True)
    return fails + errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--month", required=True); ap.add_argument("--code", required=True)
    ap.add_argument("--report", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    pages = {"overview": f"{a.base}/ui/{a.month}/", "decisions": f"{a.base}/ui/{a.month}/decisions", "loads": f"{a.base}/ui/{a.month}/loads",
             "health": f"{a.base}/ui/{a.month}/health", "project": f"{a.base}/ui/{a.month}/projects/{a.code}",
             "report": Path(a.report).resolve().as_uri()}
    fails: list[str] = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, url in pages.items():
            fails += check(b.new_page(), url, name, out)
        page = b.new_page(); page.goto(pages["report"], wait_until="networkidle")    # 附錄切換後 PVA 圖要畫出來
        page.select_option("#pick", index=1); page.wait_for_timeout(500)
        if page.evaluate("[...document.querySelectorAll('#projects .proj')].filter(p => p.style.display !== 'none').some(p => [...p.querySelectorAll('[data-chart]')].some(c => !c.querySelector('svg')))"):
            fails.append("report: appendix charts not drawn after switching project")
        b.close()
    print("\n".join(fails) or f"all checks passed; screenshots in {out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
