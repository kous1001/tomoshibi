"""FasterWhisperASR の認識パラメータ回帰テスト。

重い faster_whisper を読み込まずに、transcribe() がモデルへ正しい
パラメータ（beam_size/initial_prompt/vad など）を渡すことを担保する。
"""

import tempfile
from pathlib import Path

from tomoshibi.voice.asr import FasterWhisperASR


class _FakeModel:
    """transcribe の呼び出し引数を記録するスタブ。"""

    def __init__(self):
        self.calls: list[dict] = []

    def transcribe(self, wav_path, **kwargs):
        self.calls.append({"wav_path": wav_path, **kwargs})
        # (segments, info) を返す本物のシグネチャに合わせる
        return [], None


def _asr_with_fake() -> tuple[FasterWhisperASR, _FakeModel]:
    # __init__ は faster_whisper を import するため bypass する
    asr = FasterWhisperASR.__new__(FasterWhisperASR)
    fake = _FakeModel()
    asr.model = fake
    return asr, fake


def test_transcribe_passes_accuracy_params():
    asr, fake = _asr_with_fake()
    with tempfile.NamedTemporaryFile(suffix=".wav") as f:
        asr.transcribe(f.name)

    assert len(fake.calls) == 1
    kw = fake.calls[0]
    assert kw["language"] == "ja"
    assert kw["beam_size"] == 5
    assert kw["initial_prompt"]  # 非空
    assert kw["vad_filter"] is True
    assert kw["condition_on_previous_text"] is False


def test_transcribe_missing_path_returns_empty():
    asr, fake = _asr_with_fake()
    assert asr.transcribe(None) == ""
    assert asr.transcribe("/no/such/file.wav") == ""
    assert fake.calls == []  # モデルは呼ばれない
