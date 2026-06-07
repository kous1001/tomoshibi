"""119引き継ぎ文生成(emergency/dispatch.py)と プロフィール検証のテスト。"""

from tomoshibi.emergency.dispatch import (
    build_dispatch_facts,
    compose_dispatch_script,
)
from tomoshibi.emergency.profile import parse_profile

SAMPLE = {
    "resident": {"name": "山田 花子", "age": 78, "sex": "女性", "address": "新宿区..."},
    "medical": {
        "conditions": ["高血圧", "糖尿病"],
        "medications": ["アムロジピン"],
        "allergies": ["ペニシリン"],
    },
    "emergency_contacts": [{"name": "山田 太郎", "relation": "長男", "phone": "090-..."}],
}


def test_facts_include_critical_medical_info():
    profile = parse_profile(SAMPLE)
    facts = build_dispatch_facts(profile, situation="転倒・応答なし")
    joined = "\n".join(facts)
    assert "山田 花子" in joined
    assert "78歳" in joined
    assert "ペニシリン" in joined  # アレルギーは救急で必須
    assert "新宿区" in joined


def test_template_fallback_without_llm():
    profile = parse_profile(SAMPLE)
    script, facts = compose_dispatch_script(profile, situation="転倒・応答なし", llm=None)
    assert "救急" in script
    assert len(facts) > 0


def test_llm_failure_falls_back_to_template():
    class BrokenLLM:
        def complete(self, system: str, user: str) -> str:
            raise RuntimeError("model down")

    profile = parse_profile(SAMPLE)
    script, _ = compose_dispatch_script(profile, situation="転倒", llm=BrokenLLM())
    assert "救急" in script  # 例外でも止まらずテンプレートで継続


def test_empty_profile_does_not_crash():
    profile = parse_profile({})
    facts = build_dispatch_facts(profile, situation="転倒")
    assert any("対象者" in f for f in facts)
