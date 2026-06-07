"""会話応答の長さ整形(companion/text.py)のユニットテスト。

高齢者向けに「1回の発話を短く」保つため、60字を超えたら文単位で丸める。
途中で切らない（聞き手が不自然に感じない）ことを担保する。
"""

from tomoshibi.companion.text import trim_reply


def test_short_reply_unchanged():
    text = "それは嬉しいですね。どんな花が咲いたんですか？"
    assert trim_reply(text) == text


def test_strips_surrounding_whitespace():
    assert trim_reply("  はい、元気ですよ。  ") == "はい、元気ですよ。"


def test_over_limit_trims_to_last_sentence_within_limit():
    # 1文目=句点で終わる11字。尾部を足して合計60字超にし、文単位で丸める。
    s1 = "今日はいい天気ですね。"  # 11字
    trimmed = trim_reply(s1 + "あ" * 60)
    assert trimmed == s1
    assert len(trimmed) <= 60


def test_no_punctuation_falls_back_to_hard_cut():
    text = "あ" * 100
    out = trim_reply(text)
    assert len(out) == 60
    assert out == "あ" * 60


def test_question_mark_counts_as_sentence_end():
    s1 = "最近はどんなご様子ですか？"  # ？で終わる13字
    assert trim_reply(s1 + "あ" * 60) == s1


def test_empty_returns_empty():
    assert trim_reply("") == ""
    assert trim_reply("   ") == ""


def test_custom_max_chars():
    assert trim_reply("はい。" + "ね" * 50, max_chars=3) == "はい。"
