#!/usr/bin/env bash
# 在能上網的機器（你的 Mac）打一個離線安裝包：程式碼 + 全部 wheel。
# 用法：deploy/bundle-offline.sh [py_version] [arch]
#   deploy/bundle-offline.sh                 # 預設 3.12、x86_64
#   deploy/bundle-offline.sh 3.11 aarch64    # 主機是 Python 3.11 / ARM 時
# 產出：/tmp/eis-mcp-offline-<git短碼>.tar.gz，scp 到主機後：
#   tar -xzf eis-mcp-offline-*.tar.gz && cd eis-mcp-offline-* && sudo deploy/install.sh
# install.sh 看到同層的 wheels/ 目錄就自動 --no-index 安裝，不會碰 PyPI。
set -euo pipefail
PYVER=${1:-3.12}
ARCH=${2:-x86_64}
SRC=$(cd "$(dirname "$0")/.." && pwd)
PY=${PYTHON:-$SRC/.venv/bin/python}
[ -x "$PY" ] || PY=python3
REV=$(git -C "$SRC" rev-parse --short HEAD)
NAME="eis-mcp-offline-$REV"
WORK=$(mktemp -d)
OUT="/tmp/$NAME.tar.gz"

echo "== code ($REV) -> $WORK/$NAME"
mkdir -p "$WORK/$NAME"
git -C "$SRC" archive --format=tar HEAD | tar -x -C "$WORK/$NAME"

echo "== wheels for python $PYVER / $ARCH (this needs internet)"
"$PY" -m pip download -q -r "$SRC/requirements.txt" -d "$WORK/$NAME/wheels" \
  --python-version "$PYVER" --only-binary=:all: \
  --platform "manylinux2014_$ARCH" --platform "manylinux_2_17_$ARCH" --platform "manylinux_2_28_$ARCH" --platform any
N=$(ls "$WORK/$NAME/wheels" | wc -l | tr -d ' ')
echo "   $N wheels"

echo "== pack"
tar -czf "$OUT" -C "$WORK" "$NAME"
rm -rf "$WORK"
echo
echo "bundle: $OUT ($(du -h "$OUT" | cut -f1))"
echo "next  : scp $OUT <user>@<host>:/tmp/ ; ssh <host> 'cd /tmp && tar -xzf $NAME.tar.gz && cd $NAME && sudo deploy/install.sh'"
echo "note  : target must have python$PYVER; if not, re-run with that version, e.g. deploy/bundle-offline.sh 3.11"
