"""エスカレーション状態機械（純粋・不変）。

転倒確定後の段階的対応を司る安全機能の心臓部:

  MONITORING ──fall_confirmed──▶ CHECK_IN(S1)
  CHECK_IN ──resident_ok──▶ RESOLVED
  CHECK_IN ──resident_help──▶ EMERGENCY
  CHECK_IN ──timeout(15s)──▶ NOTIFY_FAMILY(S2)
  NOTIFY_FAMILY ──resident_ok / family_ack──▶ RESOLVED
  NOTIFY_FAMILY ──resident_help / timeout(30s)──▶ EMERGENCY(S3)

副作用は持たない。`transition` は (新状態, [Action...]) を返し、
実際の発話/通知/119文生成はアプリ側(executor)が実行する。
これにより FSM 単体をテスト可能に保つ。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..config import CHECKIN_TIMEOUT_S, FAMILY_ACK_TIMEOUT_S


class Phase(str, Enum):
    MONITORING = "monitoring"
    CHECK_IN = "check_in"  # S1: 本人へ声かけ
    NOTIFY_FAMILY = "notify_family"  # S2: 家族へ通知
    EMERGENCY = "emergency"  # S3: 救急シミュレーション
    RESOLVED = "resolved"  # 解決(本人無事/家族対応)


class Event(str, Enum):
    FALL_CONFIRMED = "fall_confirmed"  # LFM2-VL が転倒を確認
    RESIDENT_OK = "resident_ok"  # 本人が「大丈夫」/ 起立
    RESIDENT_HELP = "resident_help"  # 本人が「助けて」
    FAMILY_ACK = "family_ack"  # 家族が対応を引き受けた
    TICK = "tick"  # 定期チェック（タイムアウト評価）
    CANCEL = "cancel"  # 手動取消（誤検知）


class ActionKind(str, Enum):
    SPEAK = "speak"  # 本人へ発話(TTS)
    NOTIFY_FAMILY = "notify_family"  # 家族へ通知
    ANNOUNCE_EMERGENCY = "announce_emergency"  # 119文生成＋読み上げ
    LOG = "log"  # タイムラインへ記録


@dataclass(frozen=True)
class Action:
    kind: ActionKind
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EscalationState:
    phase: Phase = Phase.MONITORING
    since: float = 0.0  # 現フェーズに入った時刻
    reason: str = ""  # 解決/緊急の理由（タイムラインに残す）


def _enter(phase: Phase, now: float, reason: str = "") -> EscalationState:
    return EscalationState(phase=phase, since=now, reason=reason)


def _checkin_actions() -> list[Action]:
    return [
        Action(ActionKind.LOG, "転倒の可能性を検知しました"),
        Action(
            ActionKind.SPEAK,
            "もしもし、大丈夫ですか？ 聞こえたら「大丈夫」と教えてください。"
            "助けが必要なときは「助けて」と言ってくださいね。",
            {"expect_response": True},
        ),
    ]


def _notify_actions() -> list[Action]:
    return [
        Action(ActionKind.LOG, "応答がありません。ご家族へ通知します"),
        Action(ActionKind.NOTIFY_FAMILY, "ご本人からの応答がありません。様子をご確認ください。"),
        Action(
            ActionKind.SPEAK,
            "ご家族に連絡しました。もう少しだけ待っていてくださいね。",
        ),
    ]


def _emergency_actions(reason: str) -> list[Action]:
    return [
        Action(ActionKind.LOG, f"緊急対応に移行します（{reason}）"),
        Action(
            ActionKind.SPEAK,
            "今から救急に連絡します。動かずに待っていてください。すぐ助けが来ますからね。",
        ),
        Action(ActionKind.ANNOUNCE_EMERGENCY, "", {"reason": reason}),
    ]


def transition(
    state: EscalationState, event: Event, now: float
) -> tuple[EscalationState, list[Action]]:
    """状態遷移（純粋）。新状態と実行すべきActionリストを返す。"""

    # 取消はどのフェーズからでも監視へ戻す
    if event == Event.CANCEL:
        if state.phase in (Phase.CHECK_IN, Phase.NOTIFY_FAMILY):
            return _enter(Phase.MONITORING, now), [Action(ActionKind.LOG, "誤検知として取消しました")]
        return state, []

    if state.phase == Phase.MONITORING:
        if event == Event.FALL_CONFIRMED:
            return _enter(Phase.CHECK_IN, now), _checkin_actions()
        return state, []

    if state.phase == Phase.CHECK_IN:
        if event == Event.RESIDENT_OK:
            return _enter(Phase.RESOLVED, now, "本人が無事を確認"), [
                Action(ActionKind.LOG, "本人の無事を確認しました"),
                Action(ActionKind.SPEAK, "よかった、安心しました。無理せずゆっくりしてくださいね。"),
            ]
        if event == Event.RESIDENT_HELP:
            return _enter(Phase.EMERGENCY, now, "本人が助けを要請"), _emergency_actions("本人が助けを要請")
        if event == Event.TICK and (now - state.since) >= CHECKIN_TIMEOUT_S:
            return _enter(Phase.NOTIFY_FAMILY, now), _notify_actions()
        return state, []

    if state.phase == Phase.NOTIFY_FAMILY:
        if event in (Event.RESIDENT_OK, Event.FAMILY_ACK):
            reason = "本人が無事を確認" if event == Event.RESIDENT_OK else "家族が対応"
            return _enter(Phase.RESOLVED, now, reason), [Action(ActionKind.LOG, f"解決: {reason}")]
        if event == Event.RESIDENT_HELP:
            return _enter(Phase.EMERGENCY, now, "本人が助けを要請"), _emergency_actions("本人が助けを要請")
        if event == Event.TICK and (now - state.since) >= FAMILY_ACK_TIMEOUT_S:
            return _enter(Phase.EMERGENCY, now, "家族応答なし"), _emergency_actions("家族応答なし")
        return state, []

    # EMERGENCY / RESOLVED は終端（TICKでは動かない）
    return state, []
