"""/ui/ 首頁：這是什麼、資料多新、從哪裡開始。中英並列（需求方 2026-10-01）。

文字來源：標題、說明、名詞定義盡量沿用月報 render/strings.py 的中英文字串（不另編）；只有網頁專用的幾句
（唯讀說明、入口說明）寫在這裡。數字全部取自最新快照。
"""
from __future__ import annotations
from html import escape as e
from ...portfolio.render.page import stage_strip_html
from ...portfolio.render.strings import t
from .pages_overview import months_body
from .shell import meta_line

ZH = "zh-Hant"

READ_ONLY = ("Read-only. Same data as the monthly report and the MCP tools; nothing is inferred or filled in.",
             "唯讀。資料與月報、MCP 工具相同，不推算、不補值。")

# (path, 英文名, 中文名, 英文說明, 中文說明)
ENTRIES = (
    ("", "Overview", "總覽", "KPIs, charts and the six-month timeline.", "KPI、圖表與六個月時程。"),
    ("decisions", "Decisions", "本月要決定的事", "What needs a decision this month, with evidence.", "本月要決定的事，附證據。"),
    ("projects", "Projects", "專案", "Every project; filter by stage, type, category, group or customer.",
     "全部專案，可依階段、類型、類別、產品群或客戶篩選。"),
    ("loads", "Loads", "部門負載", "Department load by month: where spare capacity is left.", "各部門每月負載：哪裡還有餘裕。"),
    ("health", "Data health", "資料健康度", "What the source files could not answer, and past-month numbers that changed.",
     "來源檔答不出來的事，以及被改過的過去月份數字。"),
    ("report.html", "Monthly report", "月報", "The single-page report, ready to forward.", "可直接轉寄的單頁月報。"),
)


def bi(en: str, zh: str, cls: str = "") -> str:
    """一段中英並列文字：英文在上、中文在下（標 lang，螢幕閱讀器才會用中文發音）。輸入是純文字，這裡負責跳脫。"""
    c = f' class="{cls}"' if cls else ""
    return f'<p{c}><span>{e(en)}</span><span class="zh" lang="{ZH}">{e(zh)}</span></p>'


def exception_titles(snap: dict, th: dict, lang: str) -> list[str]:
    """與 render/page.py::_exceptions 相同的標題組法（同一組 kw、同一個 legacy 退路），只取標題。
    tests 以「每個標題都出現在 exceptions_html 輸出裡」守住兩邊不漂移。"""
    out = []
    for x in snap["exceptions"]:
        k = x["title"]
        kw = {"n": x["count"], "days": th["mp_slip_days"], "pct": th["spare_capacity_pct"], "full": x.get("ask_data", "")}
        kw.update(x.get("extra", {}))
        if k == "suspended_charging" and "suspended" not in kw:
            k = "suspended_charging_legacy"
        out.append(t(lang, f"ex_{k}_title", **kw))
    return out


SUMMARY_ATTRS = 'data-expand="expand · 展開" data-collapse="collapse · 收合"'   # 與月報 task 表的 summary 同一形狀：左標題、右動作字樣


def _intro() -> str:
    return (f'<section class="intro">{bi(t("en", "intro"), t("zh", "intro"), "lead")}'
            f'{bi(*READ_ONLY, "dim")}</section>')


def _latest(snap: dict, th: dict) -> str:
    month = snap["meta"]["report_month"]; lm = snap["meta"]["latest_month"]
    en, zh = exception_titles(snap, th, "en"), exception_titles(snap, th, "zh")
    items = "".join(f'<li><a href="/ui/{e(month)}/"><span class="n">{x["rank"]}</span><span><b>{e(a)}</b>'
                    f'<span class="zh" lang="{ZH}">{e(b)}</span></span></a></li>'
                    for x, a, b in zip(snap["exceptions"], en, zh))
    n = len(snap["exceptions"])
    decisions = (f'<h3>{n} decision{"" if n == 1 else "s"} this month <span class="zh-inline" lang="{ZH}">本月 {n} 件要決定</span></h3>'
                 f'<ol class="home-ex">{items}</ol>') if items else bi("Nothing needs a decision this month.", "本月沒有需要決定的事。", "empty")
    search = (f'<form method="get" action="/ui/{e(month)}/projects" class="home-search">'
              f'<input type="search" name="q" placeholder="Project code or name · 專案代碼或名稱" aria-label="Find a project">'
              f'<button>Find</button></form>')
    return (f'<section class="latest"><h2>Latest <span class="zh-inline" lang="{ZH}">最新資料</span></h2>{meta_line(snap["meta"])}'
            f'{decisions}{stage_strip_html(snap, "en", lm)}{search}</section>')


def _entries(month: str) -> str:
    rows = "".join(f'<li><a href="/ui/{e(month)}/{path}"><b>{e(en)}</b> <span class="zh-inline" lang="{ZH}">{e(zh)}</span></a>'
                   f'{bi(den, dzh, "dim")}</li>' for path, en, zh, den, dzh in ENTRIES)
    return f'<section><h2>Where to start <span class="zh-inline" lang="{ZH}">從哪裡開始</span></h2><ul class="entries">{rows}</ul></section>'


def _agent() -> str:
    return (f'<section><h2>Use it from an AI agent <span class="zh-inline" lang="{ZH}">用 AI agent 查詢</span></h2>'
            f'{bi("Ask about these projects from Claude or OpenCode through the EIS MCP server. The setup page has a prompt your agent can follow.", "透過 EIS MCP server，在 Claude 或 OpenCode 裡直接問這些專案。設定頁有一段可以直接貼給 agent 照做的提示。", "dim")}'
            f'<p><a href="/ui/mcp"><b>MCP setup</b> <span class="zh-inline" lang="{ZH}">MCP 設定說明</span></a></p></section>')


def _terms() -> str:
    """名詞定義沿用月報字串或網頁既有說明，不另編新說法。"""
    terms = (
        # 這兩則取自月報 s_decisions_lead / s_health_lead 與總覽頁 lead，去掉指涉月報版面的部分（「above」「only here」）
        ("Decisions", "本月要決定的事", "Ranked by urgency. Each item carries its evidence and its source.", "依急迫排序，每條附證據與出處。"),
        ("Data health", "資料健康度", "What the source files could not answer. Decide means the BU head has to act; track is handled by the report owner.",
         "來源檔案回答不了的事。「決定」要主管出面，「追蹤」由報表維護者處理。"),
        ("FTE", "FTE", t("en", "foot_1"), t("zh", "foot_1")),
        ("Load / util %", "負載 / util %", t("en", "foot_2"), t("zh", "foot_2")),
        ("Corrections", "歷史修正", ENTRIES[3][3], ENTRIES[3][4]),
    )
    rows = "".join(f'<dt>{e(a)} <span class="zh-inline" lang="{ZH}">{e(b)}</span></dt><dd>{bi(c, d)}</dd>' for a, b, c, d in terms)
    return f'<details class="home-more"><summary {SUMMARY_ATTRS}><span>Terms <span class="zh-inline" lang="{ZH}">名詞</span></span></summary><dl class="terms">{rows}</dl></details>'


def _history(months: list[dict]) -> str:
    n = len(months)
    return (f'<details class="home-more"><summary {SUMMARY_ATTRS}><span>Data history <span class="zh-inline" lang="{ZH}">資料歷程</span> · {n} month{"" if n == 1 else "s"}</span></summary>'
            f'{months_body(months, heading=False)}</details>')


def home_body(months: list[dict], snap: dict | None, th: dict, broken_month: str | None = None) -> str:
    """snap 為最新可讀（ok）月份的快照，沒有則 None。broken_month 是比它更新、卻讀不出來的月份（有就顯示警告）。"""
    parts = [_intro()]
    if broken_month:
        parts.append(f'<section>{bi(f"The snapshot for {broken_month} could not be read; ask an uploader to run ingest_month again.", f"{broken_month} 的快照讀不出來，請上傳者重新執行 ingest_month。", "sig")}</section>')
    if snap is not None:
        parts += [_latest(snap, th), _entries(snap["meta"]["report_month"])]
    elif not broken_month:
        parts.append(f'<section>{bi("Nothing ingested yet. An uploader must upload a month and call ingest_month first.", "尚未匯入任何月份。請上傳者先上傳資料並執行 ingest_month。", "empty")}</section>')
    parts.append(_agent())
    parts.append(f'<section class="home-foot">{_terms()}{_history(months) if months else ""}</section>')
    return "".join(parts)
