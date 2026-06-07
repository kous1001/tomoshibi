#!/usr/bin/env bash
# fall_detection デモ動画を編集する。
# 無音の待ち区間を早送り（処理映像は残す）、119読み上げは軽く早送り（ピッチ保持）。
# 元ファイルは変更せず、_edited.mp4 を新規生成する。再実行可能。
set -euo pipefail

cd "$(dirname "$0")/.."

IN="docs/submission/fall_detection.mp4"
OUT="docs/submission/fall_detection_edited.mp4"

# --- 区間境界（秒）。silencedetect 解析に基づく ---
B1=16.46   # 姿勢解析(無音) の終わり / 音声開始
B2=42.22   # S1→S2(音声) の終わり / S3無音ホールド開始
B3=52.49   # S3無音ホールドの終わり / 119読み上げ開始
B4=94.94   # 119読み上げの終わり / 末尾ホールド開始（以降はEOFまで）

ffmpeg -y -i "$IN" -filter_complex "
[0:v]trim=0:${B1},setpts=(PTS-STARTPTS)/4[v0];
[0:a]atrim=0:${B1},asetpts=PTS-STARTPTS,atempo=2,atempo=2[a0];
[0:v]trim=${B1}:${B2},setpts=PTS-STARTPTS[v1];
[0:a]atrim=${B1}:${B2},asetpts=PTS-STARTPTS[a1];
[0:v]trim=${B2}:${B3},setpts=(PTS-STARTPTS)/4[v2];
[0:a]atrim=${B2}:${B3},asetpts=PTS-STARTPTS,atempo=2,atempo=2[a2];
[0:v]trim=${B3}:${B4},setpts=(PTS-STARTPTS)/1.2[v3];
[0:a]atrim=${B3}:${B4},asetpts=PTS-STARTPTS,atempo=1.2[a3];
[0:v]trim=${B4},setpts=(PTS-STARTPTS)/2[v4];
[0:a]atrim=${B4},asetpts=PTS-STARTPTS,atempo=2[a4];
[v0][a0][v1][a1][v2][a2][v3][a3][v4][a4]concat=n=5:v=1:a=1[outv][outa]
" -map "[outv]" -map "[outa]" \
  -c:v libx264 -crf 20 -preset medium -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 160k \
  "$OUT"

echo "done -> $OUT"
