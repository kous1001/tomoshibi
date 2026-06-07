"""119救急への引き継ぎ文を生成する。

二層構成:
1. `build_dispatch_facts` … プロフィールから決定論的に「事実の箇条書き」を作る（PIIはローカルのみ）。
2. `compose_dispatch_script` … 事実をローカルLFM2で自然な読み上げ口調に整形（任意）。
   LLM が無い/失敗した場合は決定論的テンプレートにフォールバック（デモを止めない）。

外部LLMにPIIを渡さない設計（生成は必ずローカルモデル）。
"""

from __future__ import annotations

from typing import Optional, Protocol

from ..config import DISPATCH_MAX_TOKENS
from .profile import Profile


class LocalLLM(Protocol):
    def complete(self, system: str, user: str, max_tokens: int | None = None) -> str: ...


def build_dispatch_facts(profile: Profile, *, situation: str) -> list[str]:
    """救急に伝えるべき事実を順序立てて並べる（決定論的）。"""
    r = profile.resident
    m = profile.medical
    facts: list[str] = []

    facts.append(f"通報内容: {situation}")
    who = r.name + (f"（{r.name_kana}）" if r.name_kana else "")
    age = f"{r.age}歳" if r.age is not None else "年齢不明"
    facts.append(f"対象者: {who}、{age}、{r.sex or '性別不明'}")
    if r.address:
        facts.append(f"住所: {r.address}")
    if r.phone:
        facts.append(f"電話: {r.phone}")
    if m.conditions:
        facts.append(f"持病: {'、'.join(m.conditions)}")
    if m.medications:
        facts.append(f"服薬: {'、'.join(m.medications)}")
    if m.allergies:
        facts.append(f"アレルギー: {'、'.join(m.allergies)}")
    if m.blood_type:
        facts.append(f"血液型: {m.blood_type}")
    if m.mobility:
        facts.append(f"歩行: {m.mobility}")
    if m.primary_doctor:
        facts.append(f"かかりつけ: {m.primary_doctor}")
    if profile.emergency_contacts:
        c = profile.emergency_contacts[0]
        facts.append(f"緊急連絡先: {c.name}（{c.relation}）{c.phone}")
    return facts


def _template_script(facts: list[str]) -> str:
    """LLM不要の安全な読み上げ文（フォールバック）。"""
    body = "。".join(facts)
    return (
        "救急です。一人暮らしの高齢者宅で転倒が検知され、ご本人からの応答がありません。"
        f"{body}。至急の救助をお願いします。"
    )


DISPATCH_SYSTEM = (
    "あなたは救急通報を補助するAIです。与えられた事実だけを使い、"
    "119番の通信指令員に落ち着いて伝える短い読み上げ原稿を作成してください。"
    "事実を創作・脚色しないこと。最重要情報（場所・容体・本人特定・持病/薬/アレルギー）を先に。"
    "30秒以内で読める長さ、敬体、箇条書きにせず自然な話し言葉で。"
)


def compose_dispatch_script(
    profile: Profile,
    *,
    situation: str,
    llm: Optional[LocalLLM] = None,
) -> tuple[str, list[str]]:
    """(読み上げ原稿, 事実リスト) を返す。llm 未指定/失敗時はテンプレートへ。"""
    facts = build_dispatch_facts(profile, situation=situation)
    if llm is None:
        return _template_script(facts), facts
    try:
        user = "次の事実から救急通報の読み上げ原稿を作成してください:\n- " + "\n- ".join(facts)
        script = llm.complete(DISPATCH_SYSTEM, user, max_tokens=DISPATCH_MAX_TOKENS).strip()
        if not script:  # 空応答は信頼しない
            return _template_script(facts), facts
        return script, facts
    except Exception:
        # 緊急時に例外でデモを止めない。必ずテンプレートで継続。
        return _template_script(facts), facts
