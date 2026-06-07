# 灯 Tomoshibi

[![English](https://img.shields.io/badge/lang-English-9AA6C6?style=for-the-badge)](README.md)
[![日本語](https://img.shields.io/badge/lang-日本語-2E8C82?style=for-the-badge)](README.ja.md)

> 一人暮らしの高齢者のための、**100%オンデバイス**の AI 話し相手 ＆ 見守り。
> **Hack the Liquid WAY Tokyo Hackathon 2026 — Track 1（LFM Application）** 作品。
> 対話も視覚も音声もすべて端末内（LFM2 / LFM2-VL / faster-whisper / VOICEVOX）。
> 外部に出るのは「家族への通知」**一点だけ**。AMD Ryzen AI PC へそのまま移植できる構成です。

---

## なぜ「灯」か

日本は超高齢社会。一人暮らしの高齢者を最も苦しめるのが **孤独**、そして **誰にも気づかれない転倒**（数日後に発見される孤独死）です。

家庭にカメラを置く最大の障壁は **プライバシー**。灯はそれを設計で解決します — **すべての推論を端末内で実行**し、外部送信は「家族への通知」だけ（デモではモック）。クラウドLLMでは満たせない要件を、オンデバイスのLFMなら満たせます。

灯は2つの顔を持つ1つのアプリです。

- **話し相手 (Companion)** — LFM2 による温かい日本語**音声対話**。傾聴・回想・体調気づかい・服薬リマインド。高齢者向けに**ゆっくり**話します（ハンズフリーのマイク／テキスト）。
- **見守り (Guardian)** — カメラで転倒を**2段階**検知し、段階的に対応:
  **本人へ声かけ → 反応がなければ家族へ通知 → 緊急時は119通報原稿を読み上げ**（シミュレーション）。

---

## システム構成

```
┌──────────────────────── 話し相手 (Companion) ────────────────────────┐
 🎤 マイク ─VAD自動区切り→ faster-whisper(ASR) ─→ LFM2.5-1.2B-JP(対話, llama.cpp)
        ─→ VOICEVOX(TTS, ゆっくり) ─→ スピーカー ＋ Live2D 口パク(RMS)
└──────────────────────────────────────────────────────────────────────┘

┌──────────────── 見守り (Guardian) — 2段階カスケード ────────────────┐
 📷 カメラ ─連続/安価→ MediaPipe PoseLandmarker ─→ 転倒ヒューリスティック
            （立位→水平＋低位置 の遷移 → 3秒 未回復で候補確定）
   候補成立時だけ 1フレーム→ LFM2-VL-450M(意味確認) ──確定──┐
                                                          ▼
   エスカレーションFSM: S1 声かけ →(15s)→ S2 家族通知 →(5s)→ S3 119読み上げ
└──────────────────────────────────────────────────────────────────────┘
                 UI: FastAPI + バニラHTML/JS（夜テーマ・Live2D）
```

**2段階にする理由**: VLMを毎フレーム回すのはオンデバイスでは重すぎます。軽い MediaPipe で「いつ見るか」を絞り、稀に1枚だけ LFM2-VL で「本当に倒れているか」を意味確認します。これで **低負荷×高精度・低誤検知** を両立し、重いモデルは普段アイドルのままです。

---

## 技術スタック

| 役割 | 実モデル/ライブラリ | 実行場所 | mock(開発) |
|---|---|---|---|
| 対話 LLM | **LFM2.5-1.2B-JP**（GGUF Q4_K_M） | llama.cpp サーバ — Mac=Metal / Ryzen=Vulkan・FastFlowLM NPU（OpenAI互換HTTP） | ルールベース応答 |
| 視覚確認 | **LFM2-VL-450M** | transformers（Mac=MPS / Ryzen=ROCm・CPU）候補時のみ・遅延ロード | 常に「転倒」 |
| 姿勢検知 | **MediaPipe PoseLandmarker**（lite） | CPU・連続 | 純関数でテスト |
| 音声合成 | **VOICEVOX**（cpu-0.25.2, Docker） | ローカルHTTP :50021 | テキストのみ |
| 音声認識 | **faster-whisper**(Mac) / **whisper.cpp**(Ryzen) | CPU/Metal | 空文字 |
| キャラ | **Live2D (Hiyori)** + PIXI/Cubism | ブラウザ(WebGL) | — |
| 観測性 | **W&B Weave**（任意・既定OFF） | クラウド(ログのみ) | no-op |
| UI/API | **FastAPI + バニラHTML/CSS/JS** | ローカル | 同じ |

設計の肝: **全バックエンドに mock 実装**があり、モデル無しでも E2E で起動・テストできます。実モデルへは**環境変数の切替だけ**で移行（Pythonコードは不変）。

話し相手の返答は高齢者・TTS向けに短く保ちます（**1〜2文・60字以内**、`max_new_tokens=72`、`companion/text.py` で整形）。

---

## クイックスタート（mock / モデル不要）

```bash
uv venv --python 3.12            # 実LFM2-VLまで使うなら arm64 ネイティブ推奨（後述）
uv pip install -e .              # 最小依存（fastapi / uvicorn / numpy / pillow 等）
cp config/profile.example.json config/profile.json

# ヘッドレスで全シナリオを確認（GUI不要）
PYTHONPATH=src TOMOSHIBI_MODE=mock python scripts/demo_scenario.py

# UI（Live2D会話 + 見守りダッシュボード）
PYTHONPATH=src TOMOSHIBI_MODE=mock PROFILE_PATH=config/profile.example.json \
  python -m uvicorn tomoshibi.webapp.server:app --port 8000
# → http://127.0.0.1:8000（Live2DはWebGL対応ブラウザで表示）
```

UI: 左=会話（Live2D＋単一吹き出し＋🎤）、右=見守り（カメラ/デモ・状態・タイムライン・119原稿・医療カード）。**「🧪 転倒をシミュレート」**→ S1 →(15s)→ S2 →(5s)→ S3 と自動進行。**🙆大丈夫 / 🆘助けて / 👨‍👩‍👧家族が対応** で分岐します。

> 旧 Gradio 版は `src/tomoshibi/app.py` に残置（非推奨・mockデバッグ用）。現行UIは FastAPI 版です。

---

## 本番に近い構成（実LFM2対話 ＋ 実音声 ＋ 実視覚）

実モデルで動かすには **3プロセス**（VOICEVOX / LFM2サーバ / アプリ）を立てます。

```bash
# 依存とモデル
uv pip install -e ".[asr,vision,models]"
brew install llama.cpp                              # llama-server（Mac=Metal）
huggingface-cli download LiquidAI/LFM2.5-1.2B-JP-202606-GGUF \
  LFM2.5-1.2B-JP-202606-Q4_K_M.gguf --local-dir models
mv models/LFM2.5-1.2B-JP-202606-Q4_K_M.gguf models/LFM2.5-1.2B-JP-Q4_K_M.gguf

# 1) VOICEVOX :50021   2) LFM2対話 :8080   3) アプリ
bash scripts/run_voicevox.sh
bash scripts/run_llm_server.sh
LLAMACPP_SERVER_URL=http://127.0.0.1:8080 TOMOSHIBI_MODE=auto \
  TTS_BACKEND=voicevox ASR_BACKEND=faster_whisper \
  PROFILE_PATH=config/profile.example.json \
  PYTHONPATH=src python -m uvicorn tomoshibi.webapp.server:app --port 8000
```

- 起動ログが `backends: llm:llamacpp / tts:voicevox / asr:faster_whisper / vision:transformers` なら実モデル接続成功。
- **見守りカメラ**: 右パネル「📷 ON」で実カメラ起動（macOS初回はカメラ許可が必要）。
- **テスト動画**: 「🎬 デモ1〜4」。デモ1〜3＝転倒、**デモ4＝通常動作（誤検知しないことの検証）**。動画は `data/demos/`（UR Fall Detection Dataset 由来）。

### Ryzen AI PC への移植（アプリのPythonは不変）

| 要素 | Mac | AMD Ryzen AI PC |
|---|---|---|
| 対話 LFM2 | `run_llm_server.sh`（llama.cpp Metal） | 同 compose；`-ngl` を Vulkan・FastFlowLM NPU に |
| VOICEVOX | `run_voicevox.sh`（Docker compose） | 同左（Windows Docker Desktop） |
| 視覚 LFM2-VL | transformers(MPS) | transformers(ROCm/CPU) |
| ASR | faster-whisper | whisper.cpp（`ASR_BACKEND=whisper_cpp`）も可 |
| アプリ | 変更なし | `LLAMACPP_SERVER_URL` を指すだけ |

`LlamaCppLLM` がOpenAI互換HTTPを叩くため、対話モデルの差し替えは**起動コマンドのみ**。詳細手順 → [`docs/RYZEN_AI_PC_SETUP.md`](docs/RYZEN_AI_PC_SETUP.md)。

---

## プライバシー実証

デモ中に **機内モード**でも、会話・転倒検知・119読み上げが動くことを示せます。外部送信は「家族通知」のみで、`FAMILY_NOTIFY_CHANNEL=mock` ならネットワークにも出ません。医療プロフィール（PII）は**端末内のみ**に保存されます。

## テスト

```bash
uv pip install pytest
PYTHONPATH=src TOMOSHIBI_MODE=mock python -m pytest -q     # 71 tests
```

- 純関数: 転倒ヒューリスティック(`pose.py`) / FSM(`fsm.py`) / 119生成(`dispatch.py`) / 読み上げ整形(`jp_text.py`) / 返答整形(`companion/text.py`) / 人格プロンプト(`persona.py`)。
- 統合: FastAPI の chat・見守り・transcribe を TestClient で（mock E2E）。

## ディレクトリ

```
src/tomoshibi/
├── config.py              設定・閾値（FSM秒数/話速/生成トークン）・OpenMP対策
├── runtime.py             統合層（会話/見守り・状態保持・非同期119生成）
├── webapp/                server.py(FastAPI API+MJPEG) / serialize.py(状態→JSON)
├── companion/             persona.py(人格) / llm.py(LFM2: llamacpp/transformers/mock) / text.py(返答整形)
├── guardian/              camera.py(cv2+MediaPipe) / pose.py(転倒判定) /
│                          vision.py(LFM2-VL) / fsm.py(エスカレーションFSM)
├── voice/                 asr.py / tts.py(VOICEVOX) / jp_text.py(読み上げ整形)
├── emergency/             profile.py / dispatch.py(119原稿) / notify.py(家族通知)
└── obs/trace.py           W&B Weave ラッパ（任意）

web/                       フロント（バニラHTML/CSS/JS + Live2D, 夜テーマ）
scripts/                   run_voicevox.sh / run_llm_server.sh / demo_scenario.py
config/profile.example.json  医療/見守りプロフィール（端末ローカル）
docker-compose.yml         VOICEVOX サービス定義
```

## ライセンス / 注意

ハッカソンのプロトタイプです。実際の救急通報(119)は行いません（原稿の生成＋読み上げシミュレーション）。医療プロフィールは端末ローカルに保存され、外部送信しません。Live2D「Hiyori」は Cubism 公式サンプル（各ライセンスに従う）。デモ動画は UR Fall Detection Dataset 由来。コードは MIT ライセンス（[`LICENSE`](LICENSE)）。
