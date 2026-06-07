"""読み上げ用の日本語テキスト整形（プロジェクト内製・純粋関数）。

VOICEVOX(OpenJTalk)が読み誤りやすい点を吸収し、抑揚・間を自然にする。
画面表示は変えず、TTSへ渡す直前の文字列だけを整える。
"""

from __future__ import annotations

import re

# ふりがな注釈「漢字（かな）」は、かな側だけ読む（注釈は読み上げない）。
# 例: 「灯（あかり）」→「あかり」、「山田 花子（やまだ はなこ）」→「やまだ はなこ」。
# 漢字側・かな側とも姓名間のスペースを許容。かなを含む括弧だけが対象で、
# 「難聴（右耳）」のような漢字内容の括弧は意味があるので残す。
_FURIGANA_RE = re.compile(r"[一-龥々〆ヶ 　]+（([ぁ-んァ-ンヴーゝゞ々・ 　]+)）")

# 伸ばし記号のゆれを長音符「ー」に統一。直前がかな/長音/同種記号のときだけ変換し、
# 数字やラテン間のハイフン（10-20, Wi-Fi）は変えない。
_ELONG_PREV = "ぁ-んァ-ヶーｰ~～〜―‐‑—–−\\-"
_ELONG_RE = re.compile(f"(?<=[{_ELONG_PREV}])[~～〜―‐‑—–−\\-]")

# OpenJTalk が読み誤りやすい語の「音声用」読み置換（画面表示は変えない）。必要に応じて追記。
_READING_FIXES = {
    "宝物": "たからもの",
    "灯": "あかり",  # キャラ名「灯」を「ともしび/ひ」でなく「あかり」と読ませる
}

_END_PUNCT = "。．.！!？?…"  # 文末がこれなら句点を足さない


def _ensure_end_punct(t: str) -> str:
    t = t.rstrip()
    if not t:
        return t
    if t[-1] in "、,":  # 文末の読点は句点に直す
        return t[:-1] + "。"
    if t[-1] not in _END_PUNCT:
        return t + "。"
    return t


def normalize_for_tts(text: str) -> str:
    """読み上げ用に整形する（ふりがな除去・読み誤り置換・伸ばし記号統一・文末句点）。"""
    t = text or ""
    t = _FURIGANA_RE.sub(r"\1", t)  # ①ふりがな注釈はかなだけ残す（読み置換より先）
    for surface, yomi in _READING_FIXES.items():  # ②注釈なしの単独漢字の読み補正
        t = t.replace(surface, yomi)
    t = _ELONG_RE.sub("ー", t)
    t = _ensure_end_punct(t)
    return t
