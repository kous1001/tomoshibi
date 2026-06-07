"""TTS — 日本語音声合成。

backend:
- voicevox  … このプロジェクト所有のVOICEVOXエンジン(HTTP)。`scripts/run_voicevox.sh` で起動。
              読み上げ整形は voice/jp_text.py に内製（他プロジェクトに依存しない）。
- lfm_audio … LFM2.5-Audio（スポンサー整合・要ROCm GPU）。雛形のみ。
- mock      … 音声を生成せず、発話テキストだけ返す（Mac開発/UI確認）。

返り値は (wav_path|None, spoken_text)。wav_path が None ならUIはテキスト表示のみ。
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass

from ..config import Settings
from .jp_text import normalize_for_tts


@dataclass(frozen=True)
class Speech:
    wav_path: str | None
    text: str
    backend: str


class MockTTS:
    backend = "mock"

    def speak(self, text: str, speed: float = 1.0) -> Speech:
        return Speech(None, text, self.backend)


class VoicevoxTTS:
    backend = "voicevox"

    def __init__(self, url: str, speaker: int):
        self.url = url.rstrip("/")
        self.speaker = speaker

    def speak(self, text: str, speed: float = 1.0) -> Speech:
        """speed: 話速(1.0=標準, <1.0で ゆっくり)。高齢者向け会話は遅め推奨。"""
        try:
            import requests

            spoken = normalize_for_tts(text)  # 読み上げ用に整形（表示テキストは変えない）
            q = requests.post(
                f"{self.url}/audio_query",
                params={"text": spoken, "speaker": self.speaker},
                timeout=10,
            )
            q.raise_for_status()
            query = q.json()
            query["speedScale"] = speed  # 話速を上書き（ゆっくり/標準）
            synth = requests.post(
                f"{self.url}/synthesis",
                params={"speaker": self.speaker},
                json=query,
                timeout=30,
            )
            synth.raise_for_status()
            path = tempfile.mktemp(suffix=".wav")
            with open(path, "wb") as f:
                f.write(synth.content)
            return Speech(path, text, self.backend)
        except Exception:
            # 合成失敗でも会話を止めない
            return Speech(None, text, "mock(fallback)")


def build_tts(settings: Settings):
    if settings.mode == "mock" or settings.tts_backend == "mock":
        return MockTTS()
    if settings.tts_backend == "voicevox":
        return VoicevoxTTS(settings.voicevox_url, settings.voicevox_speaker)
    # lfm_audio は実機ROCmでの実装ポイント（ここでは安全にMockへ）
    return MockTTS()
