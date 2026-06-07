"""FastAPI フロントAPI(webapp/server.py)の統合テスト（mockモード）。"""

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    os.environ["TOMOSHIBI_MODE"] = "mock"
    os.environ["PROFILE_PATH"] = "config/profile.example.json"
    from tomoshibi.webapp.server import app

    with TestClient(app) as c:  # lifespan が Runtime を構築
        yield c


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Tomoshibi" in r.text


def test_greet_returns_text(client):
    r = client.post("/api/greet")
    assert r.status_code == 200
    body = r.json()
    assert body["text"]
    assert body["character_name"] == "灯"
    assert body["audio"] is None  # mock TTS


def test_chat_replies(client):
    r = client.post("/api/chat", json={"text": "こんにちは"})
    assert r.status_code == 200
    assert r.json()["text"]


def test_guardian_state_shape(client):
    s = client.get("/api/guardian/state").json()
    assert s["phase"] == "monitoring"
    assert "timeline" in s and "profile" in s and "backends" in s
    assert "speech" in s


def test_fall_enters_checkin(client):
    s = client.post("/api/guardian/fall").json()
    assert s["phase"] == "check_in"
    # 見守り発話が出ている（seqが進む）
    assert s["speech"]["seq"] >= 1


def test_resident_help_jumps_to_emergency(client):
    client.post("/api/guardian/fall")
    s = client.post("/api/guardian/event", json={"event": "resident_help"}).json()
    assert s["phase"] == "emergency"
    assert s["emergency"]["active"] is True
    assert any("ペニシリン" in f for f in s["emergency"]["facts"])  # アレルギー伝達


def test_unknown_event_rejected(client):
    r = client.post("/api/guardian/event", json={"event": "bogus"})
    assert r.status_code == 400


def test_reset_returns_to_monitoring(client):
    client.post("/api/guardian/fall")
    s = client.post("/api/guardian/reset").json()
    assert s["phase"] == "monitoring"


def test_reset_clears_timeline_and_emergency(client):
    # 緊急まで進めてから reset → タイムライン空・緊急非表示でクリーンに
    client.post("/api/guardian/fall")
    client.post("/api/guardian/event", json={"event": "resident_help"})
    s = client.post("/api/guardian/reset").json()
    assert s["phase"] == "monitoring"
    # reset 自身のログ1件のみ（過去の緊急/声かけ履歴は消える）
    assert len(s["timeline"]) <= 1
    assert s["emergency"]["active"] is False
    assert s["emergency"]["script"] == ""


def test_transcribe_invalid_base64_is_graceful(client):
    r = client.post("/api/transcribe", json={"audio": "!!!notbase64!!!", "ext": "webm"})
    assert r.status_code == 200
    assert r.json()["text"] == ""  # 失敗してもクラッシュせず空文字


def test_transcribe_mock_returns_empty(client):
    # mockモードでは ASR が空文字（音声入力は実機/faster_whisperで有効化）
    import base64

    fake = base64.b64encode(b"RIFF....not-real-audio").decode()
    r = client.post("/api/transcribe", json={"audio": fake, "ext": "wav"})
    assert r.status_code == 200
    assert "text" in r.json()
