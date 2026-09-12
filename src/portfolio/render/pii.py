"""輸出前的負向檢查。找到任何一項就不准寫出 HTML。"""
from __future__ import annotations
import re

P_EMPID = re.compile(r"\bLA\d{7}\b")
P_NAME_CJK = re.compile(r"\b[A-Z][a-z]+\d?(?:[ _][A-Z][a-z]+\d?)?\([一-鿿]{2,3}\)")
P_UPPER_CJK = re.compile(r"\b[A-Z]+\d?_[A-Z]+\d?\([一-鿿]{2,3}\)")


def find_pii(html: str, forbidden: set[str] = frozenset()) -> list[str]:
    hits = P_EMPID.findall(html) + P_NAME_CJK.findall(html) + P_UPPER_CJK.findall(html)
    hits += [f for f in sorted(forbidden) if f and f in html]
    return hits
