# 灯(Tomoshibi) — AMD Ryzen AI PC 移植・起動メモ

結論: **現状のまま移植できます。** アプリ(FastAPI+Python)とフロント(HTML/JS)はOS非依存。
対話LLMは llama.cpp の OpenAI互換HTTP、TTSはDocker、視覚/ASRは環境変数で切替で、
**アプリのPythonコードは1行も変えずに**動きます。変えるのは「各モデルの起動方法」と `.env` だけ。

3プロセス構成（Macと同じ）:
1. VOICEVOX（音声合成, :50021）
2. llama.cpp サーバ（LFM2.5-1.2B-JP 対話, :8080）← Ryzenでは Vulkan か FastFlowLM(NPU)
3. アプリ本体（FastAPI, :8000）＝ MediaPipe＋LFM2-VL(視覚) と faster-whisper(ASR) を内包

---

## 0. 前提

- **OS**: Windows（Ryzen AI / FastFlowLM 想定）または Linux(ROCm)。
- **Python 3.11 or 3.12**（x86_64。Ryzenなら torch≥2.4 のwheelが普通に入る＝Mac特有のarm64問題は無い）。
- **Docker Desktop**（VOICEVOXコンテナ用。使わない場合はネイティブVOICEVOXエンジンでも可）。
- **git, ffmpeg**（ffmpegはASRの音声変換に使用。Windowsは `winget install Gyan.FFmpeg` 等）。
- ネット接続（初回のみ各モデルをDL。オフラインデモは §8 で事前取得）。
- Webカメラ（無い場合は「🎬 デモ動画」で代替可）。

> Windowsでは `*.sh` を Git Bash か WSL で実行するか、本書の「同等コマンド」を直接実行してください。

---

## 1. プロジェクト取得 ＋ Python環境

```bash
# プロジェクトを配置（git or コピー）。data/demos と models は .gitignore のため別途要（§5,§3,§8）。
cd tomoshibi
uv venv --python 3.12            # uv 推奨（無ければ python -m venv .venv）
uv pip install -e ".[asr,vision,models]"
#   asr=faster-whisper / vision=opencv・mediapipe / models=torch・torchvision・transformers
```

- `config/profile.json` を用意（`cp config/profile.example.json config/profile.json`）。
- まず**mockで起動確認**しておくと切り分けが楽:
  `PYTHONPATH=src TOMOSHIBI_MODE=mock python -m uvicorn tomoshibi.webapp.server:app --port 8000`

---

## 2. VOICEVOX（音声合成 :50021）

**A. Docker（推奨・Macと同じ）**
```bash
bash scripts/run_voicevox.sh
#   同等: docker compose up -d voicevox   （docker-compose.yml に定義, image cpu-0.25.2）
```
GPU版を使うなら `docker-compose.yml` の image を `voicevox/voicevox_engine:nvidia-0.25.2` 等へ。

**B. ネイティブエンジン**（Dockerを使わない場合）
VOICEVOX アプリ/エンジンを起動 → `.env` の `VOICEVOX_URL` をそのポートに合わせる。

確認: `curl http://127.0.0.1:50021/version` → `"0.25.2"` 等。

---

## 3. LFM2.5-1.2B-JP 対話サーバ（llama.cpp :8080）

GGUF を取得:
```bash
huggingface-cli download LiquidAI/LFM2.5-1.2B-JP-202606-GGUF \
  LFM2.5-1.2B-JP-202606-Q4_K_M.gguf --local-dir models
# ファイル名を既定に合わせる
mv models/LFM2.5-1.2B-JP-202606-Q4_K_M.gguf models/LFM2.5-1.2B-JP-Q4_K_M.gguf
```

起動（Ryzenは下のいずれか。kit `examples/on_device/` も参照）:

**A. llama.cpp + Vulkan（iGPU, 堅牢な既定）**
```bash
LLM_NGL=99 bash scripts/run_llm_server.sh
#   同等: llama-server -m models/LFM2.5-1.2B-JP-Q4_K_M.gguf --host 127.0.0.1 --port 8080 -ngl 99 --jinja -c 4096
```
Vulkan対応の llama.cpp バイナリを使うこと（AMD iGPUにオフロード）。CPUのみなら `-ngl 0`。

**B. FastFlowLM（XDNA2 NPU, Strix Point/Halo）**
FastFlowLM をOpenAI互換サーバとして起動し、`LLAMACPP_SERVER_URL` をそのエンドポイントに向ける。
（アプリは `LlamaCppLLM` で `/v1/chat/completions` を叩くだけなので、OpenAI互換ならそのまま動く）

確認: `curl http://127.0.0.1:8080/health` → 200。

---

## 4. 視覚(LFM2-VL) と 音声認識(ASR)

これらはアプリ本体に内包され、起動時/初回利用時にロードされます。

- **視覚 LFM2-VL-450M**: `transformers` で実行。初回 `from_pretrained` で ~1-2GB をDL（HFキャッシュ）。
  - Linux+ROCm なら GPU。**Windowsは既定でCPU**（候補時のみの推論なので実用上OK。必要なら DirectML/torch-directml を検討）。
- **ASR**: 既定は **faster-whisper**（`ASR_BACKEND=faster_whisper`, x86_64で問題なく動作, 初回モデルDL）。
  - NPU/Vulkan志向なら **whisper.cpp**（`ASR_BACKEND=whisper_cpp` + `WHISPER_CPP_BIN`/`WHISPER_CPP_MODEL`）。
- **姿勢**: MediaPipe PoseLandmarker。`pose_landmarker_lite.task` を `models/` に自動DL。

---

## 5. デモ用テスト動画

`data/demos/demo1〜4.mp4` が必要（1〜3=転倒, 4=非転倒）。Macからコピーするか、URFDから再取得:
```bash
mkdir -p data/demos && cd data/demos
base=http://fenix.ur.edu.pl/~mkepski/ds/data
curl -sLO $base/fall-01-cam0.mp4 && curl -sLO $base/fall-02-cam0.mp4 && curl -sLO $base/fall-04-cam0.mp4 && curl -sLO $base/adl-05-cam0.mp4
for n in 01 02 04; do ffmpeg -y -i fall-$n-cam0.mp4 -vf "tpad=stop_mode=clone:stop_duration=6" -an /tmp/f$n.mp4; done
cp /tmp/f01.mp4 demo1.mp4; cp /tmp/f02.mp4 demo2.mp4; cp /tmp/f04.mp4 demo3.mp4; cp adl-05-cam0.mp4 demo4.mp4
```
（最も確実なのは Mac の `data/demos/demo1〜4.mp4` をそのままコピーすること）

---

## 6. `.env`（接続先・パラメータ）

プロジェクト直下に `.env` を作成（`.env.example` をコピーして編集）:
```ini
TOMOSHIBI_MODE=auto
PROFILE_PATH=config/profile.json

LLAMACPP_SERVER_URL=http://127.0.0.1:8080
LFM2_GGUF_PATH=models/LFM2.5-1.2B-JP-Q4_K_M.gguf

TTS_BACKEND=voicevox
VOICEVOX_URL=http://127.0.0.1:50021
COMPANION_SPEECH_SPEED=0.85          # 話し相手の話速（ゆっくり）

ASR_BACKEND=faster_whisper           # NPU志向なら whisper_cpp
FASTER_WHISPER_MODEL=base

GUARDIAN_CAMERA_INDEX=0
GUARDIAN_FPS=12
# 本番では家族通知やタイムアウトを調整可:
# FAMILY_ACK_TIMEOUT_S は config 定数（デモ用5s）。本番延長は config.py か今後の環境変数化で。
```

---

## 7. アプリ起動 ＋ 動作確認

```bash
PYTHONPATH=src python -m uvicorn tomoshibi.webapp.server:app --host 0.0.0.0 --port 8000
```
ブラウザで `http://127.0.0.1:8000`。

**起動ログのチェック**: `[灯] backends: {llm: llamacpp, tts: voicevox, asr: faster_whisper, vision: transformers}`
→ すべて実モデル接続成功。`mock` が混ざっていたら該当サービス未起動/未導入。

**動作チェックリスト**:
- [ ] 🎤 で話しかけ → ゆっくりした音声で返答＋Live2D口パク
- [ ] 「📷 ON」で自分の映像＋骨格表示（初回カメラ許可）
- [ ] 「🎬 デモ1」→ 転倒検知→S1声かけ→(15s)→S2→(5s)→S3 119読み上げ
- [ ] 「🎬 デモ4」→ 何も起きない（誤検知なし）
- [ ] 右上の時計が更新

---

## 8. オフラインデモ用の事前ダウンロード（重要）

本番会場のネットが不安定でも動くよう、**事前に1回**オンラインで起動して各モデルをキャッシュしておく:
- VOICEVOX イメージ（docker pull 済みにする）
- GGUF（`models/`）
- LFM2-VL-450M（HFキャッシュ `~/.cache/huggingface`）
- faster-whisper モデル（初回 `transcribe` でDL → 一度マイク/デモを動かす）
- `models/pose_landmarker_lite.task`
- デモ動画 `data/demos/`

→ 以降は **機内モードでも全機能が動作**（外部送信は家族通知のみ。`FAMILY_NOTIFY_CHANNEL=mock`なら皆無）。
これは「100%オンデバイス」の実演にもなる。

---

## 9. Windows 固有の注意

- `*.sh` は Git Bash / WSL で。無ければ各「同等コマンド」を直接実行。
- カメラは cv2 既定バックエンド（`CAP_ANY`→DSHOW/MSMF）を使用（コードはmac以外で自動切替済み）。
- torch の GPU: ROCm は Linux のみ。Windowsは CPU で可（VLは候補時のみ）。GPU化したい場合は ROCm(Linux) か DirectML を検討。
- ポート: 8000(アプリ) / 8080(LLM) / 50021(VOICEVOX)。競合時は変更し `.env`/起動引数を合わせる。

## 10. トラブルシュート

| 症状 | 対処 |
|---|---|
| `backends` に mock | 対応サービス未起動（VOICEVOX/llama-server）か依存未導入（`.[vision,models,asr]`） |
| 起動時 OpenMP の Error #15 | `config.py` が `KMP_DUPLICATE_LIB_OK=TRUE` を設定済み（古い場合は環境変数で設定） |
| カメラが開かない | OSのカメラ許可 / `GUARDIAN_CAMERA_INDEX` を変更 / デモ動画で代替 |
| 転倒が検知されない | カメラに**全身が写る**位置へ（上半身近接では水平姿勢を取れない）。デモ動画で確認 |
| 119原稿が途中で切れる | 解消済み（`DISPATCH_MAX_TOKENS=384`）。さらに長い構成なら値を上げる |
| 初回検知が遅い | LFM2-VL の初回ロード（カメラON時にwarm-up）。事前に一度起動しておく |

---

## まとめ
アプリは**移植済みと同義**（OS非依存）。AI PC側の作業は実質「①VOICEVOX起動 ②llama.cppでGGUF起動(Vulkan/NPU) ③`.env`設定 ④uvicorn起動」の4点。
GPU/NPUの最適化（Vulkan・FastFlowLM・ROCm/DirectML）は kit `examples/on_device/` を参照して詰める。
