# EIS MCP Server 安裝手冊

版本：2026-09-19（repo `seen0722/dashboard_eis`，main 8517857 之後）
適用：內網 Linux 主機（Ubuntu 22.04+ / Debian 12+ / RHEL 9+，需 systemd）；client 端 OpenCode、Claude Code、Claude Desktop。

---

## 1. 這是什麼

一個內網 HTTP 服務，把每月 EIS 匯出的 Excel 包轉成專案狀態快照，讓同仁用 AI client（OpenCode / Claude）以自然語言查詢 BU10 專案的 stage、里程碑、人力、例外事項。

- **server 端不需要任何 LLM、API key 或 AI 帳號**，只是一個 Python 服務。模型在使用者的 client 端。
- 真相來源是 EIS 匯出檔；server 不接受人工填寫的狀態，回傳只有快照既有的欄位。
- 兩級權限：`uploader`（可上傳、可 ingest、可查）與 `viewer`（只能查）。
- PII 零容忍：原檔含姓名工號，只落在 server 端 0700 目錄，不經任何 tool 回傳；ingest 命中 PII 形狀就拒絕寫檔；每個 tool 回傳出口再掃一次。

## 2. 主機需求

| 項目 | 要求 |
|---|---|
| OS | Linux + systemd |
| Python | 3.12 以上（`python3 --version`；太舊就另裝 3.12 並用 `PYTHON=` 指定） |
| 工具 | `rsync`、`curl`（線上安裝另需 `git`；離線安裝見 §3.0） |
| 網路 | 開放一個 TCP port 給內網（預設 8765） |
| 磁碟 | 每月一包約 50–100 MB（原檔 + 快照），一年 2 GB 內 |
| 記憶體 | 服務本身 < 200 MB；ingest 瞬間可能到 500 MB |

不需要 root 執行服務（安裝腳本會建 `eis` 系統帳號），但安裝需要 sudo。

## 3. 安裝（server 端，約 5 分鐘）

```bash
git clone git@github.com:seen0722/dashboard_eis.git
cd dashboard_eis
sudo deploy/install.sh
```

腳本是冪等的，做這些事：

1. 建系統帳號 `eis`（無登入 shell）。
2. 程式碼 rsync 到 `/opt/eis-mcp`（只帶 `src/ config/ scripts/ requirements.txt README.md`，不帶任何資料檔）。
3. 建 venv、裝 `requirements.txt`。
4. 建資料目錄 `/var/lib/eis-mcp`（0700，owner `eis`）。
5. **首次執行**自動產生 `/var/lib/eis-mcp/tokens.yaml`（一把 uploader、一把 viewer，0600）。
6. 寫 `/etc/eis-mcp/env`（監聽位址、port、`--allowed-host <主機名>:8765`）。
7. 安裝 `eis-mcp.service`、`systemctl enable --now`，並打 `/mcp` 確認回 401。

結束時會印出 token 位置、client 設定片段、上傳指令與 log 指令。

若 Python 太舊（Ubuntu 22.04 內建 3.10，實測過的做法）：

```bash
# 主機能連 apt 時（deadsnakes PPA；不動系統的 python3）
sudo add-apt-repository -y ppa:deadsnakes/ppa && sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv
PYTHON=python3.12 sudo -E deploy/install.sh
```

主機連不到 PPA 時（或不想動系統套件），用 **python-build-standalone**：單一 tarball、解壓即用、不需 apt（實測 Ubuntu 20.04/22.04 x86_64 可行）：

```bash
# Mac（能上網）：抓 3.12 的 x86_64 Linux 版（gh 已登入）
TAG=$(gh api repos/astral-sh/python-build-standalone/releases/latest -q .tag_name)
ASSET=$(gh api "repos/astral-sh/python-build-standalone/releases/tags/$TAG" -q '.assets[].name' | grep -E '^cpython-3\.12\.[0-9]+\+.*-x86_64-unknown-linux-gnu-install_only\.tar\.gz$' | head -1)
curl -sSL -o "/tmp/$ASSET" "https://github.com/astral-sh/python-build-standalone/releases/download/$TAG/$ASSET"
scp "/tmp/$ASSET" <user>@<host>:/tmp/

# 主機：解到 /opt/python3.12，之後安裝時指定 PYTHON=
sudo mkdir -p /opt/python3.12 && sudo tar -xzf /tmp/cpython-3.12.*-install_only.tar.gz -C /opt/python3.12 --strip-components=1
/opt/python3.12/bin/python3.12 --version
PYTHON=/opt/python3.12/bin/python3.12 sudo -E deploy/install.sh
```

### 3.0 主機連不到 PyPI / GitHub（公司內網常見）→ 離線安裝

**最簡單的做法：repo 裡已經帶著全部離線檔案**（`deploy/offline/`：40 個 wheel 約 12 MB + Python 3.12 stripped 版約 32 MB）。主機只要能 `git clone`／`git pull` 這個 repo，就不需要再傳任何檔案：

```bash
cd dashboard_eis
sudo mkdir -p /opt/python3.12                       # 主機 python3 < 3.12 時才需要這兩行
sudo tar -xzf deploy/offline/cpython-3.12.*-install_only_stripped.tar.gz -C /opt/python3.12 --strip-components=1
PYTHON=/opt/python3.12/bin/python3.12 sudo -E deploy/install.sh   # 自動偵測 deploy/offline/wheels，--no-index 安裝
```

以下兩種是連 GitHub 也連不到時的替代做法。

在能上網的電腦（你的 Mac）打一個自足的安裝包，裡面有程式碼與全部 wheel（約 12 MB），主機端完全不需要網路：

```bash
# Mac 上（預設打 Python 3.12 / x86_64 的 wheel；主機版本不同就帶參數）
deploy/bundle-offline.sh              # 或 deploy/bundle-offline.sh 3.11 aarch64
scp /tmp/eis-mcp-offline-<rev>.tar.gz <user>@<host>:/tmp/

# 主機上
cd /tmp && tar -xzf eis-mcp-offline-<rev>.tar.gz && cd eis-mcp-offline-<rev>
sudo deploy/install.sh                # 看到同層 wheels/ 就自動 --no-index 安裝
```

先在主機確認 `python3 --version`，wheel 的 Python 版本必須一致（3.12 的包在 3.11 上裝不起來）。之後更新程式也是同樣流程：Mac 重打包、scp、`sudo deploy/install.sh`（資料與 tokens 保留）。

### 3.1 驗證安裝

```bash
systemctl status eis-mcp
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/mcp   # 期待 401
journalctl -u eis-mcp -n 20
sudo -u eis cat /var/lib/eis-mcp/tokens.yaml
```

### 3.2 設定檔

| 檔案 | 內容 | 改完要 |
|---|---|---|
| `/etc/eis-mcp/env` | `EIS_BIND_HOST`（0.0.0.0）、`EIS_PORT`（8765）、`EIS_ALLOWED_HOST_ARG`（client 會打的 Host，例如 `--allowed-host eis-host:8765`，可多個） | `sudo systemctl restart eis-mcp` |
| `/var/lib/eis-mcp/tokens.yaml` | `tokens: [{token, name, role}]`；token 用 `python3 -c 'import secrets;print(secrets.token_urlsafe(32))'` 產生；role 是 `uploader` 或 `viewer` | `sudo systemctl restart eis-mcp` |

tokens.yaml 範例：

```yaml
tokens:
  - token: "REPLACE_WITH_token_urlsafe_OUTPUT"
    name: "Billy"
    role: uploader
  - token: "REPLACE_WITH_token_urlsafe_OUTPUT"
    name: "PM-Karen"
    role: viewer
```

server 啟動時會拒絕：空 token、`REPLACE_ME`、含 `<` `>` 的 token、重複 token、`input/` 非 0700、`tokens.yaml` 非 0600（會印出該下的 chmod 指令）。

### 3.2a 設定 client 會用的位址（`--allowed-host`；OA 電腦 curl 回 421 就是這裡）

`--allowed-host` 檢查的是 **server 自己的位址**（client 在 URL 裡打的 host:port），跟 client 有幾台無關。100 台電腦都用同一個位址連，只需要一個值。同事有人打 IP、有人打主機名，就每種各加一個。

一行寫入（`/etc/eis-mcp/env` 不存在就建、存在就覆蓋），IP 換成 VM 自己的內網 IP，然後重啟：

```bash
printf 'EIS_BIND_HOST=0.0.0.0\nEIS_PORT=8765\nEIS_ALLOWED_HOST_ARG=--allowed-host 172.18.220.125:8765 --allowed-host localhost:8765 --allowed-host 127.0.0.1:8765\n' | sudo tee /etc/eis-mcp/env >/dev/null && sudo chown root:eis /etc/eis-mcp/env && sudo chmod 640 /etc/eis-mcp/env && sudo systemctl restart eis-mcp && sleep 4 && systemctl is-active eis-mcp && sudo cat /etc/eis-mcp/env
```

- 看到 `active` 與三行內容即完成；client 的 `<HOST>` 填同一個 `IP:8765`。
- 有內網 DNS 名稱時（例如 `eis-mcp.pega.local`）改填名稱，之後換 IP 不用改設定。
- 過渡期不想管：把最後一行改成 `EIS_ALLOWED_HOST_ARG=`（空值）就關掉這道檢查，仍有 Bearer token 防護。
- `/etc/eis-mcp` 目錄是 `750 root:eis`，一般帳號會 Permission denied，看或改都要 `sudo`；`sudo vim` 開到空白代表檔案不存在，用上面那行建。

### 3.3 發 token 給同仁（一人一把）

```bash
sudo deploy/eis-token.sh add <名字> viewer      # 只查詢
sudo deploy/eis-token.sh add <名字> uploader    # 負責每月上傳的人
sudo deploy/eis-token.sh list                   # 名字與角色（不顯示 token）
sudo deploy/eis-token.sh rotate <名字>          # 換新，舊的立即失效
sudo deploy/eis-token.sh revoke <名字>          # 離職／撤銷
```

`add` 會產生 token、寫進 `tokens.yaml`、重啟服務，並**只印出一次**（連同 client 設定片段）。管理者用一對一私訊交給本人，不要群組、不要 email 列表。名字要唯一，稽核表（`audit.sqlite`）就是靠它對到人。

### 3.4 TLS（選用）

第一版走 HTTP。要 https 就在前面放 nginx 反向代理到 `127.0.0.1:8765`，並把 `/etc/eis-mcp/env` 的 `EIS_BIND_HOST` 改成 `127.0.0.1`。

## 4. 每月流程（uploader）

1. 從 EIS / PM 拿到當月四類檔案放進一個目錄（檔名不用改）：
   - `Project List-YYYYMM.xlsx`
   - `BU10_Project_Briefing_YYYYMMDD.xlsx`
   - `2026 EIS Resource Summary.xlsx`
   - `2026  EIS Resource Control List-<專案> (<PM>).xlsx` × N（`.xlsb` 也可）
2. 上傳（腳本在 repo 的 `scripts/`，也已複製到主機 `/opt/eis-mcp/scripts/`）：

```bash
EIS_URL=http://eis-host:8765 EIS_TOKEN=<uploader token> scripts/eis-upload.sh 202610 ./input-10
```

3. 在 AI client 裡說「ingest 202610」（呼叫 `ingest_month("202610")`）。回傳：
   - `status: ok` + summary（案數、Control List 份數、latest_month）+ health 摘要。
   - `status: rejected_pii`：原檔含姓名工號形狀的字串，**什麼都不會寫**；回傳只有遮罩片段，原文在主機 `/var/lib/eis-mcp/snapshots/202610/ingest.json`。修好原檔重傳再跑。
   - `missing_input` / `input_unreadable` / `no_manpower_month` / `busy`：訊息裡會說下一步。
4. 同月份可重跑，會覆蓋快照並在 `ingest.json` 留紀錄。

## 5. Client 設定

三種 client 都只需要 URL 與 token。以下 `<host>` 換成主機名或 IP，`<token>` 由管理者從 `tokens.yaml` 發給你。建議把 token 存成檔案而不是寫死在設定裡。

### 5.1 OpenCode

`~/.config/opencode/opencode.json`（或 `.jsonc`）：

```json
{
  "mcp": {
    "eis": {
      "type": "remote",
      "url": "http://<host>:8765/mcp",
      "headers": { "Authorization": "Bearer {file:~/.secrets/eis_mcp_token}" }
    }
  }
}
```

```bash
mkdir -p ~/.secrets && chmod 700 ~/.secrets
printf '%s' '<token>' > ~/.secrets/eis_mcp_token && chmod 600 ~/.secrets/eis_mcp_token
opencode mcp list        # 期待 ✓ eis connected
```

Windows 若 `~` 不展開，改絕對路徑或直接寫 `"Bearer <token>"`。

### 5.2 Claude Code

```bash
claude mcp add --transport http eis http://<host>:8765/mcp --header "Authorization: Bearer <token>"
claude mcp list
```

### 5.3 Claude Desktop

設定檔的 `mcpServers` 加：

```json
{"mcpServers": {"eis": {"url": "http://<host>:8765/mcp",
                         "headers": {"Authorization": "Bearer <token>"}}}}
```

### 5.4 連線前先用 curl 驗證

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://<host>:8765/mcp        # 401 = 通了、只是沒 token
curl -s -H "Authorization: Bearer <token>" http://<host>:8765/mcp -o /dev/null -w '%{http_code}\n'   # 非 401 = token 正確
```

## 6. 可以問什麼

| tool | 例句 |
|---|---|
| `list_months` | 「有哪些月份的資料」 |
| `get_project` | 「THORPE 現在什麼 stage、MP 是哪天」 |
| `search_projects` | 「列出所有 Execution 階段的案子」「AMD 的案子有哪些」 |
| `get_exceptions` / `get_health` | 「這個月要決定的事」「資料健康度」 |
| `get_upcoming_milestones` | 「未來八週有哪些里程碑」「有哪些已經逾期」 |
| `get_dept_loads` / `get_capacity` | 「哪些部門負載超過 100%」「產能曲線」 |
| `diff_project` / `get_corrections` | 「THORPE 9 月和 8 月差在哪」「有哪些歷史數字被改過」 |

resources：`eis://months`、`eis://YYYYMM/report.html`（該月的單頁月報 HTML）。

每個回傳都帶 `meta.report_month`（快照月份 YYYYMM）與 `meta.latest_month`（1–12，最後一個有人力資料的月份）。`get_dept_loads` 的 `util` 是整數百分比，`min_util=85` 代表 85%。`diff_project` 回 `meta_a` / `meta_b`。

## 7. 營運與維護

- **Log**：`journalctl -u eis-mcp -f`。
- **稽核**：`/var/lib/eis-mcp/audit.sqlite`，每次上傳、tool 呼叫、resource 讀取一列（誰、何時、哪個 tool、參數、結果、耗時）。查法：`sudo -u eis sqlite3 /var/lib/eis-mcp/audit.sqlite 'select at,name,action,status from audit order by id desc limit 20;'`
- **敏感資料位置**（備份與權限比照原檔）：`input/`（原檔）、`snapshots/*/ingest.json`（被判定為 PII 的原始片段）、`audit.sqlite`、`tokens.yaml`。整個 `/var/lib/eis-mcp` 是 0700，服務以 `UMask=0077` 執行。
- **加人 / 撤銷**：`sudo deploy/eis-token.sh add|rotate|revoke <名字>`（見 3.3），腳本會自動重啟服務。
- **更新程式**：`cd dashboard_eis && git pull && sudo deploy/install.sh`（資料、tokens、env 都保留）。
- **上傳無大小上限**（內網、uploader 限定）。
- **DNS-rebinding 防護**：`EIS_ALLOWED_HOST_ARG` 建議一律設定，值要等於 client 實際打的 Host。

## 8. 疑難排解

| 症狀 | 原因 / 處理 |
|---|---|
| `systemctl status` 顯示 failed，log 有 `refusing to start; fix permissions` | 照 log 印出的 `chmod` 指令做，再 restart |
| log 有 `PermissionError: ... tokens.yaml` | 檔案擁有者不是 `eis`（手動以 root 編輯過）：`sudo chown eis:eis /var/lib/eis-mcp/tokens.yaml && sudo systemctl restart eis-mcp`；用 `deploy/eis-token.sh` 改就不會發生 |
| `install.sh` 最後印 `WARN: /mcp returned '000'` 但 `systemctl is-active` 是 active | 主機啟動較慢；等 5 秒再 `curl` 一次。腳本已改為最多等 15 秒 |
| log 有 `tokens.yaml entry N: ...` | token 格式錯：空字串、placeholder、含 `<>`、role 不是 uploader/viewer、重複 |
| client 回 401 | token 錯或沒帶 header；用 5.4 的 curl 分辨 |
| client 連不上（curl `000`） | 防火牆沒開 port、`EIS_BIND_HOST` 是 127.0.0.1、不同網段 |
| 帶 token 的 curl 回 `421` | `--allowed-host` 沒包含 client 打的 host:port；照 §3.2a 一行改 |
| `ingest_month` 回 `forbidden` | 用的是 viewer token |
| `missing_input` | 四類檔案沒齊或檔名不合樣式（回應會列出允許的樣式） |
| `rejected_pii` | 原檔（通常是 Control List 的任務描述）含工號或「Name(中文)」形狀；修好重傳 |
| `snapshot_broken` | 快照檔損毀；重跑 `ingest_month` 該月 |
| `unknown_month` | 該月沒 ingest 過；回應會列可用月份 |

## 9. 開發機快速試跑（不裝 systemd）

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
mkdir -p server_data
# 建 server_data/tokens.yaml（見 3.2），chmod 600
.venv/bin/python -m src.eis_mcp --data server_data --host 0.0.0.0 --port 8765
.venv/bin/python -m pytest tests -q      # 173 tests，不需啟動 server
```

設計文件：`docs/superpowers/specs/2026-09-18-eis-mcp-server-design.md`；操作說明：README §7；專案守則與資料語意：`AGENTS.md`。
