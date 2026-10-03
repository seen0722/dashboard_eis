#!/usr/bin/env bash
# 在內網主機（Ubuntu/Debian/RHEL 皆可，需 systemd 與 python3.12+）安裝 EIS MCP server。
# 用法（在 repo 根目錄，以 sudo 執行）：
#   sudo deploy/install.sh
# 可重複執行（冪等）：只會更新程式碼與依賴、保留資料與 tokens。
set -euo pipefail

APP_DIR=/opt/eis-mcp
DATA_DIR=/var/lib/eis-mcp
ENV_DIR=/etc/eis-mcp
SVC_USER=eis
PY=${PYTHON:-python3}

[ "$(id -u)" -eq 0 ] || { echo "run as root: sudo deploy/install.sh" >&2; exit 1; }
SRC=$(cd "$(dirname "$0")/.." && pwd)
[ -f "$SRC/requirements.txt" ] && [ -d "$SRC/src/eis_mcp" ] || { echo "run from the dashboard_eis repo (missing src/eis_mcp)" >&2; exit 1; }
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' || { echo "need python >= 3.12 (set PYTHON=/path/to/python3.12)" >&2; exit 1; }
for tool in rsync curl systemctl; do command -v "$tool" >/dev/null || { echo "missing $tool (apt/dnf install it first)" >&2; exit 1; }; done

echo "== service user"
id "$SVC_USER" >/dev/null 2>&1 || useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$SVC_USER"

echo "== code -> $APP_DIR (only what the server needs; no data/, input-*/, out/)"
mkdir -p "$APP_DIR"
rsync -a --delete \
  --include='src/' --include='src/**' \
  --include='config/' --include='config/**' \
  --include='scripts/' --include='scripts/**' \
  --include='vendor/' --include='vendor/**' \
  --include='requirements.txt' --include='README.md' \
  --include='docs/' --include='docs/eis-mcp-client-setup.md' \
  --exclude='*' \
  "$SRC/" "$APP_DIR/"
find "$APP_DIR" -name '__pycache__' -type d -prune -exec rm -rf {} +
chown -R root:root "$APP_DIR"; chmod -R a+rX "$APP_DIR"

echo "== venv"
[ -x "$APP_DIR/.venv/bin/python" ] || "$PY" -m venv "$APP_DIR/.venv"
WHEELS=""
[ -d "$SRC/wheels" ] && WHEELS="$SRC/wheels"                                    # deploy/bundle-offline.sh 產出的包
[ -z "$WHEELS" ] && [ -d "$SRC/deploy/offline/wheels" ] && WHEELS="$SRC/deploy/offline/wheels"   # 直接進版控的 wheel
if [ -n "$WHEELS" ]; then
  # 離線：只用本機 wheel，不碰 PyPI，也不升級 pip
  echo "   offline: installing from $WHEELS ($(ls "$WHEELS" | wc -l | tr -d ' ') wheels)"
  "$APP_DIR/.venv/bin/python" -m pip install -q --no-index --find-links "$WHEELS" -r "$APP_DIR/requirements.txt"
else
  "$APP_DIR/.venv/bin/python" -m pip install -q --upgrade pip
  "$APP_DIR/.venv/bin/python" -m pip install -q -r "$APP_DIR/requirements.txt"
fi
( cd "$APP_DIR" && .venv/bin/python -c 'from mcp.server.mcpserver import MCPServer; import src.eis_mcp' )

echo "== data dir $DATA_DIR (owner-only)"
install -d -m 700 -o "$SVC_USER" -g "$SVC_USER" "$DATA_DIR"
if [ ! -f "$DATA_DIR/tokens.yaml" ]; then
  UP=$("$APP_DIR/.venv/bin/python" -c 'import secrets;print(secrets.token_urlsafe(32))')
  VW=$("$APP_DIR/.venv/bin/python" -c 'import secrets;print(secrets.token_urlsafe(32))')
  cat > "$DATA_DIR/tokens.yaml" <<EOF
tokens:
  - token: "$UP"
    name: "uploader-1"
    role: uploader
  - token: "$VW"
    name: "viewer-1"
    role: viewer
EOF
  chown "$SVC_USER:$SVC_USER" "$DATA_DIR/tokens.yaml"; chmod 600 "$DATA_DIR/tokens.yaml"
  echo "   generated $DATA_DIR/tokens.yaml (uploader-1 / viewer-1) — edit names, add people, then: systemctl restart eis-mcp"
else
  echo "   keeping existing $DATA_DIR/tokens.yaml"
fi

echo "== env $ENV_DIR/env"
install -d -m 750 -o root -g "$SVC_USER" "$ENV_DIR"
if [ ! -f "$ENV_DIR/env" ]; then
  install -m 640 -o root -g "$SVC_USER" "$SRC/deploy/env.example" "$ENV_DIR/env"
  sed -i "s/eis-host:8765/$(hostname -s):8765/" "$ENV_DIR/env"
  echo "   wrote $ENV_DIR/env with --allowed-host $(hostname -s):8765 — check it matches what clients will type"
else
  echo "   keeping existing $ENV_DIR/env"
fi

echo "== systemd unit"
install -m 644 "$SRC/deploy/eis-mcp.service" /etc/systemd/system/eis-mcp.service
systemctl daemon-reload
systemctl enable --now eis-mcp
systemctl restart eis-mcp      # 重跑安裝時程式碼可能已更新，一律重啟載入新版
PORT=$(sed -n 's/^EIS_PORT=//p' "$ENV_DIR/env")
CODE=000
for i in $(seq 1 15); do        # 小型主機啟動要 3–5 秒，最多等 15 秒
  sleep 1
  CODE=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT:-8765}/mcp" || true)
  [ "$CODE" = "401" ] && break
done
systemctl --no-pager --lines=3 status eis-mcp || true
if [ "$CODE" = "401" ]; then
  echo "== OK: /mcp answers 401 without a token (auth is on)"
else
  echo "== WARN: /mcp returned '$CODE'; see: journalctl -u eis-mcp -n 50" >&2
fi
cat <<EOF

Next:
  tokens : sudo -u $SVC_USER cat $DATA_DIR/tokens.yaml
  client : {"mcpServers":{"eis":{"url":"http://$(hostname -s):${PORT:-8765}/mcp","headers":{"Authorization":"Bearer <token>"}}}}
  upload : EIS_URL=http://$(hostname -s):${PORT:-8765} EIS_TOKEN=<uploader token> $APP_DIR/scripts/eis-upload.sh 202610 ./input-10
  logs   : journalctl -u eis-mcp -f
  update : git pull && sudo deploy/install.sh   (data and tokens are kept)
EOF
