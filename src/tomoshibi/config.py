"""集中設定 — 環境変数を読み、定数を一元管理する。

KISS: 1つの immutable な Settings に集約。マジックナンバーはここに名前を付ける。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# torch(libiomp5) と faster-whisper/ctranslate2・mediapipe の OpenMP 二重リンク衝突を回避する。
# 重いライブラリのimportより前に設定する必要があるため、最上流の config で行う（macOS開発向け）。
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

try:  # python-dotenv は任意。無ければ os.environ をそのまま使う。
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - 環境依存
    pass


# --- 見守りFSMの閾値（マジックナンバーをここで命名） ---
CHECKIN_TIMEOUT_S = 15.0  # S1: 本人へ声かけ後、反応を待つ秒数
FAMILY_ACK_TIMEOUT_S = 5.0  # S2→S3: 家族通知後、応答を待つ秒数（デモ用に短縮。本番は30s等）
FALL_STILLNESS_S = 3.0  # 転倒後この秒数静止し続けたら候補確定（デモ動画/side用）
# 俯瞰ライブ用: 倒れてからこの秒数起き上がらなければ確定（一時的に横になる動作の誤検知を抑制）。
OVERHEAD_STILLNESS_S = 10.0
VL_CONFIRM_MIN_CONFIDENCE = 0.5  # LFM2-VL 確認のしきい値

# 話し相手の1発話の文字数上限（高齢者の負担軽減。後処理 trim_reply の閾値）。
COMPANION_MAX_CHARS = 60

# --- LFM2 生成パラメータ（AGENTS.md の正準デフォルト） ---
LFM2_GEN = {
    "do_sample": True,
    "temperature": 0.3,
    "min_p": 0.15,
    "repetition_penalty": 1.05,
    # 高齢者＋TTS向けに短く。長文は聞きづらく、小型モデルでは生成が長いほど遅延も目立つ。
    # 60字目安＋短い質問に十分な範囲で抑え、応答速度を上げる。
    "max_new_tokens": 72,
}

# 119救急原稿は項目が多く長い（氏名/住所/持病/服薬/アレルギー/緊急連絡先…）ため、
# 会話用の上限(120)では途中で切れる。専用に大きめの上限を使う。
DISPATCH_MAX_TOKENS = 384


def _root() -> Path:
    # src/tomoshibi/config.py -> プロジェクトルート
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    """全体設定（不変）。`Settings.load()` で生成する。"""

    mode: str = "auto"  # auto | mock | real

    lfm2_gguf_path: str = "models/LFM2-1.2B-Q4_K_M.gguf"
    lfm2_hf_id: str = "LiquidAI/LFM2-1.2B"
    llamacpp_server_url: str = ""
    lfm2_vl_hf_id: str = "LiquidAI/LFM2-VL-450M"

    tts_backend: str = "voicevox"  # voicevox | lfm_audio | mock
    voicevox_url: str = "http://127.0.0.1:50021"
    voicevox_speaker: int = 3
    companion_speech_speed: float = 0.85  # 話し相手の話速（高齢者向けに ゆっくり, 1.0=標準）
    asr_backend: str = "whisper_cpp"  # whisper_cpp | faster_whisper | mock
    whisper_cpp_bin: str = "whisper-cli"
    whisper_cpp_model: str = "models/ggml-base.bin"
    # tiny | base | small | medium。日本語＋高齢者音声の精度のため small を既定に
    # （base は誤認識が多い）。重い場合は FASTER_WHISPER_MODEL で base へ切替可。
    faster_whisper_model: str = "small"

    family_notify_channel: str = "mock"  # mock | webhook | line_notify
    family_webhook_url: str = ""
    line_notify_token: str = ""

    enable_weave: bool = False
    weave_project: str = "tomoshibi"

    profile_path: str = "config/profile.json"

    guardian_camera_index: int = 0  # cv2.VideoCapture のカメラ番号
    guardian_fps: int = 12  # 姿勢検出ループの目標FPS
    guardian_video_path: str = "data/demos/fall_sustained.mp4"  # デモ動画（転倒テスト用）
    # ライブカメラの転倒判定視点: overhead(俯瞰/真上) | side(横)。デモ動画は常に side。
    guardian_camera_view: str = "overhead"

    root: Path = field(default_factory=_root)

    @staticmethod
    def load() -> "Settings":
        e = os.environ.get
        return Settings(
            mode=e("TOMOSHIBI_MODE", "auto"),
            lfm2_gguf_path=e("LFM2_GGUF_PATH", "models/LFM2-1.2B-Q4_K_M.gguf"),
            lfm2_hf_id=e("LFM2_HF_ID", "LiquidAI/LFM2-1.2B"),
            llamacpp_server_url=e("LLAMACPP_SERVER_URL", ""),
            lfm2_vl_hf_id=e("LFM2_VL_HF_ID", "LiquidAI/LFM2-VL-450M"),
            tts_backend=e("TTS_BACKEND", "voicevox"),
            voicevox_url=e("VOICEVOX_URL", "http://127.0.0.1:50021"),
            voicevox_speaker=int(e("VOICEVOX_SPEAKER", "3")),
            companion_speech_speed=float(e("COMPANION_SPEECH_SPEED", "0.85")),
            asr_backend=e("ASR_BACKEND", "whisper_cpp"),
            whisper_cpp_bin=e("WHISPER_CPP_BIN", "whisper-cli"),
            whisper_cpp_model=e("WHISPER_CPP_MODEL", "models/ggml-base.bin"),
            faster_whisper_model=e("FASTER_WHISPER_MODEL", "small"),
            family_notify_channel=e("FAMILY_NOTIFY_CHANNEL", "mock"),
            family_webhook_url=e("FAMILY_WEBHOOK_URL", ""),
            line_notify_token=e("LINE_NOTIFY_TOKEN", ""),
            enable_weave=e("TOMOSHIBI_ENABLE_WEAVE", "0") == "1",
            weave_project=e("WEAVE_PROJECT", "tomoshibi"),
            profile_path=e("PROFILE_PATH", "config/profile.json"),
            guardian_camera_index=int(e("GUARDIAN_CAMERA_INDEX", "0")),
            guardian_fps=int(e("GUARDIAN_FPS", "12")),
            guardian_video_path=e("GUARDIAN_VIDEO_PATH", "data/demos/fall_sustained.mp4"),
            guardian_camera_view=e("GUARDIAN_CAMERA_VIEW", "overhead"),
        )

    def resolve(self, path: str) -> Path:
        """相対パスをプロジェクトルート基準で解決する。"""
        p = Path(path)
        return p if p.is_absolute() else self.root / p
