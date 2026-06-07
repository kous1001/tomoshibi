# 灯 — Tomoshibi

> 一人暮らしの高齢者のための、**100%オンデバイス**の AI 話し相手 ＆ 見守り。
> Hack the Liquid WAY Tokyo Hackathon 2026 — **Track 1: LFM Application Track**。
> 対話も視覚も音声もすべて端末内（LFM2 / LFM2-VL / VOICEVOX / faster-whisper）。
> 外部に出るのは「家族への通知」一点だけ。AMD Ryzen AI PC へそのまま移植できる構成。

## なぜ「灯」か

日本は超高齢社会。一人暮らしの高齢者の **孤独** と、誰にも気づかれない **転倒・孤独死** が深刻な課題です。
家庭にカメラを置く最大の障壁は **プライバシー**。灯はそれを設計で解決します
— すべての推論を端末内で行い、外部送信は「家族への通知」だけ（デモではモック）。

灯は2つの顔を持つ1つのアプリです。

1. **話し相手 (Companion)** — LFM2 による温かい日本語**音声対話**。傾聴・回想・体調気づかい・服薬リマインド。
   高齢者向けに**ゆっくり**話します（マイクのハンズフリー会話／テキスト会話）。
2. **見守り (Guardian)** — カメラで転倒を**2段階**検知し、段階的に対応:
   **本人へ声かけ → 反応なしなら家族へ通知 → 緊急時は医療プロフィールを救急向けに整形して読み上げ（119シミュレーション）**。

---

## システム構成

```
┌──────────────────────── 話し相手 (Companion) ────────────────────────┐
 🎤マイク ─VAD自動区切り→ faster-whisper(ASR) ─→ LFM2.5-1.2B-JP(対話, llama.cpp)
        ─→ VOICEVOX(TTS, ゆっくり) ─→ スピーカー ＋ Live2D 口パク(RMS)
└──────────────────────────────────────────────────────────────────┘

┌──────────────── 見守り (Guardian) 2段階カスケード ────────────────┐
 📷カメラ ─連続/安価→ MediaPipe PoseLandmarker ─→ 転倒ヒューリスティック
        （立位→水平+低位置 の遷移 → 3秒 未回復で候補確定）
   候補成立時だけ 1フレーム→ LFM2-VL-450M(確認/意味理解) ──確定──┐
                                                              ▼
   エスカレーションFSM: S1 声かけ →(15s)→ S2 家族通知 →(5s)→ S3 119読み上げ
└──────────────────────────────────────────────────────────────────┘
                    UI: FastAPI + バニラHTML/JS（夜テーマ・Live2D）
```

**2段階にする理由**: VLMを毎フレーム回すのは重すぎる（オンデバイスで非現実的）。
軽い MediaPipe で「いつ見るか」を絞り、稀に1枚だけ LFM2-VL で「本当に倒れているか」を意味確認する
（誤検知を弾く）。これで**低負荷×高精度**を両立。

---

## 技術スタック

| 役割 | 実モデル/ライブラリ | 実行場所 | mock(開発用) |
|---|---|---|---|
| 対話 LLM | **LFM2.5-1.2B-JP**（GGUF Q4_K_M） | llama.cpp サーバ（Mac=Metal / Ryzen=Vulkan・FastFlowLM NPU）OpenAI互換HTTP | ルールベース応答 |
| 視覚確認 | **LFM2-VL-450M** | transformers（Mac=MPS / Ryzen=ROCm・CPU）※候補時のみ・遅延ロード | 常に「転倒」 |
| 姿勢検知 | **MediaPipe PoseLandmarker**（Tasks API, lite） | CPU・連続 | （純関数でテスト） |
| 音声合成 | **VOICEVOX**（cpu-0.25.2, 本リポジトリ所有のdocker） | ローカルHTTP :50021 | テキストのみ |
| 音声認識 | **faster-whisper**(Mac) / **whisper.cpp**(Ryzen) | CPU/Metal | 空文字 |
| キャラ | **Live2D (Hiyori)** + PIXI/Cubism | ブラウザ(WebGL) | — |
| 観測性 | **W&B Weave**（任意・既定OFF） | クラウド(ログのみ) | no-op |
| UI | **FastAPI + バニラHTML/CSS/JS** | ローカル | 同じ |

設計の肝: **全バックエンドに mock 実装**があり、モデル無しでも E2E で起動・テストできる。
実モデルへは**環境変数の切替だけ**で移行（Pythonコードは不変）。

---

## 処理フロー（実装の詳細）

### 話し相手
- 🎤ボタンで**ハンズフリー会話**（`web/conversation.js`）: VAD（音量）で発話の区切りを自動判定 →
  録音→`/api/transcribe`（faster-whisper）→`/api/chat`（LFM2.5-JP）→ VOICEVOX音声＋Live2D口パク。
  灯の発話中はマイクを止めエコー混入を防止。テキスト会話も併用可。
- **話速**: 話し相手は `COMPANION_SPEECH_SPEED`（既定 **0.85=ゆっくり**）。見守りの発話は 1.0。
- 返答は高齢者・TTS向けに**2〜3文**へ短縮（`LFM2_GEN.max_new_tokens=120`）。
- 読み上げ整形は `voice/jp_text.py`（ふりがな注釈「灯（あかり）」→「あかり」、伸ばし記号統一、文末句点）。

### 見守り
- `guardian/camera.py` の `CameraMonitor`（サーバ側スレッド）: cv2でフレーム取得 → MediaPipe PoseLandmarker →
  `landmarks_to_sample`（体幹角度・重心）→ `pose.py` のヒューリスティック。映像は骨格＋状態を描いて **MJPEG** 配信。
- **転倒ヒューリスティック**（`guardian/pose.py`）: 「立位→水平＋低位置」の**遷移**を検知 →
  **`FALL_STILLNESS_S`(3秒)以内に起き上がり(立位かつ重心が高い状態が0.4s継続)が無ければ確定**。
  床で MediaPipe が人物を見失っても「起き上がっていない＝確定」となり頑健。
- **LFM2-VL 確認**（`guardian/vision.py`）: 候補フレームを英語プロンプト
  `"Is there a person lying on the floor or ground? Answer yes or no."` で判定（未FTでも安定）。
  初回のみ遅延ロード＋カメラON時にウォームアップ、**VL専用スレッド**で対話をブロックしない。
- **エスカレーションFSM**（`guardian/fsm.py`）:
  - `S1 声かけ` → 15秒(`CHECKIN_TIMEOUT_S`)無応答 → `S2 家族通知` → 5秒(`FAMILY_ACK_TIMEOUT_S`)無応答 → `S3 119`。
  - 「🆘助けて」は**最緊急**として S2 を飛ばし**直接 S3** へ。「🙆大丈夫」で解決。
  - S3 の **119原稿は実LFM2が非同期生成**（`DISPATCH_MAX_TOKENS=384`）し、画面は即S3へ遷移→生成完了後に反映・読み上げ。
    事実の箇条書き（氏名/住所/持病/服薬/アレルギー/緊急連絡先）は決定論生成で即時表示。**PIIは端末内のみ**。

---

## クイックスタート（mock / モデル不要）

```bash
uv venv --python 3.12            # 実LFM2-VLまで使うなら arm64 ネイティブ推奨（後述）
uv pip install -e .              # 最小依存（fastapi/uvicorn/numpy/pillow 等）
cp config/profile.example.json config/profile.json

# ヘッドレスで全シナリオを確認（GUI不要）
PYTHONPATH=src TOMOSHIBI_MODE=mock python scripts/demo_scenario.py

# UI（Live2D会話 + 見守りダッシュボード）を起動
PYTHONPATH=src TOMOSHIBI_MODE=mock PROFILE_PATH=config/profile.example.json \
  python -m uvicorn tomoshibi.webapp.server:app --port 8000
# → http://127.0.0.1:8000（Live2DはWebGL対応ブラウザで表示）
```

UI: 左=会話（Live2D＋単一吹き出し＋🎤）、右=見守り（カメラ/デモ・状態・タイムライン・119原稿・医療カード）。
「🧪 転倒をシミュレート」→ S1→(15s)→S2→(5s)→S3 と自動進行。「🙆大丈夫 / 🆘助けて / 👨‍👩‍👧家族が対応」で分岐。

> 旧 Gradio 版は `src/tomoshibi/app.py` に残置（非推奨・mockデバッグ用）。現行UIは FastAPI 版です。

## 本番に近い構成（実LFM2対話 ＋ 実音声 ＋ 実視覚）

実モデルで動かすには **3プロセス**（VOICEVOX / LFM2サーバ / アプリ）を立てます。

```bash
# 依存とモデル
uv pip install -e ".[asr,vision,models]"           # faster-whisper / opencv・mediapipe / torch・transformers
brew install llama.cpp                              # llama-server（Mac=Metal）
huggingface-cli download LiquidAI/LFM2.5-1.2B-JP-202606-GGUF \
  LFM2.5-1.2B-JP-202606-Q4_K_M.gguf --local-dir models
mv models/LFM2.5-1.2B-JP-202606-Q4_K_M.gguf models/LFM2.5-1.2B-JP-Q4_K_M.gguf

# 1) VOICEVOX（本リポジトリ所有 :50021）  2) LFM2対話 :8080  3) アプリ
bash scripts/run_voicevox.sh
bash scripts/run_llm_server.sh
LLAMACPP_SERVER_URL=http://127.0.0.1:8080 TOMOSHIBI_MODE=auto \
  TTS_BACKEND=voicevox ASR_BACKEND=faster_whisper \
  PROFILE_PATH=config/profile.example.json \
  PYTHONPATH=src python -m uvicorn tomoshibi.webapp.server:app --port 8000
```

- 起動ログ `backends:` が `llm:llamacpp / tts:voicevox / asr:faster_whisper / vision:transformers` なら実モデル接続成功。
- **見守りカメラ**: 右パネル「📷 ON」で実カメラ起動（macOS初回はターミナルに**カメラ許可**が必要）。
- **テスト動画**: 「🎬 デモ1〜4」ボタン。デモ1〜3＝転倒、**デモ4＝通常動作（非転倒・誤検知しないことの検証）**。
  動画は `data/demos/`（UR Fall Detection由来）。`.env` で速度等を調整可（`COMPANION_SPEECH_SPEED` 等）。

### Ryzen AI PC への移植（アプリのPythonは不変）

| 要素 | Mac | Ryzen AI PC |
|---|---|---|
| 対話 LFM2 | `run_llm_server.sh`（llama.cpp Metal） | 同 compose / `-ngl` を Vulkan・FastFlowLM NPU に |
| VOICEVOX | `run_voicevox.sh`（docker compose） | 同左（Windows Docker Desktop, 同 compose） |
| 視覚 LFM2-VL | transformers(MPS) | transformers(ROCm/CPU) |
| ASR | faster-whisper | whisper.cpp（`ASR_BACKEND=whisper_cpp`）も可 |
| アプリ | 変更なし | `LLAMACPP_SERVER_URL` を指すだけ |

`LlamaCppLLM` がOpenAI互換HTTPを叩くため、対話モデルの差し替えは**起動コマンドのみ**。
**移植・起動の詳細手順 → [`docs/RYZEN_AI_PC_SETUP.md`](docs/RYZEN_AI_PC_SETUP.md)**。

---

## 環境メモ（重要）

- **実 LFM2-VL を Mac で動かすには arm64 ネイティブ Python が必要**（torch≥2.4 が Intel-Mac wheel 非対応のため）。
  本プロジェクトの `.venv` は uv の **CPython 3.12 (arm64) + torch 2.12（MPS）**。x86_64環境では視覚は自動的に mock へフォールバック。
- `config.py` で `KMP_DUPLICATE_LIB_OK=TRUE` を設定（torch と ctranslate2/cv2 の OpenMP 二重リンク回避）。
- アプリ既定ポートは **8000**。本開発機では 8000 が別プロジェクト使用中のため **8030** で起動している。
- `.env`（gitignore対象）で接続先・話速・カメラ番号などを上書き可（`.env.example` 参照）。

## プライバシー実証

デモ中に **機内モード**でも、会話・転倒検知・119読み上げが動くことを示せます
（外部送信は「家族通知」のみ。`FAMILY_NOTIFY_CHANNEL=mock` ならネットワークにも出ません）。

## テスト

```bash
uv pip install pytest
PYTHONPATH=src TOMOSHIBI_MODE=mock python -m pytest tests/ -q   # 51 tests
```

- 純関数: 転倒ヒューリスティック(`pose.py`) / FSM(`fsm.py`) / 119生成(`dispatch.py`) /
  読み上げ整形(`jp_text.py`) / 姿勢変換(`camera.landmarks_to_sample`)。
- 統合: FastAPI(`webapp`) の chat・見守り・transcribe を TestClient で（mock E2E）。

## ディレクトリ

```
src/tomoshibi/
├── config.py              設定・閾値（FSM秒数/話速/生成トークン）・OpenMP対策
├── runtime.py             統合層（会話/見守りの実行・状態保持・非同期119生成）
├── webapp/                server.py(FastAPI API+MJPEG) / serialize.py(状態→JSON)
├── app.py / ui_render.py  旧Gradio UI（残置・非推奨）
├── companion/             persona.py(人格) / llm.py(LFM2: llamacpp/transformers/mock)
├── guardian/              camera.py(cv2+MediaPipe Tasks) / pose.py(転倒判定) /
│                          vision.py(LFM2-VL) / fsm.py(エスカレーションFSM)
├── voice/                 asr.py(faster-whisper/whisper.cpp) / tts.py(VOICEVOX, 話速) / jp_text.py
└── obs/trace.py           W&B Weave ラッパ（任意）

web/                       フロント（バニラHTML/CSS/JS + Live2D, 夜テーマ）
├── index.html  styles.css
├── main.js                会話・Live2D起動・RMSリップシンク
├── conversation.js        🎤ハンズフリー会話（VAD）
├── guardian.js            見守りポーリング・カメラ/デモ操作・119表示
├── live2d.js + vendor/    PIXI + Cubism            models/hiyori/ Live2Dモデル
docker-compose.yml         VOICEVOX(tomoshibi-voicevox) 定義
scripts/                   run_voicevox.sh / run_llm_server.sh / demo_scenario.py
data/demos/                デモ用テスト動画 demo1〜4.mp4（gitignore）
config/profile.example.json  医療/見守りプロフィール（端末ローカル）
```

## ライセンス / 注意

ハッカソンのプロトタイプです。実際の救急通報(119)は行いません（読み上げ原稿の生成＋シミュレーション）。
医療プロフィールは端末ローカルに保存され、外部送信しません。
Live2D「Hiyori」は Live2D Cubism 公式サンプル（各ライセンスに従う）。デモ動画は UR Fall Detection Dataset 由来。
