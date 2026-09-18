#!/usr/bin/env bash
# 把一個月份的 EIS Excel 包上傳到 EIS MCP server。
# 用法: EIS_URL=http://eis-host:8765 EIS_TOKEN=<token> scripts/eis-upload.sh 202610 ./input-10
set -euo pipefail
month="${1:?usage: eis-upload.sh <YYYYMM> <dir>}"
dir="${2:?usage: eis-upload.sh <YYYYMM> <dir>}"
: "${EIS_URL:?set EIS_URL, e.g. http://eis-host:8765}"
: "${EIS_TOKEN:?set EIS_TOKEN to your uploader token}"
[[ "$month" =~ ^[0-9]{6}$ ]] || { echo "month must be YYYYMM, got '$month'" >&2; exit 2; }
args=()
while IFS= read -r -d '' f; do args+=(-F "file=@$f"); done \
  < <(find "$dir" -maxdepth 1 -type f \( -name '*.xlsx' -o -name '*.xlsb' \) ! -name '~$*' -print0)
[ ${#args[@]} -gt 0 ] || { echo "no .xlsx/.xlsb files in $dir" >&2; exit 2; }
echo "uploading $(( ${#args[@]} / 2 )) file(s) to $EIS_URL/upload/$month" >&2
curl -sS --fail-with-body -H "Authorization: Bearer $EIS_TOKEN" "${args[@]}" "$EIS_URL/upload/$month"
echo
echo "done. Now call ingest_month(\"$month\") from your MCP client." >&2
