"""ランタイム状態を JSON（フロント向け）へ変換する純粋関数群。

フロントの guardian.js がこの形を描画する。表示ロジックは ui_render.py と重複させず、
ここに一元化する（HTMLフロントはMarkdownでなくJSONを受け取るため別実装が必要）。
"""

from __future__ import annotations

import time

from ..guardian.fsm import Phase
from ..runtime import Runtime, TimelineEntry

# フェーズ → (アイコン, ラベル, 説明, 配色キー)
_PHASE = {
    Phase.MONITORING: ("🟢", "見守り中", "平常。会話を楽しめます。", "ok"),
    Phase.CHECK_IN: ("🟡", "声かけ中 (S1)", "転倒の可能性。ご本人に呼びかけています。", "warn"),
    Phase.NOTIFY_FAMILY: ("🟠", "家族へ通知 (S2)", "応答なし。ご家族へ連絡しました。", "alert"),
    Phase.EMERGENCY: ("🔴", "緊急対応 (S3)", "救急へ引き継ぎ中（シミュレーション）。", "danger"),
    Phase.RESOLVED: ("✅", "解決", "対応が完了しました。", "ok"),
}

_KIND_ICON = {"log": "•", "chat": "💬", "speak": "🗣️", "notify": "📣", "emergency": "🚑"}


def _timeline(entries: list[TimelineEntry], limit: int = 14) -> list[dict]:
    out = []
    for e in entries[-limit:][::-1]:
        out.append(
            {
                "time": time.strftime("%H:%M:%S", time.localtime(e.t)),
                "kind": e.kind,
                "icon": _KIND_ICON.get(e.kind, "•"),
                "text": e.text,
            }
        )
    return out


def guardian_state(rt: Runtime, camera: dict | None = None) -> dict:
    """見守りパネル全体の状態を1つのJSONにまとめる。

    camera: {"running": bool, "error": str} （サーバが CameraMonitor から渡す）。
    """
    icon, label, desc, tone = _PHASE.get(rt.escalation.phase, ("⚪", "不明", "", "ok"))
    r = rt.profile.resident
    m = rt.profile.medical
    return {
        "phase": rt.escalation.phase.value,
        "phase_icon": icon,
        "phase_label": label,
        "phase_desc": desc,
        "tone": tone,
        "timeline": _timeline(rt.timeline),
        "emergency": {
            "active": rt.escalation.phase == Phase.EMERGENCY,
            "script": rt.last_emergency_script,
            "facts": list(rt.last_emergency_facts),
        },
        "profile": {
            "name": r.name,
            "age": r.age,
            "sex": r.sex,
            "address": r.address,
            "conditions": list(m.conditions),
            "medications": list(m.medications),
            "allergies": list(m.allergies),
        },
        "backends": rt.backends(),
        # 見守りが発話した最新の1件（フロントが seq 変化時に再生＋吹き出し表示）
        "speech": {
            "seq": rt.speech_seq,
            "text": rt.last_speech_text,
            "audio": rt.last_speech_audio_b64,
        },
        "camera": camera or {"running": False, "error": ""},
    }
