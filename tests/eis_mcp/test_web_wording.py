"""2026-10-03 需求方定案的用語（AGENTS.md「用語」一節）：計畫人力＝Plan、EIS 填報＝reported、負載率＝Load；
並去掉自創術語（second identity、charging、briefed、snapshot 給使用者看）與口號式說明。"""
import re
import pytest
from tests.eis_mcp.conftest import TODAY
from tests.eis_mcp.test_web import html

BANNED = re.compile(r"keyed|\butil\b|second identity|charging|\bbriefed\b|Why it counts|[Bb]udget|One chart, three facts|"
                    r"Exceptions first|could not answer|snapshot", re.I)


def test_english_strings_use_the_team_glossary():
    from src.portfolio.render.strings import STRINGS
    bad = {k: v for k, v in STRINGS["en"].items() if isinstance(v, str) and BANNED.search(re.sub(r"\{\w+\}", "", v))}
    assert bad == {}


@pytest.mark.parametrize("path", ["/", "/decisions", "/projects", "/projects/BR0000015346", "/loads", "/health"])
def test_pages_use_the_team_glossary(ingested, path):
    t = html(ingested, f"/ui/202609{path}?today={TODAY}")
    body = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", t, flags=re.S)
    hits = sorted({m.group(0) for m in BANNED.finditer(body)})
    assert hits == [], hits
