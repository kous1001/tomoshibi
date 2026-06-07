#!/usr/bin/env bash
# タグライン1枚スライド(HTML)を PDF 化する（Google Chrome ヘッドレス）。
set -euo pipefail
cd "$(dirname "$0")/.."

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HTML="$PWD/docs/submission/tagline/tagline.html"
PDF="$PWD/docs/submission/tagline/tagline.pdf"

"$CHROME" --headless=new --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="$PDF" "file://$HTML"

echo "done -> $PDF"
