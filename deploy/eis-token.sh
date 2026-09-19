#!/usr/bin/env bash
# 管理 EIS MCP server 的 token（一人一把）。在主機上以 sudo 執行。
#   sudo deploy/eis-token.sh add <name> <uploader|viewer>   產生並印出一次（之後不再顯示）
#   sudo deploy/eis-token.sh list                           列出名字與角色（不顯示 token）
#   sudo deploy/eis-token.sh revoke <name>                  刪除該人
#   sudo deploy/eis-token.sh rotate <name>                  換一把新的，舊的立即失效
# 環境變數：EIS_DATA（預設 /var/lib/eis-mcp）、EIS_PY（預設 /opt/eis-mcp/.venv/bin/python）、EIS_SERVICE（預設 eis-mcp）
set -euo pipefail
DATA=${EIS_DATA:-/var/lib/eis-mcp}
PY=${EIS_PY:-/opt/eis-mcp/.venv/bin/python}
SVC=${EIS_SERVICE:-eis-mcp}
FILE="$DATA/tokens.yaml"
cmd=${1:-}; name=${2:-}; role=${3:-}

[ -f "$FILE" ] || { echo "no $FILE (run deploy/install.sh first)" >&2; exit 1; }
[ -x "$PY" ] || { echo "no python at $PY (set EIS_PY)" >&2; exit 1; }

edit() {   # $1=op $2=name $3=role → python 改檔，stdout 回新 token（add/rotate）
  "$PY" - "$FILE" "$1" "$2" "${3:-}" <<'EOF'
import secrets, sys, yaml
path, op, name, role = sys.argv[1:5]
doc = yaml.safe_load(open(path, encoding="utf-8")) or {}
rows = doc.get("tokens") or []
byname = {r.get("name"): r for r in rows}
if op == "list":
    for r in rows: print(f"{r.get('name'):<24} {r.get('role')}")
    sys.exit(0)
if op == "add":
    if role not in ("uploader", "viewer"): sys.exit("role must be uploader or viewer")
    if name in byname: sys.exit(f"{name} already has a token; use rotate or revoke")
    tok = secrets.token_urlsafe(32); rows.append({"token": tok, "name": name, "role": role}); print(tok)
elif op == "rotate":
    if name not in byname: sys.exit(f"no token for {name}")
    tok = secrets.token_urlsafe(32); byname[name]["token"] = tok; print(tok)
elif op == "revoke":
    if name not in byname: sys.exit(f"no token for {name}")
    rows = [r for r in rows if r.get("name") != name]
else:
    sys.exit(f"unknown op {op}")
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    yaml.safe_dump({"tokens": rows}, f, allow_unicode=True, sort_keys=False)
import os, shutil
os.chmod(tmp, 0o600)
st = os.stat(path); shutil.chown(tmp, st.st_uid, st.st_gid)   # 以 root 執行時，擁有者要維持服務帳號，否則服務讀不到
os.replace(tmp, path)
EOF
}

restart() {
  if command -v systemctl >/dev/null && systemctl is-active --quiet "$SVC"; then
    systemctl restart "$SVC" && echo "restarted $SVC" >&2
  else
    echo "note: service $SVC not running under systemd; restart the server by hand for the change to apply" >&2
  fi
}

case "$cmd" in
  list)   edit list "" "" ;;
  add)    [ -n "$name" ] && [ -n "$role" ] || { echo "usage: add <name> <uploader|viewer>" >&2; exit 2; }
          tok=$(edit add "$name" "$role"); restart
          printf '\n%s (%s) token — shown once, deliver privately:\n\n  %s\n\nclient snippet:\n  {"mcpServers":{"eis":{"url":"http://<host>:8765/mcp","headers":{"Authorization":"Bearer %s"}}}}\n' "$name" "$role" "$tok" "$tok" ;;
  rotate) [ -n "$name" ] || { echo "usage: rotate <name>" >&2; exit 2; }
          tok=$(edit rotate "$name" ""); restart; printf '\n%s new token — shown once:\n\n  %s\n' "$name" "$tok" ;;
  revoke) [ -n "$name" ] || { echo "usage: revoke <name>" >&2; exit 2; }
          edit revoke "$name" ""; restart; echo "revoked $name" ;;
  *)      sed -n '2,7p' "$0"; exit 2 ;;
esac
