"""ランタイム統合のスモークテスト（mockモードでE2E）。"""

import os
import time

import pytest

from tomoshibi.config import CHECKIN_TIMEOUT_S, FAMILY_ACK_TIMEOUT_S, Settings
from tomoshibi.guardian.fsm import EscalationState, Event, Phase
from tomoshibi.runtime import Runtime


@pytest.fixture()
def rt() -> Runtime:
    os.environ["TOMOSHIBI_MODE"] = "mock"
    os.environ["PROFILE_PATH"] = "config/profile.example.json"
    return Runtime.build(Settings.load())


def test_companion_replies_in_japanese(rt: Runtime):
    reply, wav = rt.companion_say("こんにちは")
    assert reply  # 何か返す
    assert wav is None  # mock TTS は音声を作らない
    assert len(rt.chat_history) == 1


def test_empty_message_is_ignored(rt: Runtime):
    reply, _ = rt.companion_say("   ")
    assert reply == ""
    assert rt.chat_history == []


def test_fall_to_emergency_full_path(rt: Runtime):
    rt.simulate_fall()
    assert rt.escalation.phase == Phase.CHECK_IN

    # 声かけタイムアウト → 家族通知
    rt.escalation = EscalationState(phase=Phase.CHECK_IN, since=time.time() - CHECKIN_TIMEOUT_S - 1)
    rt.tick()
    assert rt.escalation.phase == Phase.NOTIFY_FAMILY

    # 家族応答タイムアウト → 緊急
    rt.escalation = EscalationState(
        phase=Phase.NOTIFY_FAMILY, since=time.time() - FAMILY_ACK_TIMEOUT_S - 1
    )
    rt.tick()
    assert rt.escalation.phase == Phase.EMERGENCY
    assert "救急" in rt.last_emergency_script
    assert any("ペニシリン" in f for f in rt.last_emergency_facts)  # アレルギーが伝わる


def test_resident_ok_resolves(rt: Runtime):
    rt.simulate_fall()
    rt.feed_event(Event.RESIDENT_OK)
    assert rt.escalation.phase == Phase.RESOLVED


def test_backends_report_mock(rt: Runtime):
    b = rt.backends()
    assert b["llm"] == "mock"
    assert b["vision"] == "mock"
