#!/usr/bin/env bash
# Technical Summary スライド(2枚 HTML)を PDF 化する（Google Chrome ヘッドレス）。
set -euo pipefail
cd "$(dirname "$0")/.."

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HTML="$PWD/docs/submission/tech_summary/tech_summary.html"
PDF="$PWD/docs/submission/tech_summary/tech_summary.pdf"

"$CHROME" --headless=new --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="$PDF" "file://$HTML"

echo "done -> $PDF"
