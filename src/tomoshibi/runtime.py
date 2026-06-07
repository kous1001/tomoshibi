"""ランタイム — 全バックエンドを束ね、FSMのActionを実行する統合層。

app.py(UI) はここだけを呼べばよい。状態を持つ唯一の場所。
FSM/ヒューリスティック等の純粋ロジックは変更せず、ここで副作用を起こす。
"""

from __future__ import annotations

import base64
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .companion.llm import build_llm
from .companion.persona import build_system_prompt
from .companion.text import trim_reply
from .config import Settings
from .emergency.dispatch import build_dispatch_facts, compose_dispatch_script
from .emergency.notify import notify_family
from .emergency.profile import Profile, load_profile
from .guardian.fsm import (
    Action,
    ActionKind,
    EscalationState,
    Event,
    Phase,
    transition,
)
from .guardian.vision import build_vision
from .obs import trace
from .voice.asr import build_asr
from .voice.tts import build_tts


@dataclass(frozen=True)
class TimelineEntry:
    t: float
    kind: str  # log | speak | notify | emergency | chat
    text: str


@dataclass
class Runtime:
    settings: Settings
    profile: Profile
    llm: object
    tts: object
    asr: object
    vision: object
    system_prompt: str
    escalation: EscalationState = field(default_factory=EscalationState)
    chat_history: list[tuple[str, str]] = field(default_factory=list)
    timeline: list[TimelineEntry] = field(default_factory=list)
    last_emergency_script: str = ""
    last_emergency_facts: list[str] = field(default_factory=list)
    # 見守りが発話したときに、ブラウザで再生させるための最新音声（1発話分）
    speech_seq: int = 0
    last_speech_text: str = ""
    last_speech_audio_b64: str | None = None

    # ------------------------------------------------------------------ #
    # 構築
    # ------------------------------------------------------------------ #
    @staticmethod
    def build(settings: Settings | None = None) -> "Runtime":
        settings = settings or Settings.load()
        trace.init(settings.weave_project, settings.enable_weave)
        profile = load_profile(settings.resolve(settings.profile_path))
        return Runtime(
            settings=settings,
            profile=profile,
            llm=build_llm(settings),
            tts=build_tts(settings),
            asr=build_asr(settings),
            vision=build_vision(settings),
            system_prompt=build_system_prompt(profile),
        )

    def _log(self, kind: str, text: str) -> None:
        self.timeline.append(TimelineEntry(time.time(), kind, text))

    def _emit_speech(self, text: str, wav_path: str | None) -> None:
        """見守り発話をブラウザ再生用に保持（音声はb64化、mockはNone）。"""
        audio = None
        if wav_path:
            try:
                audio = base64.b64encode(Path(wav_path).read_bytes()).decode("ascii")
            except Exception:
                audio = None
        self.speech_seq += 1
        self.last_speech_text = text
        self.last_speech_audio_b64 = audio

    # ------------------------------------------------------------------ #
    # 話し相手(Companion)
    # ------------------------------------------------------------------ #
    @trace.op("companion_turn")
    def companion_say(self, user_text: str) -> tuple[str, str | None]:
        """ユーザー発話に応答。(返答テキスト, 音声wavパス|None) を返す。"""
        user_text = (user_text or "").strip()
        if not user_text:
            return "", None
        # 高齢者向けに1発話を短く。モデルが長く返しても文単位で丸める。
        reply = trim_reply(self.llm.chat(self.system_prompt, self.chat_history, user_text))
        self.chat_history.append((user_text, reply))
        self._log("chat", f"本人: {user_text} / 灯: {reply}")
        # 話し相手の発話は高齢者向けに ゆっくり
        speech = self.tts.speak(reply, speed=self.settings.companion_speech_speed)
        return reply, speech.wav_path

    @trace.op("companion_greet")
    def companion_greet(self) -> tuple[str, str | None]:
        """起動時の灯からの最初の挨拶（決定論的で確実）。"""
        name = self.profile.resident.name or "あなた"
        greeting = f"{name}さん、こんにちは。灯（あかり）です。今日はどんな一日でしたか？"
        self._log("speak", f"灯: {greeting}")
        speech = self.tts.speak(greeting, speed=self.settings.companion_speech_speed)
        return greeting, speech.wav_path

    @trace.op("asr_transcribe")
    def transcribe(self, wav_path: str | None) -> str:
        """音声(wav)→日本語テキスト。バックエンドが無効なら空文字。"""
        return self.asr.transcribe(wav_path)

    def warm_vision(self) -> None:
        """LFM2-VL を先読みロード（初回検知の遅延を消す）。失敗は無視。"""
        fn = getattr(self.vision, "ensure_loaded", None)
        if fn:
            try:
                fn()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # 見守り(Guardian) — FSM駆動
    # ------------------------------------------------------------------ #
    def _apply_event(self, event: Event) -> list[Action]:
        now = time.time()
        new_state, actions = transition(self.escalation, event, now)
        self.escalation = new_state
        for a in actions:
            self._execute(a)
        return actions

    @trace.op("escalation_event")
    def feed_event(self, event: Event) -> EscalationState:
        self._apply_event(event)
        return self.escalation

    def tick(self) -> EscalationState:
        """定期呼び出し。タイムアウトを評価して自動遷移する。"""
        if self.escalation.phase in (Phase.CHECK_IN, Phase.NOTIFY_FAMILY):
            self._apply_event(Event.TICK)
        return self.escalation

    @trace.op("vision_confirm_fall")
    def report_fall_candidate(self, image=None) -> EscalationState:
        """姿勢ヒューリスティックが候補を立てたら呼ぶ。VLで確認→確定で起動。"""
        if image is None:  # 画像が無ければVL確認できない（手動シミュレートは simulate_fall を使う）
            return self.escalation
        print("[灯] LFM2-VL 確認開始…", flush=True)
        result = self.vision.confirm(image)
        print(f"[灯] LFM2-VL 結果: is_fall={result.is_fall} "
              f"conf={result.confidence:.2f} backend={result.backend}", flush=True)
        self._log("log", f"LFM2-VL確認: {'転倒' if result.is_fall else '非転倒'} "
                          f"(信頼度{result.confidence:.0%}) {result.rationale}")
        if result.is_fall:
            self._apply_event(Event.FALL_CONFIRMED)
        return self.escalation

    def simulate_fall(self) -> EscalationState:
        """🧪 手動シミュレート: VLを介さず直接「転倒確定」させる（デモ/カメラ無し用）。"""
        self._log("log", "🧪 転倒をシミュレート（手動・VL省略）")
        self._apply_event(Event.FALL_CONFIRMED)
        return self.escalation

    # ------------------------------------------------------------------ #
    # Action 実行（副作用はここに集約）
    # ------------------------------------------------------------------ #
    def _execute(self, action: Action) -> None:
        if action.kind == ActionKind.LOG:
            self._log("log", action.message)

        elif action.kind == ActionKind.SPEAK:
            speech = self.tts.speak(action.message)
            self._emit_speech(action.message, speech.wav_path)
            self._log("speak", f"灯: {action.message}")

        elif action.kind == ActionKind.NOTIFY_FAMILY:
            res = notify_family(self.settings, self.profile, action.message)
            who = "、".join(res.recipients)
            self._log("notify", f"家族へ通知[{res.channel}] → {who}（{'成功' if res.ok else res.detail}）")

        elif action.kind == ActionKind.ANNOUNCE_EMERGENCY:
            situation = action.detail.get("reason", "転倒・応答なし")
            # 事実は決定論で即時表示。原稿(LLM生成)＋読み上げは重い(~十数秒)ので別スレッドで実行し、
            # S3への画面遷移をブロックしない（生成完了後にポーリングで反映）。
            self.last_emergency_facts = build_dispatch_facts(self.profile, situation=situation)
            self.last_emergency_script = "（救急への通報内容を準備しています…）"
            self._log("emergency", "緊急対応に移行。119通報内容を準備中…")
            threading.Thread(
                target=self._compose_and_announce_emergency, args=(situation,), daemon=True
            ).start()

    def _compose_and_announce_emergency(self, situation: str) -> None:
        """119原稿をLLMで生成し、状態更新＋読み上げ（別スレッド実行）。"""
        script, facts = compose_dispatch_script(self.profile, situation=situation, llm=self.llm)
        self.last_emergency_script = script
        self.last_emergency_facts = facts
        speech = self.tts.speak(script)
        self._emit_speech(script, speech.wav_path)
        self._log("emergency", f"119通報(シミュレーション)を読み上げ: {script}")

    # ------------------------------------------------------------------ #
    # UI向けヘルパ
    # ------------------------------------------------------------------ #
    def reset_guardian(self) -> None:
        """見守りをクリーンな初期状態へ。タイムラインと緊急原稿も消す。

        ページ再読込のたびに前回の緊急状態が残らないようにする（単一ユーザー前提）。
        last_speech_* は消さない（フロントが seq でベースライン管理するため）。
        """
        self.escalation = EscalationState()
        self.timeline.clear()
        self.last_emergency_script = ""
        self.last_emergency_facts = []
        self._log("log", "見守りを通常状態にリセットしました")

    def backends(self) -> dict[str, str]:
        return {
            "llm": getattr(self.llm, "backend", "?"),
            "tts": getattr(self.tts, "backend", "?"),
            "asr": getattr(self.asr, "backend", "?"),
            "vision": getattr(self.vision, "backend", "?"),
            "weave": "on" if self.settings.enable_weave else "off",
        }
