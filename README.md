# 灯 Tomoshibi

[![English](https://img.shields.io/badge/lang-English-2E8C82?style=for-the-badge)](README.md)
[![日本語](https://img.shields.io/badge/lang-日本語-9AA6C6?style=for-the-badge)](README.ja.md)

> A **100% on-device** AI companion & safety watch for elderly people who live alone.
> Built for **Hack the Liquid WAY Tokyo Hackathon 2026 — Track 1 (LFM Application)**.
> Dialogue, vision, and voice all run locally (LFM2 / LFM2-VL / faster-whisper / VOICEVOX).
> The **only** thing that ever leaves the device is a family alert — and it ports to an AMD Ryzen AI PC as-is.

---

## Why Tomoshibi

Japan is a super-aged society. Two problems hit elders who live alone hardest: **loneliness**, and a **fall that nobody notices** — sometimes a lonely death discovered days later.

The biggest barrier to putting a camera in an elder's home is **privacy**. Tomoshibi solves it by design: **every inference runs on the device**, and the only outbound message is a family alert (mocked in the demo). A cloud LLM can't meet that bar — an on-device LFM can.

Tomoshibi is one app with two faces:

- **Companion (話し相手)** — warm Japanese **voice** conversation powered by LFM2: listening, reminiscence, gentle check-ins, medication reminders. It speaks **slowly** for elders (hands-free mic or text).
- **Guardian (見守り)** — a **2-stage** on-device fall watch that escalates gracefully:
  **voice check-in → notify family if no answer → read a 119 emergency script aloud** (a simulation).

---

## Architecture

```
┌──────────────────────── Companion (話し相手) ────────────────────────┐
 🎤 mic ─VAD auto-segment→ faster-whisper (ASR) ─→ LFM2.5-1.2B-JP (llama.cpp)
        ─→ VOICEVOX (TTS, slow) ─→ speaker  +  Live2D lip-sync (RMS)
└──────────────────────────────────────────────────────────────────────┘

┌──────────────── Guardian (見守り) — 2-stage cascade ────────────────┐
 📷 camera ─cheap/continuous→ MediaPipe PoseLandmarker ─→ fall heuristic
            (stand → horizontal + low → unrecovered for 3 s = candidate)
   only on a candidate, 1 frame → LFM2-VL-450M (semantic confirm) ──┐
                                                                    ▼
   Escalation FSM:  S1 check-in →(15s)→ S2 notify family →(5s)→ S3 119 read-out
└──────────────────────────────────────────────────────────────────────┘
                 UI: FastAPI + vanilla HTML/JS (night theme · Live2D)
```

**Why two stages?** Running a VLM on every frame is infeasible on-device. Cheap MediaPipe decides **when to look**; the LFM2-VL model does a single semantic confirmation (*“is a person lying on the floor?”*) only on a candidate frame. Result: **low power, high precision, few false positives** — and the heavy model stays mostly idle.

---

## Tech stack

| Role | Model / library (real) | Where it runs | Mock (dev) |
|---|---|---|---|
| Dialogue LLM | **LFM2.5-1.2B-JP** (GGUF Q4_K_M) | llama.cpp server — Mac=Metal / Ryzen=Vulkan·FastFlowLM NPU (OpenAI-compatible HTTP) | rule-based replies |
| Fall confirmation | **LFM2-VL-450M** | transformers (Mac=MPS / Ryzen=ROCm·CPU); candidate-only, lazy-loaded | always “fallen” |
| Pose (when-to-look) | **MediaPipe PoseLandmarker** (lite) | CPU, continuous | pure-function tested |
| TTS | **VOICEVOX** (cpu-0.25.2, Docker) | local HTTP :50021 | text only |
| ASR | **faster-whisper** (Mac) / **whisper.cpp** (Ryzen) | CPU / Metal | empty string |
| Avatar | **Live2D (Hiyori)** + PIXI / Cubism | browser (WebGL) | — |
| Observability | **W&B Weave** (optional, off by default) | cloud (logs only) | no-op |
| UI / API | **FastAPI** + vanilla HTML/CSS/JS | local | same |

Design key: **every backend has a mock**, so the app boots and the full test suite runs with no models present. Moving to real models is **just environment variables** — the Python code is unchanged.

Companion replies are kept short for elders and TTS (**1–2 sentences, ≤60 chars**, `max_new_tokens=72`, trimmed by `companion/text.py`).

---

## Quick start (mock — no models)

```bash
uv venv --python 3.12            # arm64-native recommended if you want real LFM2-VL (see Notes)
uv pip install -e .              # minimal deps (fastapi / uvicorn / numpy / pillow ...)
cp config/profile.example.json config/profile.json

# Headless walkthrough of every scenario (no GUI)
PYTHONPATH=src TOMOSHIBI_MODE=mock python scripts/demo_scenario.py

# UI (Live2D chat + guardian dashboard)
PYTHONPATH=src TOMOSHIBI_MODE=mock PROFILE_PATH=config/profile.example.json \
  python -m uvicorn tomoshibi.webapp.server:app --port 8000
# → http://127.0.0.1:8000  (Live2D needs a WebGL browser)
```

UI: left = conversation (Live2D + single speech bubble + 🎤), right = guardian (camera/demo · status · timeline · 119 script · medical card). Press **“🧪 Simulate fall”** → S1 →(15s)→ S2 →(5s)→ S3 runs automatically; branch with **🙆 OK / 🆘 Help / 👨‍👩‍👧 family handled**.

> The legacy Gradio UI remains in `src/tomoshibi/app.py` (deprecated, mock-debug only). The current UI is the FastAPI app.

---

## Run with real models (3 processes)

Real LFM2 dialogue + real voice + real vision use **three processes** (VOICEVOX / LFM2 server / app).

```bash
# Deps + model
uv pip install -e ".[asr,vision,models]"
brew install llama.cpp                              # llama-server (Mac=Metal)
huggingface-cli download LiquidAI/LFM2.5-1.2B-JP-202606-GGUF \
  LFM2.5-1.2B-JP-202606-Q4_K_M.gguf --local-dir models
mv models/LFM2.5-1.2B-JP-202606-Q4_K_M.gguf models/LFM2.5-1.2B-JP-Q4_K_M.gguf

# 1) VOICEVOX :50021   2) LFM2 dialogue :8080   3) app
bash scripts/run_voicevox.sh
bash scripts/run_llm_server.sh
LLAMACPP_SERVER_URL=http://127.0.0.1:8080 TOMOSHIBI_MODE=auto \
  TTS_BACKEND=voicevox ASR_BACKEND=faster_whisper \
  PROFILE_PATH=config/profile.example.json \
  PYTHONPATH=src python -m uvicorn tomoshibi.webapp.server:app --port 8000
```

- Success when the startup log shows `backends: llm:llamacpp / tts:voicevox / asr:faster_whisper / vision:transformers`.
- **Guardian camera**: click **“📷 ON”** in the right panel (macOS asks for camera permission on first run).
- **Test videos**: **“🎬 Demo 1–4”** — demos 1–3 are falls, **demo 4 is normal activity** (verifies no false positive). Clips live in `data/demos/` (from the UR Fall Detection Dataset).

### Port to AMD Ryzen AI PC (app Python unchanged)

| Component | Mac | AMD Ryzen AI PC |
|---|---|---|
| Dialogue LFM2 | `run_llm_server.sh` (llama.cpp Metal) | same compose; `-ngl` → Vulkan / FastFlowLM NPU |
| VOICEVOX | `run_voicevox.sh` (Docker compose) | same (Windows Docker Desktop) |
| Vision LFM2-VL | transformers (MPS) | transformers (ROCm / CPU) |
| ASR | faster-whisper | whisper.cpp (`ASR_BACKEND=whisper_cpp`) too |
| App | unchanged | just point `LLAMACPP_SERVER_URL` at the local server |

`LlamaCppLLM` speaks OpenAI-compatible HTTP, so swapping the dialogue model is **launch-command only**. Full steps → [`docs/RYZEN_AI_PC_SETUP.md`](docs/RYZEN_AI_PC_SETUP.md).

---

## Privacy proof

During the demo you can turn on **airplane mode** and everything still works — conversation, fall detection, and the 119 read-out. The only outbound message is the family alert; with `FAMILY_NOTIFY_CHANNEL=mock` even that stays off the network. The medical profile (PII) is stored **only on the device**.

## Tests

```bash
uv pip install pytest
PYTHONPATH=src TOMOSHIBI_MODE=mock python -m pytest -q     # 71 tests
```

- Pure functions: fall heuristic (`pose.py`), escalation FSM (`fsm.py`), 119 generation (`dispatch.py`), read-aloud shaping (`jp_text.py`), reply trimming (`companion/text.py`), persona prompt (`persona.py`).
- Integration: FastAPI chat / guardian / transcribe via TestClient (mock E2E).

## Project layout

```
src/tomoshibi/
├── config.py              settings & thresholds (FSM timers / speech speed / gen tokens) + OpenMP fix
├── runtime.py             integration layer (companion/guardian, state, async 119 generation)
├── webapp/                server.py (FastAPI API + MJPEG) · serialize.py (state → JSON)
├── companion/             persona.py · llm.py (LFM2: llamacpp/transformers/mock) · text.py (reply trim)
├── guardian/              camera.py (cv2 + MediaPipe) · pose.py (fall heuristic) ·
│                          vision.py (LFM2-VL) · fsm.py (escalation FSM)
├── voice/                 asr.py · tts.py (VOICEVOX) · jp_text.py (read-aloud shaping)
├── emergency/             profile.py · dispatch.py (119 script) · notify.py (family)
└── obs/trace.py           W&B Weave wrapper (optional)

web/                       frontend (vanilla HTML/CSS/JS + Live2D, night theme)
scripts/                   run_voicevox.sh · run_llm_server.sh · demo_scenario.py
config/profile.example.json  medical / guardian profile (device-local)
docker-compose.yml         VOICEVOX service
```

## License & notes

A hackathon prototype. It does **not** place a real 119 call — it generates and reads a dispatch script (simulation). The medical profile is stored locally and never sent off-device. Live2D “Hiyori” is the official Cubism sample (subject to its license). Demo clips are from the UR Fall Detection Dataset. Code is MIT licensed (see [`LICENSE`](LICENSE)).
