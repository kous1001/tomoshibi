"""エスカレーションFSM(guardian/fsm.py)のユニットテスト。"""

from tomoshibi.config import CHECKIN_TIMEOUT_S, FAMILY_ACK_TIMEOUT_S
from tomoshibi.guardian.fsm import (
    ActionKind,
    EscalationState,
    Event,
    Phase,
    transition,
)


def test_fall_confirmed_enters_checkin_and_speaks():
    s0 = EscalationState()
    s1, actions = transition(s0, Event.FALL_CONFIRMED, now=0.0)
    assert s1.phase == Phase.CHECK_IN
    assert any(a.kind == ActionKind.SPEAK for a in actions)


def test_resident_ok_resolves_from_checkin():
    s = EscalationState(phase=Phase.CHECK_IN, since=0.0)
    s2, _ = transition(s, Event.RESIDENT_OK, now=2.0)
    assert s2.phase == Phase.RESOLVED


def test_checkin_timeout_notifies_family():
    s = EscalationState(phase=Phase.CHECK_IN, since=0.0)
    # タイムアウト未満では遷移しない
    s_same, _ = transition(s, Event.TICK, now=CHECKIN_TIMEOUT_S - 1)
    assert s_same.phase == Phase.CHECK_IN
    # タイムアウト到達で家族通知へ
    s2, actions = transition(s, Event.TICK, now=CHECKIN_TIMEOUT_S + 0.1)
    assert s2.phase == Phase.NOTIFY_FAMILY
    assert any(a.kind == ActionKind.NOTIFY_FAMILY for a in actions)


def test_resident_help_jumps_to_emergency():
    s = EscalationState(phase=Phase.CHECK_IN, since=0.0)
    s2, actions = transition(s, Event.RESIDENT_HELP, now=1.0)
    assert s2.phase == Phase.EMERGENCY
    assert any(a.kind == ActionKind.ANNOUNCE_EMERGENCY for a in actions)


def test_family_timeout_escalates_to_emergency():
    s = EscalationState(phase=Phase.NOTIFY_FAMILY, since=0.0)
    s2, actions = transition(s, Event.TICK, now=FAMILY_ACK_TIMEOUT_S + 0.1)
    assert s2.phase == Phase.EMERGENCY
    assert any(a.kind == ActionKind.ANNOUNCE_EMERGENCY for a in actions)


def test_family_ack_resolves():
    s = EscalationState(phase=Phase.NOTIFY_FAMILY, since=0.0)
    s2, _ = transition(s, Event.FAMILY_ACK, now=5.0)
    assert s2.phase == Phase.RESOLVED


def test_cancel_returns_to_monitoring():
    s = EscalationState(phase=Phase.NOTIFY_FAMILY, since=0.0)
    s2, _ = transition(s, Event.CANCEL, now=5.0)
    assert s2.phase == Phase.MONITORING


def test_emergency_is_terminal_on_tick():
    s = EscalationState(phase=Phase.EMERGENCY, since=0.0)
    s2, actions = transition(s, Event.TICK, now=999.0)
    assert s2.phase == Phase.EMERGENCY
    assert actions == []


def test_full_no_response_path():
    """転倒 → 無応答 → 家族無応答 → 緊急、の通し経路。"""
    s = EscalationState()
    s, _ = transition(s, Event.FALL_CONFIRMED, now=0.0)
    assert s.phase == Phase.CHECK_IN
    s, _ = transition(s, Event.TICK, now=CHECKIN_TIMEOUT_S + 0.1)
    assert s.phase == Phase.NOTIFY_FAMILY
    t2 = s.since + FAMILY_ACK_TIMEOUT_S + 0.1
    s, actions = transition(s, Event.TICK, now=t2)
    assert s.phase == Phase.EMERGENCY
    assert any(a.kind == ActionKind.ANNOUNCE_EMERGENCY for a in actions)
