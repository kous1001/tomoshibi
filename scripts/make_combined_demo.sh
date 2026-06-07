#!/usr/bin/env bash
# 提出用デモ動画を1本に結合する。
#   ① 見守り・転倒検知（fall_detection.mp4 を再カット。119読み上げは先頭5秒のみ）
#   ② 話し相手・会話（chat_edited.mp4 を使用）
# 各セクションの前に日英併記の説明カード(2.5s)を挿入。元ファイルは変更しない。
set -euo pipefail
cd "$(dirname "$0")/.."

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FALL="docs/submission/fall_detection.mp4"   # 元動画から再カット
CHAT="docs/submission/chat_edited.mp4"       # 完成済み（会話3ターン）
CARDS="docs/submission/video_cards"
OUT="docs/submission/demo.mp4"

CARD_SEC=2.5   # カード表示秒数

# --- 1) 説明カードを PNG 化（1920x1050） ---
for name in fall chat; do
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
    --window-size=1920,1050 --screenshot="$CARDS/title_${name}.png" \
    "file://$PWD/$CARDS/card_${name}.html" >/dev/null 2>&1
done

# --- 2) 転倒セクションの境界（元動画基準。119は 52.49→57.49 の先頭5秒のみ） ---
B1=16.46   # 姿勢解析(無音,4x) → 音声開始
B2=42.22   # 転倒→S1→S2(1x) → S3無音(4x)
B3=52.49   # S3ホールド終わり → 119読み上げ開始
B4=57.49   # 119の先頭5秒でカット

# --- 3) 1回のエンコードで結合（concat フィルタ） ---
ffmpeg -y \
  -loop 1 -t $CARD_SEC -i "$CARDS/title_fall.png" \
  -i "$FALL" \
  -loop 1 -t $CARD_SEC -i "$CARDS/title_chat.png" \
  -i "$CHAT" \
  -f lavfi -t $CARD_SEC -i anullsrc=channel_layout=stereo:sample_rate=48000 \
  -f lavfi -t $CARD_SEC -i anullsrc=channel_layout=stereo:sample_rate=48000 \
  -filter_complex "
[0:v]scale=1920:1050,fps=30,format=yuv420p,setsar=1[t1v];
[2:v]scale=1920:1050,fps=30,format=yuv420p,setsar=1[t2v];
[1:v]trim=0:${B1},setpts=(PTS-STARTPTS)/4[f0v];
[1:a]atrim=0:${B1},asetpts=PTS-STARTPTS,atempo=2,atempo=2[f0a];
[1:v]trim=${B1}:${B2},setpts=PTS-STARTPTS[f1v];
[1:a]atrim=${B1}:${B2},asetpts=PTS-STARTPTS[f1a];
[1:v]trim=${B2}:${B3},setpts=(PTS-STARTPTS)/4[f2v];
[1:a]atrim=${B2}:${B3},asetpts=PTS-STARTPTS,atempo=2,atempo=2[f2a];
[1:v]trim=${B3}:${B4},setpts=PTS-STARTPTS[f3v];
[1:a]atrim=${B3}:${B4},asetpts=PTS-STARTPTS[f3a];
[f0v][f0a][f1v][f1a][f2v][f2a][f3v][f3a]concat=n=4:v=1:a=1[fv][fa];
[fv]scale=1920:1050,fps=30,format=yuv420p,setsar=1[fv2];
[fa]aresample=48000[fa2];
[3:v]scale=1920:1050,fps=30,format=yuv420p,setsar=1[cv];
[3:a]aresample=48000[ca];
[t1v][4:a][fv2][fa2][t2v][5:a][cv][ca]concat=n=4:v=1:a=1[outv][outa]
" -map "[outv]" -map "[outa]" \
  -c:v libx264 -crf 20 -preset medium -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 160k \
  "$OUT"

echo "done -> $OUT"
