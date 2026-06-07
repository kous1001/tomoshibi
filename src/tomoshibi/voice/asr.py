"""ASR — 音声認識。

backend:
- whisper_cpp … whisper.cpp バイナリを subprocess 起動（オンデバイス）。
- mock        … 入力テキストをそのまま返す（UIのテキスト欄を音声入力の代用に）。

返り値は認識テキスト(str)。
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from ..config import Settings

logger = logging.getLogger(__name__)

# 認識のヒント（高齢者の日常会話という文脈を与え、口語・短い発話の取りこぼしを減らす）。
_ASR_PROMPT = "一人暮らしの高齢者との、やさしい日常会話です。"


class MockASR:
    backend = "mock"

    def transcribe(self, wav_path: str | None) -> str:
        # Mockではマイク入力を扱わない。UI側のテキスト欄を使う想定。
        return ""


class FasterWhisperASR:
    """faster-whisper（CTranslate2）によるオンデバイスASR。Mac開発に最適（torch不要）。"""

    backend = "faster_whisper"

    def __init__(self, model_size: str = "base"):
        from faster_whisper import WhisperModel  # 遅延import（重い）

        # CPU + int8 で軽量・高速。Ryzen/GPUなら device/compute_type を変更可。
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")

    def transcribe(self, wav_path: str | None) -> str:
        if not wav_path or not Path(wav_path).exists():
            return ""
        try:
            segments, _ = self.model.transcribe(
                wav_path,
                language="ja",
                beam_size=5,  # 既定値。貪欲(=1)だと日本語で誤認識が増える。
                initial_prompt=_ASR_PROMPT,
                vad_filter=True,
                # 高齢者の小声・語頭/語尾を削り過ぎないよう既定より緩める。
                vad_parameters=dict(threshold=0.3, min_silence_duration_ms=300),
                condition_on_previous_text=False,  # 短い単発ターンでの誤り伝播を防ぐ。
            )
            text = "".join(seg.text for seg in segments).strip()
            if not text:
                logger.warning("ASR: 認識結果が空でした (path=%s)", wav_path)
            return text
        except Exception:
            logger.exception("ASR: faster-whisper の認識に失敗しました (path=%s)", wav_path)
            return ""


class WhisperCppASR:
    backend = "whisper_cpp"

    def __init__(self, binary: str, model: str):
        self.binary = binary
        self.model = model

    def transcribe(self, wav_path: str | None) -> str:
        if not wav_path or not Path(wav_path).exists():
            return ""
        try:
            # whisper.cpp の CLI: JSON 出力で結果を取得
            proc = subprocess.run(
                [self.binary, "-m", self.model, "-f", wav_path, "-l", "ja", "-oj", "-of", wav_path],
                capture_output=True,
                text=True,
                timeout=60,
            )
            jpath = Path(wav_path + ".json")
            if jpath.exists():
                data = json.loads(jpath.read_text(encoding="utf-8"))
                segs = data.get("transcription", [])
                return "".join(s.get("text", "") for s in segs).strip()
            return proc.stdout.strip()
        except Exception:
            return ""


def build_asr(settings: Settings):
    if settings.mode == "mock" or settings.asr_backend == "mock":
        return MockASR()
    if settings.asr_backend == "faster_whisper":
        try:
            return FasterWhisperASR(settings.faster_whisper_model)
        except Exception:
            # 無言でMock(常に"")に落ちると「精度が悪い」ように見えるため必ず記録する。
            logger.exception(
                "ASR: faster-whisper の初期化に失敗 → MockASRにフォールバック (model=%s)",
                settings.faster_whisper_model,
            )
            return MockASR()
    if settings.asr_backend == "whisper_cpp":
        return WhisperCppASR(settings.whisper_cpp_bin, settings.whisper_cpp_model)
    return MockASR()
