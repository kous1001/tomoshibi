#!/usr/bin/env bash
# 灯 専用の VOICEVOX エンジンを起動する（このプロジェクトが所有）。
# 他プロジェクト(sobani)のコンテナには依存しない。
#
#   bash scripts/run_voicevox.sh          # 起動
#   bash scripts/run_voicevox.sh stop     # 停止
#
# AI PC(Windows Docker Desktop)でも同じ compose で動く。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT="${VOICEVOX_PORT:-50021}"

if [ "${1:-up}" = "stop" ]; then
  docker compose down
  exit 0
fi

# 他プロジェクトのコンテナ(名前: voicevox)が同じポートを掴んでいたら警告
if docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -vq "tomoshibi-voicevox" \
   && docker ps --format '{{.Ports}}' 2>/dev/null | grep -q ":${PORT}->"; then
  if ! docker ps --format '{{.Names}}' | grep -q "tomoshibi-voicevox"; then
    echo "[warn] ポート ${PORT} を別コンテナが使用中の可能性があります。" >&2
    echo "       競合する場合は \`docker stop voicevox\` で停止するか、VOICEVOX_PORT=50121 を指定してください。" >&2
  fi
fi

echo "[voicevox] starting tomoshibi-voicevox on :${PORT} ..."
VOICEVOX_PORT="$PORT" docker compose up -d voicevox

# 起動待ち
for i in $(seq 1 40); do
  if curl -fs "http://127.0.0.1:${PORT}/version" >/dev/null 2>&1; then
    echo "[voicevox] ready: $(curl -s http://127.0.0.1:${PORT}/version) on :${PORT}"
    exit 0
  fi
  sleep 1
done
echo "[voicevox] 起動確認に失敗しました。'docker compose logs voicevox' を確認してください。" >&2
exit 1
