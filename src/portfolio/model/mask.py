"""任務文字的人名遮罩。寧可漏遮也不要把產品代號遮掉，所以第二條規則有 protect 與母音檢查。"""
from __future__ import annotations
import re
from ..config import normalize_name

MASK = "[name]"
P_LATIN_CJK = re.compile(r"[A-Za-z]+\d*[_ ][A-Za-z]+\d*\s*\([^)]*[一-鿿]+[^)]*\)")
P_UNDERSCORE = re.compile(r"\b([A-Za-z]+\d?)_([A-Za-z]+)\b")
P_NAME_DATE = re.compile(r"\b[A-Z][a-z]{2,}\d{4}\b")
VOWELS = set("aeiouAEIOU")


def _has_vowel(s: str) -> bool:
    return any(ch in VOWELS for ch in s)


def mask_names(text: str, protect: set[str]) -> tuple[str, int]:
    if not text:
        return "", 0
    count = 0
    text, n = P_LATIN_CJK.subn(MASK, text); count += n

    def repl(m: re.Match) -> str:
        nonlocal count
        a, b = m.group(1), m.group(2)
        if not (_has_vowel(a) and _has_vowel(b)):
            return m.group(0)
        if normalize_name(a) in protect or normalize_name(b) in protect:
            return m.group(0)
        count += 1
        return MASK
    text = P_UNDERSCORE.sub(repl, text)
    text, n = P_NAME_DATE.subn(MASK, text); count += n
    return text, count
