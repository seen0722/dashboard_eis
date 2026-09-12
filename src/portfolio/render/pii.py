"""輸出前的負向檢查。找到任何一項就不准寫出 HTML。"""
from __future__ import annotations
import re

P_EMPID = re.compile(r"\bLA\d{7}\b")
P_LATIN_CJK = re.compile(r"[A-Za-z]+\([一-鿿]{2,4}\)")


def find_pii(html: str, forbidden: set[str] = frozenset()) -> list[str]:
    hits = P_EMPID.findall(html) + P_LATIN_CJK.findall(html)
    hits += [f for f in sorted(forbidden) if f and f in html]
    return hits
