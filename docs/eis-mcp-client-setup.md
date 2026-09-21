# EIS MCP server — Client 連線設定（給 OpenCode / Claude 照著做）

> 給 AI agent 的指示：依序執行下面的步驟，每一步都要看到預期結果才進下一步。
> 需要使用者提供兩個值：`<HOST>`（server 主機名或 IP，含 port，例如 `10.1.2.3:8765`）與 `<TOKEN>`（管理者發的 Bearer token）。
> 沒有這兩個值就先向使用者要，不要猜。token 不要印在對話裡、不要寫進任何會進版控的檔案。

## 0. 這是什麼

EIS MCP server 是公司內網的 HTTP 服務，提供 BU10 專案的 EIS 狀態（stage、里程碑、人力、例外事項）。
協定：MCP Streamable HTTP，端點 `http://<HOST>/mcp`，認證 `Authorization: Bearer <TOKEN>`。
server 端不含任何 LLM；模型在 client 端。

## 0. 公司電腦有 proxy 時：內網 IP 要加進不走 proxy 的例外（必做）

OpenCode 走環境變數 `NO_PROXY`，不看 Windows 系統 proxy 設定。已有 `NO_PROXY` 就用逗號把 `<HOST>` 的 IP 接在後面，不要蓋掉。

Windows（PowerShell，設一次永久生效）：

```powershell
[Environment]::SetEnvironmentVariable("NO_PROXY", "<HOST的IP>,localhost,127.0.0.1", "User")
[Environment]::SetEnvironmentVariable("no_proxy", "<HOST的IP>,localhost,127.0.0.1", "User")
```

macOS / Linux：在 `~/.zshrc`（或 `~/.bashrc`）加 `export NO_PROXY=<HOST的IP>,localhost,127.0.0.1` 與 `export no_proxy=$NO_PROXY`。

設完**關閉並重開終端機與 OpenCode**。第 1 步回 `000`、`403` 或 `502` 多半是這步沒生效。長期做法是請 IT 給 server 一個公司網域的 DNS 名稱（proxy 的 PAC 通常已對公司網域直連）。

## 1. 連線前檢查（一定要做）

```bash
curl -s -m 5 -o /dev/null -w "%{http_code}\n" http://<HOST>/mcp
```

| 結果 | 意義 | 下一步 |
|---|---|---|
| `401` | 網路通，只是沒帶 token | 進第 2 步 |
| `000` 或 timeout | 連不到主機或 port 被擋 | 停下來告訴使用者：確認同一內網、VM 的 8765 有開 |
| 其他 | 主機在但不是 MCP server | 停下來告訴使用者，附上狀態碼 |

```bash
curl -s -m 5 -H "Authorization: Bearer <TOKEN>" -o /dev/null -w "%{http_code}\n" http://<HOST>/mcp
```

| 結果 | 意義 | 下一步 |
|---|---|---|
| `400` | token 正確（MCP 端點對純 GET 本來就回 400） | 進第 2 步 |
| `401` | token 錯 | 停下來請使用者重新取得 token |
| `421` | server 的 `--allowed-host` 沒包含 `<HOST>` | 停下來告訴使用者：請管理者在 server 的 `/etc/eis-mcp/env` 加 `--allowed-host <HOST>` 後 `systemctl restart eis-mcp` |

## 2. 存 token（不要寫死在設定檔）

macOS / Linux：

```bash
mkdir -p ~/.secrets && chmod 700 ~/.secrets
printf '%s' '<TOKEN>' > ~/.secrets/eis_mcp_token && chmod 600 ~/.secrets/eis_mcp_token
```

（用 `printf '%s'`，不要用 `echo`，避免多一個換行。）

Windows（PowerShell）：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.secrets" | Out-Null
[IO.File]::WriteAllText("$env:USERPROFILE\.secrets\eis_mcp_token", "<TOKEN>")
```

## 3. OpenCode 設定

設定檔位置：
- macOS / Linux：`~/.config/opencode/opencode.json`（或 `.jsonc`）
- Windows：`%USERPROFILE%\.config\opencode\opencode.json`

在 `mcp` 區塊加入（已有其他 server 就併進去，不要蓋掉）：

```json
{
  "mcp": {
    "eis": {
      "type": "remote",
      "url": "http://<HOST>/mcp",
      "headers": { "Authorization": "Bearer {file:~/.secrets/eis_mcp_token}" }
    }
  }
}
```

Windows 若 `{file:~/...}` 無法展開，改用絕對路徑 `{file:C:/Users/<user>/.secrets/eis_mcp_token}`，或直接寫 `"Bearer <TOKEN>"`（設定檔要設成只有本人可讀）。

驗證：

```bash
opencode mcp list
```

預期看到 `✓ eis connected`。沒有的話回到第 1 步的兩個 curl 重測。

## 3a. Claude Code（替代）

```bash
claude mcp add --transport http eis http://<HOST>/mcp --header "Authorization: Bearer <TOKEN>"
claude mcp list
```

## 3b. Claude Desktop（替代）

設定檔的 `mcpServers` 加：

```json
{"mcpServers": {"eis": {"url": "http://<HOST>/mcp",
                         "headers": {"Authorization": "Bearer <TOKEN>"}}}}
```

## 4. 第一次使用

在 OpenCode 裡問：「用 eis 列出有哪些月份的資料」→ 會呼叫 `eis_list_months`。

- 回傳有月份且 `status: ok` → 可以開始問專案（見第 5 節）。
- 回 `no_snapshot` → server 還沒 ingest 任何月份。這需要 **uploader** 角色：從有 EIS 檔的電腦執行
  `EIS_URL=http://<HOST> EIS_TOKEN=<uploader token> scripts/eis-upload.sh 202608 ./input-08`，
  然後在 OpenCode 說「ingest 202608」。viewer token 做不了這件事，回 `forbidden` 是正常的。

## 5. 可以問什麼

| 想知道 | 問法 | 會用到的 tool |
|---|---|---|
| 有哪些月份 | 「有哪些月份的資料」 | `list_months` |
| 單一專案 | 「THORPE 現在什麼 stage、MP 是哪天」 | `get_project` |
| 篩選清單 | 「列出所有 Execution 階段的案子」「AMD 的案子」 | `search_projects` |
| 本月要決定的事 | 「這個月的 exceptions」「資料健康度」 | `get_exceptions`、`get_health` |
| 里程碑 | 「未來八週有哪些里程碑」「哪些已逾期」 | `get_upcoming_milestones` |
| 部門負載 | 「哪些部門負載超過 100%」（`min_util` 是百分比） | `get_dept_loads`、`get_capacity` |
| 跨月比較 | 「THORPE 9 月和 8 月差在哪」「歷史數字被改過的」 | `diff_project`、`get_corrections` |
| 月報 HTML | 讀 resource `eis://YYYYMM/report.html` | resource |

回答時請引用回傳的 `meta.report_month`（快照月份 YYYYMM）；`meta.latest_month` 是 1–12 的月份序號，不是 YYYYMM。所有數字都來自快照，server 不會推算或補值；tool 回 `rejected_pii` 表示該回應含個資形狀字串被擋下，回報使用者即可，不要重試繞過。

## 6. 疑難排解

| 現象 | 處理 |
|---|---|
| `opencode mcp list` 顯示 eis 連不上 | 回第 1 步兩個 curl；`000` 是網路、`401` 是 token、`421` 是 allowed-host |
| tool 回 `unknown_month` | 回應裡有可用月份清單，換一個 |
| tool 回 `forbidden` | 這個 token 是 viewer，該操作需要 uploader |
| 閒置一陣子後出現 `Session not found` | server 版本太舊（stateful session 30 分鐘過期）；請管理者 `git pull && sudo deploy/install.sh` 更新，之後不會再發生 |
| tool 回 `snapshot_broken` | 請管理者重跑該月 `ingest_month` |

完整安裝與營運手冊：`docs/eis-mcp-install.md`；設計：`docs/superpowers/specs/2026-09-18-eis-mcp-server-design.md`。
