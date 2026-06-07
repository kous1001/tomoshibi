#!/usr/bin/env bash
# chat デモ動画を編集する。
# 会話の最初の3ターン（灯の挨拶＋返答2回）だけに絞り、無音の待ち(聞き取り/考え中)を早送り。
# 元ファイルは変更せず、_edited.mp4 を新規生成する。再実行可能。
set -euo pipefail

cd "$(dirname "$0")/.."

IN="docs/submission/chat.mp4"
OUT="docs/submission/chat_edited.mp4"

# --- 区間境界（秒）。silencedetect 解析に基づく ---
G0=2.66    # 挨拶(発話)開始
G1=9.91    # 挨拶終わり / 聞き取り待ち開始
T1A=34.31  # 返答1(発話)開始
T1B=39.97  # 返答1終わり / 待ち開始
T2A=54.71  # 返答2(発話)開始
END=63.30  # 返答2＋ホールドの終わり（ここでカット。4ターン目は捨てる）

ffmpeg -y -i "$IN" -filter_complex "
[0:v]trim=0:${G0},setpts=(PTS-STARTPTS)/4[v0];
[0:a]atrim=0:${G0},asetpts=PTS-STARTPTS,atempo=2,atempo=2[a0];
[0:v]trim=${G0}:${G1},setpts=PTS-STARTPTS[v1];
[0:a]atrim=${G0}:${G1},asetpts=PTS-STARTPTS[a1];
[0:v]trim=${G1}:${T1A},setpts=(PTS-STARTPTS)/6[v2];
[0:a]atrim=${G1}:${T1A},asetpts=PTS-STARTPTS,atempo=1.5,atempo=2,atempo=2[a2];
[0:v]trim=${T1A}:${T1B},setpts=PTS-STARTPTS[v3];
[0:a]atrim=${T1A}:${T1B},asetpts=PTS-STARTPTS[a3];
[0:v]trim=${T1B}:${T2A},setpts=(PTS-STARTPTS)/6[v4];
[0:a]atrim=${T1B}:${T2A},asetpts=PTS-STARTPTS,atempo=1.5,atempo=2,atempo=2[a4];
[0:v]trim=${T2A}:${END},setpts=PTS-STARTPTS[v5];
[0:a]atrim=${T2A}:${END},asetpts=PTS-STARTPTS[a5];
[v0][a0][v1][a1][v2][a2][v3][a3][v4][a4][v5][a5]concat=n=6:v=1:a=1[outv][outa]
" -map "[outv]" -map "[outa]" \
  -c:v libx264 -crf 20 -preset medium -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 160k \
  "$OUT"

echo "done -> $OUT"
