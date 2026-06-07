================================================================================
  灯 / Tomoshibi — Demo Assets
  Hack the Liquid WAY Tokyo Hackathon 2026 — Track 1 (LFM Application Track)
  Team: <TEAMNAME>          Submission date: 2026-06-07
================================================================================

Tagline
-------
  EN: Tomoshibi — a 100% on-device AI companion & safety watch for elderly
      people who live alone. Only a family alert ever leaves the device.
  JP: 灯（ともしび）— 一人暮らしの高齢者のための、100%オンデバイスの
      AI 話し相手＆見守り。外に出るのは「家族への通知」一点だけ。

Public repository
-----------------
  <PASTE PUBLIC GITHUB URL HERE>

--------------------------------------------------------------------------------
FILE LIST (what is in this folder)
--------------------------------------------------------------------------------
  README.txt ................ This file. Descriptions + demo setup steps.
  slides.pdf ................ 4-slide deck (problem / why-LFM / results / impact).
  demo.mp4 .................. 60–90s demo video (UI + fall → S1→S2→S3 + 119 + airplane mode).
  screenshots/
    01-conversation.png ..... Companion UI (Live2D + voice chat).
    02-guardian-timeline.png  Fall detected → S1 → S2 → S3 escalation timeline.
    03-119-script.png ....... Generated 119 dispatch script + medical card.
    04-weave-trace.png ...... W&B Weave trace / on-device latency (if captured).
  photos/
    product-*.png/jpg ....... Product shots (the app running on the Ryzen AI PC).
    team-*.jpg .............. Team photo(s).
  captions_bios.txt ........ Photo captions and team member bios.

  NOTE: replace every <...> placeholder before submitting. If an asset is not yet
  recorded, see the team checklist in the repo: docs/SUBMISSION.md.

--------------------------------------------------------------------------------
WHAT IT IS
--------------------------------------------------------------------------------
Tomoshibi is a single app with two faces for an elder living alone:

  1) Companion (話し相手) — warm Japanese VOICE conversation (slow, elder-friendly):
     listening, reminiscence, medication reminders.
  2) Guardian (見守り) — a 2-stage on-device fall watch that escalates gracefully:
       S1 check-in by voice  → (15s no answer) →
       S2 notify family      → (5s no answer)  →
       S3 read a 119 dispatch script aloud (name, conditions, meds, allergies).

Why an LFM: a home camera + mic is only acceptable if data never leaves the
device. All inference is local (LFM2.5-1.2B-JP for dialogue, LFM2-VL-450M for
fall confirmation, faster-whisper ASR, VOICEVOX TTS). The ONLY thing that leaves
the home is the family alert — demonstrable live in airplane mode.

--------------------------------------------------------------------------------
DEMO SETUP & RUN STEPS
--------------------------------------------------------------------------------
The app has two run modes. Use mock for a guaranteed-green walkthrough with no
models; use the real-model setup for the live demo.

A) Quick walkthrough — MOCK (no models, any machine)
   uv venv --python 3.12
   uv pip install -e .
   cp config/profile.example.json config/profile.json
   # Headless scenario (no GUI):
   PYTHONPATH=src TOMOSHIBI_MODE=mock python scripts/demo_scenario.py
   # UI:
   PYTHONPATH=src TOMOSHIBI_MODE=mock PROFILE_PATH=config/profile.example.json \
     python -m uvicorn tomoshibi.webapp.server:app --port 8000
   # → open http://127.0.0.1:8000

B) Live demo — REAL models (3 processes: VOICEVOX / LFM2 server / app)
   uv pip install -e ".[asr,vision,models]"
   brew install llama.cpp           # Mac (Metal). On Ryzen AI PC: llama.cpp + Vulkan / FastFlowLM
   huggingface-cli download LiquidAI/LFM2.5-1.2B-JP-202606-GGUF \
     LFM2.5-1.2B-JP-202606-Q4_K_M.gguf --local-dir models
   mv models/LFM2.5-1.2B-JP-202606-Q4_K_M.gguf models/LFM2.5-1.2B-JP-Q4_K_M.gguf

   bash scripts/run_voicevox.sh     # 1) VOICEVOX  (TTS) :50021
   bash scripts/run_llm_server.sh   # 2) LFM2 dialogue server :8080
   LLAMACPP_SERVER_URL=http://127.0.0.1:8080 TOMOSHIBI_MODE=auto \
     TTS_BACKEND=voicevox ASR_BACKEND=faster_whisper \
     PROFILE_PATH=config/profile.example.json \
     PYTHONPATH=src python -m uvicorn tomoshibi.webapp.server:app --port 8000   # 3) app

   Success check: startup log shows
     backends: llm:llamacpp / tts:voicevox / asr:faster_whisper / vision:transformers

DEMO FLOW (≈5 min live)
   1. Companion: speak — "最近寂しくてね" → Tomoshibi replies gently (voice).
   2. Guardian: press a "🎬 Demo" video button (or fall in front of the camera).
      Fall → LFM2-VL confirms → S1 check-in → no answer → S2 family → S3 119 read-out.
      Buttons: 🙆 OK (resolve) / 🆘 Help (jump to S3) / 👨‍👩‍👧 family handled.
   3. Privacy proof: turn on airplane mode — everything still works.

NOTES
   - Real LFM2-VL on macOS needs arm64-native Python (torch >= 2.4). x86 falls back
     to a vision mock automatically.
   - PII (medical profile) stays local; the demo does NOT place a real 119 call.
   - Live2D "Hiyori" = official Cubism sample. Test videos: UR Fall Detection Dataset.

Contact: <name / Discord handle>
================================================================================
