"""システムプロンプト(persona.py)の構造テスト。

灯が「若い女の子」として固定され、プロフィールが「お相手のもの」として
明示されること（高齢者本人の生活を自分語りしない）を担保する。
"""

from tomoshibi.companion.persona import build_system_prompt
from tomoshibi.emergency.profile import Profile, Resident


def test_base_prompt_fixes_young_identity():
    prompt = build_system_prompt(None)
    assert "若い女の子" in prompt
    # プロフィールを渡さない場合はお相手情報の節は出ない
    assert "趣味・関心" not in prompt


def test_profile_section_framed_as_partner_and_includes_interests():
    profile = Profile(
        resident=Resident(name="山田 花子", name_kana="やまだ はなこ", age=78),
        interests=("演歌", "孫の話"),
    )
    prompt = build_system_prompt(profile)

    # 灯の身元が若いと明記される
    assert "若い女の子" in prompt
    # プロフィールが「お相手」のものだと明確化されている
    assert "お相手" in prompt
    # 自分の体験として語らない、という禁止が含まれる
    assert "一人称" in prompt
    # お相手の趣味（注入値）が含まれる
    assert "演歌" in prompt
    assert "孫の話" in prompt
    # お相手の名前も入る
    assert "山田 花子" in prompt
