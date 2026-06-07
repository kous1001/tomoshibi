"""UI表示用の純粋レンダリング関数（Gradio非依存・テスト可能）。"""

from __future__ import annotations

import time

from .guardian.fsm import Phase
from .runtime import Runtime, TimelineEntry

_PHASE_BADGE = {
    Phase.MONITORING: ("🟢", "見守り中", "平常。会話を楽しめます。"),
    Phase.CHECK_IN: ("🟡", "声かけ中 (S1)", "転倒の可能性。ご本人に呼びかけています。"),
    Phase.NOTIFY_FAMILY: ("🟠", "家族へ通知 (S2)", "応答なし。ご家族へ連絡しました。"),
    Phase.EMERGENCY: ("🔴", "緊急対応 (S3)", "救急へ引き継ぎ中（シミュレーション）。"),
    Phase.RESOLVED: ("✅", "解決", "対応が完了しました。"),
}

_KIND_ICON = {
    "log": "•",
    "chat": "💬",
    "speak": "🗣️",
    "notify": "📣",
    "emergency": "🚑",
}


def status_md(rt: Runtime) -> str:
    icon, label, desc = _PHASE_BADGE.get(rt.escalation.phase, ("⚪", "不明", ""))
    b = rt.backends()
    backends = " / ".join(f"{k}:`{v}`" for k, v in b.items())
    return (
        f"## {icon} {label}\n"
        f"{desc}\n\n"
        f"<small>backends — {backends}</small>"
    )


def timeline_md(entries: list[TimelineEntry], limit: int = 12) -> str:
    if not entries:
        return "_まだ記録はありません。_"
    rows = []
    for e in entries[-limit:][::-1]:
        ts = time.strftime("%H:%M:%S", time.localtime(e.t))
        icon = _KIND_ICON.get(e.kind, "•")
        rows.append(f"{icon} `{ts}` {e.text}")
    return "\n\n".join(rows)


def emergency_md(rt: Runtime) -> str:
    if rt.escalation.phase != Phase.EMERGENCY or not rt.last_emergency_script:
        return ""
    facts = "\n".join(f"- {f}" for f in rt.last_emergency_facts)
    return (
        "### 🚑 119 読み上げ原稿（シミュレーション）\n"
        f"> {rt.last_emergency_script}\n\n"
        "#### 伝達した事実（端末ローカルのみ）\n"
        f"{facts}"
    )


def profile_card_md(rt: Runtime) -> str:
    r = rt.profile.resident
    m = rt.profile.medical
    age = f"{r.age}歳" if r.age is not None else "—"
    return (
        f"**{r.name}** さん（{age}・{r.sex or '—'}）\n\n"
        f"📍 {r.address or '—'}\n\n"
        f"🩺 持病: {'、'.join(m.conditions) or '—'}\n\n"
        f"💊 服薬: {'、'.join(m.medications) or '—'}\n\n"
        f"⚠️ アレルギー: {'、'.join(m.allergies) or '—'}\n\n"
        f"<small>※ この情報は端末内に保存され、外部送信されません。</small>"
    )
