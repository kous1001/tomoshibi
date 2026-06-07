#!/usr/bin/env bash
# 実LFM2対話サーバ（llama.cpp / OpenAI互換）を起動する。
# Mac(Metal)でも Ryzen(Vulkan/NPU)でも、起動コマンドだけ変えれば同じ構成で動く。
#
#   bash scripts/run_llm_server.sh
#
# 既定モデル: 日本語チューニング版 LFM2.5-1.2B-JP (Q4_K_M, GGUF)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="${LFM2_GGUF_PATH:-$ROOT/models/LFM2.5-1.2B-JP-Q4_K_M.gguf}"
PORT="${LLM_PORT:-8080}"
NGL="${LLM_NGL:-99}"   # GPUへオフロードする層数（Metal/Vulkan）。CPUのみなら0でも可

if [ ! -f "$MODEL" ]; then
  echo "GGUFが見つかりません: $MODEL" >&2
  echo "先にダウンロードしてください（README参照）。" >&2
  exit 1
fi

echo "[llm] starting llama-server: $MODEL :$PORT (ngl=$NGL)"
# --jinja: GGUF埋め込みのLFM2チャットテンプレートを /v1/chat/completions に適用
exec llama-server -m "$MODEL" --host 127.0.0.1 --port "$PORT" -ngl "$NGL" --jinja -c 4096
