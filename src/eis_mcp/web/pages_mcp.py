"""/ui/mcp（給人看，中英並列）與 /ui/mcp.md（給 agent 讀）：怎麼把 EIS MCP server 接到 Claude / OpenCode。

單一來源：/ui/mcp.md 就是 docs/eis-mcp-client-setup.md，只把 `<HOST>` 換成使用者開網頁時用的位址，
再附上 server 實際註冊的 tools（list_tools 產生，不手寫，不會過時）。token 永遠不出現在頁面上——文件本來就要 agent 向使用者要。
"""
from __future__ import annotations
import re
from html import escape as e
from pathlib import Path

ZH = "zh-Hant"


def bi(en: str, zh: str, cls: str = "") -> str:
    """一段中英並列文字：英文在上、中文在下（標 lang，螢幕閱讀器才會用中文發音）。輸入是純文字，這裡負責跳脫。"""
    c = f' class="{cls}"' if cls else ""
    return f'<p{c}><span>{e(en)}</span><span class="zh" lang="{ZH}">{e(zh)}</span></p>'

GUIDE = Path(__file__).resolve().parents[3] / "docs" / "eis-mcp-client-setup.md"   # deploy/install.sh 會一併複製這個檔
HOST_RE = re.compile(r"^[A-Za-z0-9.\-]+(:\d{1,5})?$")


class GuideMissing(Exception):
    pass


def host_of(raw: str | None) -> str | None:
    """Host header 只接受「主機名或 IP，可帶 port」；其他一律不用（保留 <HOST>），避免把奇怪的字串寫進安裝文件。"""
    return raw if raw and HOST_RE.match(raw) else None


def first_sentence(doc: str | None) -> str:
    text = " ".join((doc or "").split())
    m = re.match(r"(.+?\.)(\s|$)", text)
    return m.group(1) if m else text


def tools_markdown(tools: list[tuple[str, str]]) -> str:
    rows = "\n".join(f"| `{n}` | {d.replace('|', chr(92) + '|')} |" for n, d in tools)   # 說明裡的 | 要跳脫
    return ("\n\n## Tools on this server\n\n"
            "> Generated from the running server. OpenCode shows them with an `eis_` prefix (e.g. `eis_get_project`).\n\n"
            f"| Tool | What it does |\n|---|---|\n{rows}\n")


def guide_markdown(host: str | None, tools: list[tuple[str, str]]) -> str:
    if not GUIDE.exists():
        raise GuideMissing(str(GUIDE))
    md = GUIDE.read_text(encoding="utf-8")
    if host:
        # 文件開頭要 agent 向使用者要 <HOST> 與 <TOKEN>；server 已知 host，只剩 token 要問
        md = md.replace("<HOST>", host)
        md = re.sub(r"^> 需要使用者提供兩個值：.*$", f"> 這份文件由 server 提供，server 位址已填好：`{host}`。只需要向使用者要 `<TOKEN>`（管理者發的 Bearer token）。",
                    md, count=1, flags=re.M)
        md = md.replace("沒有這兩個值就先向使用者要", "沒有 token 就先向使用者要", 1)
    return md + tools_markdown(tools)


def mcp_body(host: str | None, tools: list[tuple[str, str]]) -> str:
    h = host or "<HOST>"
    endpoint, md_url = f"http://{h}/mcp", f"http://{h}/ui/mcp.md"
    prompt_en = f"Read {md_url} and follow it to connect the EIS MCP server. Ask me for the token; do not guess it."
    prompt_zh = f"閱讀 {md_url} 並照著步驟連上 EIS MCP server。token 請向我索取，不要猜。"
    guide_note = ("" if GUIDE.exists() else
                  bi("The full setup guide is not installed on this server; ask the server owner to re-run deploy/install.sh.",
                     "這台 server 沒有安裝完整的設定文件，請管理者重新執行 deploy/install.sh。", "sig"))
    rows = "".join(f"<tr><td><code>{e(n)}</code></td><td>{e(d)}</td></tr>" for n, d in tools)
    return (f'<section class="intro">'
            f'{bi("Ask about BU10 projects from Claude or OpenCode. The MCP server answers with the same data as these pages; the model runs on your side.", "在 Claude 或 OpenCode 裡直接問 BU10 專案。MCP server 回的資料與這些網頁相同，模型在你的電腦端執行。", "lead")}'
            f'</section>'
            f'<section><h2>Connection <span class="zh-inline" lang="{ZH}">連線資訊</span></h2>'
            f'<div class="kv"><span>Endpoint</span><span><code>{e(endpoint)}</code></span>'
            f'<span>Protocol</span><span>MCP Streamable HTTP</span>'
            f'<span>Auth</span><span><code>Authorization: Bearer &lt;TOKEN&gt;</code></span></div>'
            f'{bi("You need a token from the server owner: viewer to ask questions, uploader to ingest a month. Never paste it into shared files.", "需要向管理者索取 token：viewer 可以查詢，uploader 才能匯入月份。不要貼進共用檔案或版控。", "dim")}'
            f'{bi("The endpoint uses the address you opened this page with; if the server owner gave you another address, use that.", "端點用的是你開這個網頁時的位址；管理者若給你別的位址，以管理者的為準。", "dim")}'
            f'</section>'
            f'<section><h2>Let an AI agent set it up <span class="zh-inline" lang="{ZH}">讓 AI agent 幫你安裝</span></h2>'
            f'{bi("Paste this into Claude Code or OpenCode:", "把下面這段貼給 Claude Code 或 OpenCode：", "lead")}'
            f'<pre class="prompt">{e(prompt_en)}</pre><pre class="prompt" lang="{ZH}">{e(prompt_zh)}</pre>'
            f'<p><a href="/ui/mcp.md">Setup guide for agents (mcp.md)</a> <span class="zh-inline" lang="{ZH}">給 agent 讀的設定文件</span></p>{guide_note}'
            f'</section>'
            f'<section><h2>Set it up yourself <span class="zh-inline" lang="{ZH}">自己安裝</span></h2>'
            f'{bi("Claude Code, one command (replace <TOKEN>):", "Claude Code 一行指令（把 <TOKEN> 換成你的 token）：", "lead")}'
            f'<pre class="prompt">{e(f"claude mcp add --transport http eis {endpoint} --header \"Authorization: Bearer <TOKEN>\"")}</pre>'
            f'{bi("OpenCode, Claude Desktop, proxy settings and troubleshooting are in the setup guide.", "OpenCode、Claude Desktop、proxy 設定與疑難排解見設定文件。", "dim")}'
            f'</section>'
            f'<section><h2>Tools on this server <span class="zh-inline" lang="{ZH}">這台 server 提供的 tools</span></h2>'
            f'<div class="wide"><table><thead><tr><th>Tool</th><th>What it does</th></tr></thead><tbody>{rows}</tbody></table></div>'
            f'</section>')
