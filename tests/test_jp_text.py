"""読み上げ整形(voice/jp_text.py)のユニットテスト。"""

from tomoshibi.voice.jp_text import normalize_for_tts


def test_adds_end_punctuation():
    assert normalize_for_tts("今日はいい天気ですね").endswith("。")


def test_trailing_comma_becomes_period():
    assert normalize_for_tts("そうですね、").endswith("。")
    assert "、。" not in normalize_for_tts("そうですね、")


def test_keeps_existing_end_punct():
    assert normalize_for_tts("元気ですか？") == "元気ですか？"


def test_elongation_marks_unified_after_kana():
    # かなの直後の波ダッシュ等は長音符に統一
    assert "よーく" in normalize_for_tts("よ～く")


def test_hyphen_between_numbers_preserved():
    # 数字間のハイフンは変換しない（長音にしない）
    out = normalize_for_tts("10-20分")
    assert "10-20" in out


def test_reading_fix_for_character_name():
    # 「灯」は「あかり」と読ませる
    assert "あかり" in normalize_for_tts("灯です")


def test_furigana_annotation_not_doubled():
    # 「灯（あかり）です」は「あかりです。」（注釈を読み上げて二重にしない）
    out = normalize_for_tts("灯（あかり）です")
    assert out == "あかりです。"
    assert "（" not in out and out.count("あかり") == 1


def test_furigana_strip_uses_kana_reading():
    out = normalize_for_tts("山田 花子（やまだ はなこ）さん")
    assert "やまだ はなこ" in out
    assert "山田" not in out  # 漢字側は読まない


def test_kanji_paren_content_is_kept():
    # 漢字内容の括弧（ふりがなでない注釈）は残す
    out = normalize_for_tts("軽度の難聴（右耳）")
    assert "（右耳）" in out


def test_empty_is_safe():
    assert normalize_for_tts("") == ""
    assert normalize_for_tts(None) == ""  # type: ignore[arg-type]
