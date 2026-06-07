"""家族通知 — 唯一の外部送信点。

channel: mock | webhook | line_notify。
mock はネットワークに出ず、戻り値で配信内容を返す（デモ・オフライン実演用）。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from .profile import Profile


@dataclass(frozen=True)
class NotifyResult:
    ok: bool
    channel: str
    recipients: tuple[str, ...]
    detail: str


def _format_message(profile: Profile, message: str, snapshot_note: str) -> str:
    r = profile.resident
    lines = [
        "【灯(Tomoshibi)見守り通知】",
        f"{r.name} さんの様子に異変の可能性があります。",
        message,
    ]
    if snapshot_note:
        lines.append(snapshot_note)
    if r.address:
        lines.append(f"所在: {r.address}")
    return "\n".join(lines)


def notify_family(
    settings: Settings,
    profile: Profile,
    message: str,
    *,
    snapshot_note: str = "",
) -> NotifyResult:
    """家族へ通知する。例外は投げず NotifyResult で結果を返す。"""
    text = _format_message(profile, message, snapshot_note)
    recipients = tuple(f"{c.name}({c.relation})" for c in profile.emergency_contacts) or ("家族",)
    channel = settings.family_notify_channel

    if channel == "mock":
        return NotifyResult(True, "mock", recipients, text)

    try:
        import requests  # 遅延import（mock時は不要）

        if channel == "line_notify" and settings.line_notify_token:
            resp = requests.post(
                "https://notify-api.line.me/api/notify",
                headers={"Authorization": f"Bearer {settings.line_notify_token}"},
                data={"message": text},
                timeout=5,
            )
            return NotifyResult(resp.ok, channel, recipients, f"HTTP {resp.status_code}")

        if channel == "webhook" and settings.family_webhook_url:
            resp = requests.post(
                settings.family_webhook_url,
                json={"text": text, "recipients": list(recipients)},
                timeout=5,
            )
            return NotifyResult(resp.ok, channel, recipients, f"HTTP {resp.status_code}")

        return NotifyResult(False, channel, recipients, "未設定のため送信せず（mock相当）")
    except Exception as e:  # ネットワーク失敗でデモを止めない
        return NotifyResult(False, channel, recipients, f"送信失敗: {e}")
