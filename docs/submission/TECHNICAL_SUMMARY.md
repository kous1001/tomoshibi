# Technical Summary — 灯 Tomoshibi (Track 1)

> Required by the Submission Guide ("model(s) and framework, compute setup, device
> plus latency/efficiency numbers, and an architecture diagram or key technical
> innovation"). Fill every `<FILL: …>` with measured values on the assigned
> AMD Ryzen AI PC before submitting.

## One-line

A 100% on-device AI companion + 2-stage fall-safety watch for elderly people
living alone. The only data that leaves the device is a family alert.

## Models & frameworks

| Role | Model | Framework / runtime | Notes |
|---|---|---|---|
| Dialogue LLM | **LFM2.5-1.2B-JP-202606** (GGUF Q4_K_M) | llama.cpp (OpenAI-compatible HTTP) | Mac=Metal · Ryzen=Vulkan / FastFlowLM NPU |
| Fall confirmation (vision) | **LFM2-VL-450M** | transformers | invoked on ~1 frame only when a fall is suspected; lazy-loaded, own thread |
| Pose / "when to look" | MediaPipe PoseLandmarker (Tasks API, lite) | mediapipe | cheap, continuous, CPU |
| ASR | faster-whisper (Mac) / whisper.cpp (Ryzen) | CTranslate2 / whisper.cpp | VAD-segmented hands-free turns |
| TTS | **VOICEVOX** (cpu-0.25.2) | local HTTP :50021 (Docker) | slow speech for elders |
| Avatar | Live2D (Hiyori) | PIXI + Cubism (WebGL) | RMS lip-sync |
| Observability | W&B Weave (optional, default off) | weave | trace LFM calls + on-device latency |
| UI / orchestration | FastAPI + vanilla HTML/CSS/JS | uvicorn | MJPEG camera stream |

**Key innovation — 2-stage vision cascade.** Running a VLM on every frame is
infeasible on-device. Cheap MediaPipe decides *when to look*; the LFM2-VL model
does a single semantic confirmation ("is a person lying on the floor?") only on a
candidate frame. Result: low power, high precision, few false positives.

## Compute setup

- **Dev / verification:** Apple Silicon (arm64), CPython 3.12, torch 2.x (MPS).
  All models real (llm:llamacpp / tts:voicevox / asr:faster_whisper / vision:transformers).
- **Demo target device:** AMD Ryzen AI PC — `<FILL: assigned SKU, e.g. Strix Halo / Strix Point>`,
  `<FILL: RAM>`, XDNA 2 NPU. App Python is unchanged; only launch flags differ.
- **Runtime on Ryzen:** LFM2 dialogue via `<FILL: llama.cpp + Vulkan | FastFlowLM NPU>`;
  LFM2-VL via transformers (`<FILL: ROCm | CPU>`); ASR via `<FILL: faster-whisper | whisper.cpp>`.

## Latency & efficiency (measure on the Ryzen AI PC)

| Metric | Value |
|---|---|
| LFM2 dialogue — first token latency | `<FILL: ms>` |
| LFM2 dialogue — tokens/sec | `<FILL: tok/s>` |
| LFM2-VL fall confirmation (1 frame) | `<FILL: ms>` |
| ASR turn (faster-whisper/whisper.cpp) | `<FILL: ms>` |
| TTS (VOICEVOX) per utterance | `<FILL: ms>` |
| End-to-end voice turn (speak → reply audio) | `<FILL: s>` |
| Peak memory (idle / during VL confirm) | `<FILL: GB / GB>` |
| Power draw (idle watch / active) | `<FILL: W / W>` (optional) |

> Tip: enable W&B Weave (`WEAVE_ENABLED=1`, no training required) to capture LFM
> call traces and latency automatically, then screenshot for slide 3.

## Architecture

```
┌──────────────── Companion (話し相手) ────────────────┐
 🎤 mic ─VAD─▶ faster-whisper (ASR) ─▶ LFM2.5-1.2B-JP (llama.cpp)
        ─▶ VOICEVOX (TTS, slow) ─▶ 🔊 speaker + Live2D lip-sync (RMS)
└──────────────────────────────────────────────────────┘

┌──────────── Guardian (見守り) — 2-stage cascade ─────────────┐
 📷 cam ─cheap/continuous─▶ MediaPipe PoseLandmarker
        ─▶ fall heuristic (stand→horizontal+low, ~3s unrecovered)
   candidate ─1 frame─▶ LFM2-VL-450M confirm ──┐
                                               ▼
   Escalation FSM:  S1 check-in ─15s─▶ S2 family ─5s─▶ S3 119 read-out
└──────────────────────────────────────────────────────────────┘
        UI: FastAPI + vanilla HTML/JS (night theme, Live2D), MJPEG camera
```

## Privacy / on-device proof

- All inference is local. PII (medical profile) is stored only on the device.
- The only external message is the family alert (`FAMILY_NOTIFY_CHANNEL=mock`
  keeps even that off the network). Demonstrable live in airplane mode.

## Code map (where the logic lives)

- `src/tomoshibi/guardian/pose.py` — fall heuristic (pure, unit-tested)
- `src/tomoshibi/guardian/vision.py` — LFM2-VL confirmation (English prompt)
- `src/tomoshibi/guardian/fsm.py` — S1→S2→S3 escalation FSM
- `src/tomoshibi/companion/llm.py` — LFM2 (llamacpp / transformers / mock)
- `src/tomoshibi/voice/` — asr.py, tts.py (VOICEVOX), jp_text.py (read-aloud shaping)
- `src/tomoshibi/runtime.py` — integration + async 119 generation
- Tests: `tests/` — 51 unit + integration (FastAPI TestClient, mock E2E)
