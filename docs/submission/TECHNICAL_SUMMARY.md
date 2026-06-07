# Technical Summary — 灯 Tomoshibi (Track 1)

> Architecture & structure of the system: tech stack, system diagram, and the two
> core sequences (companion voice turn / guardian fall escalation). Diagrams are
> Mermaid — they render on GitHub; in PDF/plain-text viewers they show as source.

## One-line

A 100% on-device AI companion + 2-stage fall-safety watch for elderly people
living alone. The only data that leaves the device is a family alert.

## Tech stack (layers)

```mermaid
flowchart TB
  subgraph P["Presentation · browser (WebGL)"]
    UI["index.html · main.js<br/>conversation.js (VAD) · guardian.js<br/>Live2D Hiyori (PIXI + Cubism)"]
  end
  subgraph A["API · FastAPI / uvicorn"]
    EP["/api/chat · /api/transcribe · /api/greet<br/>/api/guardian/* · /api/guardian/camera.mjpg"]
  end
  subgraph O["Orchestration"]
    RT["Runtime — companion_say / transcribe /<br/>report_fall_candidate / feed_event / tick"]
  end
  subgraph C["AI capabilities"]
    COMP["Companion — persona · llm"]
    GUARD["Guardian — camera · pose · vision · fsm"]
  end
  subgraph M["Models & runtimes (on-device)"]
    LLM["LFM2.5-1.2B-JP · llama.cpp"]
    VL["LFM2-VL-450M · transformers"]
    ASR["faster-whisper / whisper.cpp"]
    POSE["MediaPipe PoseLandmarker"]
    TTS["VOICEVOX"]
  end
  subgraph X["Local processes"]
    LS["llama-server :8080"]
    VV["VOICEVOX :50021"]
  end

  P --> A --> O --> C
  COMP --> LLM & ASR & TTS
  GUARD --> POSE & VL
  LLM --- LS
  TTS --- VV
```

### Models & frameworks

| Role | Model | Framework / runtime | Notes |
|---|---|---|---|
| Dialogue LLM | **LFM2.5-1.2B-JP-202606** (GGUF Q4_K_M) | llama.cpp (OpenAI-compatible HTTP) | Mac=Metal · Ryzen=Vulkan / FastFlowLM NPU |
| Fall confirmation (vision) | **LFM2-VL-450M** | transformers | invoked on ~1 frame only when a fall is suspected; lazy-loaded, own thread |
| Pose / "when to look" | MediaPipe PoseLandmarker (Tasks API, lite) | mediapipe | cheap, continuous, CPU |
| ASR | faster-whisper (Mac) / whisper.cpp (Ryzen) | CTranslate2 / whisper.cpp | VAD-segmented hands-free turns |
| TTS | **VOICEVOX** (cpu-0.25.2) | local HTTP :50021 (Docker) | slow speech for elders |
| Avatar | Live2D (Hiyori) | PIXI + Cubism (WebGL) | RMS lip-sync |
| Observability | W&B Weave (optional, default off) | weave | trace LFM calls |
| UI / orchestration | FastAPI + vanilla HTML/CSS/JS | uvicorn | MJPEG camera stream |

## System architecture

Three local processes; the only thing that ever leaves the home is the family alert.

```mermaid
flowchart LR
  subgraph DEVICE["🔒 On-device (single PC) — all inference local"]
    direction LR
    subgraph APP["App process — FastAPI + Runtime"]
      RT["Runtime"]
      subgraph CO["Companion"]
        ASRc["ASR (faster-whisper)"]
        LLMc["LLM client (llama.cpp)"]
        TTSc["TTS client"]
      end
      subgraph GU["Guardian"]
        CAM["CameraMonitor (cv2)"]
        POSEc["MediaPipe pose → fall heuristic"]
        VLc["LFM2-VL confirm"]
        FSMc["Escalation FSM"]
      end
    end
    LS["llama-server :8080<br/>LFM2.5-1.2B-JP"]
    VV["VOICEVOX :50021"]
    PII[("Medical profile<br/>profile.json — local only")]
    BR["Browser UI<br/>Live2D + dashboards"]
  end

  FAM["👨‍👩‍👧 Family notify<br/>(only external message)"]

  BR <-->|HTTP / MJPEG| RT
  RT --> CO & GU
  LLMc -->|HTTP| LS
  TTSc -->|HTTP| VV
  CAM --> POSEc --> VLc --> FSMc
  FSMc -.->|S2/S3| FAM
  FSMc --> PII

  classDef ext fill:#ffe1d6,stroke:#e86f4c,color:#7a2e16;
  class FAM ext;
```

## Sequence — Companion voice turn

```mermaid
sequenceDiagram
  autonumber
  actor U as Resident
  participant B as Browser (VAD)
  participant API as FastAPI
  participant RT as Runtime
  participant W as faster-whisper
  participant L as LFM2 (llama-server :8080)
  participant V as VOICEVOX :50021

  U->>B: speak (hands-free)
  Note over B: VAD detects end of utterance
  B->>API: POST /api/transcribe (audio)
  API->>RT: transcribe(wav)
  RT->>W: ASR
  W-->>RT: text
  RT-->>B: transcript
  B->>API: POST /api/chat (text)
  API->>RT: companion_say(text)
  RT->>L: chat completion (persona, slow, 2–3 sentences)
  L-->>RT: reply text
  RT->>V: synthesize (slow speech)
  V-->>RT: wav
  RT-->>B: reply text + audio url
  B-->>U: 🔊 speak + Live2D lip-sync (RMS)
```

## Sequence — Guardian fall escalation

```mermaid
sequenceDiagram
  autonumber
  participant CAM as CameraMonitor
  participant P as MediaPipe + fall heuristic
  participant RT as Runtime
  participant VL as LFM2-VL-450M
  participant FSM as Escalation FSM
  participant U as Resident
  participant FAM as Family
  participant L as LFM2 (119 script)
  participant V as VOICEVOX

  loop continuous (cheap)
    CAM->>P: frame → landmarks
    P-->>CAM: stand→horizontal+low, unrecovered ~CHECKIN window
  end
  P->>RT: report_fall_candidate(frame)
  RT->>VL: "Is a person lying on the floor?" (1 frame)
  VL-->>RT: yes → fall_confirmed

  RT->>FSM: feed_event(fall_confirmed)
  FSM-->>U: S1 CHECK_IN — voice "Are you OK?"
  alt 🙆 resident_ok
    U->>FSM: ok → RESOLVED
  else 🆘 resident_help
    U->>FSM: help → jump to S3
  else no answer (tick ≥ CHECKIN_TIMEOUT_S)
    FSM-->>FAM: S2 NOTIFY_FAMILY (only external message)
    alt family handles / tick ≥ FAMILY_ACK_TIMEOUT_S
      FSM->>L: S3 EMERGENCY — generate 119 script (async)
      L-->>FSM: name · conditions · meds · allergies
      FSM->>V: read script aloud
      V-->>U: 🔊 119 dispatch read-out
    end
  end
```

> FSM phases (`src/tomoshibi/guardian/fsm.py`):
> `MONITORING → CHECK_IN (S1) → NOTIFY_FAMILY (S2) → EMERGENCY (S3)`, plus `RESOLVED`.
> Timeouts are config constants `CHECKIN_TIMEOUT_S` and `FAMILY_ACK_TIMEOUT_S`.

## Key innovation — 2-stage vision cascade

Running a VLM on every frame is infeasible on-device. Cheap MediaPipe decides
*when to look*; the LFM2-VL model does a single semantic confirmation ("is a
person lying on the floor?") only on a candidate frame. Result: low power, high
precision, few false positives — and the heavy model stays mostly idle.

## Deployment & portability

Built and verified on Mac with **all models real**; ships to the assigned AMD
Ryzen AI PC. The app's Python is **unchanged** — only launch flags / runtime
backends differ (the LLM client speaks OpenAI-compatible HTTP either way).

| Component | Mac (dev / verification) | AMD Ryzen AI PC (target) |
|---|---|---|
| Dialogue LFM2 | llama.cpp (Metal) via `run_llm_server.sh` | llama.cpp + Vulkan / FastFlowLM NPU (`.q4nx`) |
| Vision LFM2-VL | transformers (MPS) | transformers (ROCm / CPU) |
| ASR | faster-whisper | faster-whisper or whisper.cpp |
| TTS | VOICEVOX (Docker) | VOICEVOX (Docker Desktop) |
| App | uvicorn | same — point `LLAMACPP_SERVER_URL` at the local server |

Backend selection is by env (`TOMOSHIBI_MODE`, `TTS_BACKEND`, `ASR_BACKEND`,
`LLAMACPP_SERVER_URL`); every backend also has a mock, so the app boots and the
test suite runs with no models present.

## Efficiency by design (qualitative)

- **Quantized dialogue model** — LFM2.5-1.2B-JP in GGUF **Q4_K_M** for a small
  memory footprint on integrated GPU / NPU.
- **VLM only when needed** — LFM2-VL runs on ~**1 frame** per suspected fall, not
  per frame; it is lazy-loaded and warmed on camera start.
- **Cheap continuous layer** — MediaPipe PoseLandmarker (lite) on CPU does the
  always-on watching.
- **Non-blocking** — vision inference and the 119-script generation run on
  separate threads so dialogue is never blocked.
- **No cloud round-trip** — inference cost is compute cycles, not API calls;
  works fully offline.

## Privacy / on-device proof

- All inference is local. PII (medical profile) is stored only on the device.
- The only external message is the family alert (`FAMILY_NOTIFY_CHANNEL=mock`
  keeps even that off the network). Demonstrable live in airplane mode.

## Code map (where the logic lives)

- `src/tomoshibi/guardian/pose.py` — fall heuristic (pure, unit-tested)
- `src/tomoshibi/guardian/vision.py` — LFM2-VL confirmation (English prompt)
- `src/tomoshibi/guardian/fsm.py` — S1→S2→S3 escalation FSM
- `src/tomoshibi/guardian/camera.py` — cv2 + MediaPipe Tasks, MJPEG stream
- `src/tomoshibi/companion/llm.py` — LFM2 (llamacpp / transformers / mock)
- `src/tomoshibi/voice/` — asr.py, tts.py (VOICEVOX), jp_text.py (read-aloud shaping)
- `src/tomoshibi/runtime.py` — integration + async 119 generation
- `src/tomoshibi/webapp/server.py` — FastAPI routes + MJPEG
- Tests: `tests/` — 51 unit + integration (FastAPI TestClient, mock E2E)
