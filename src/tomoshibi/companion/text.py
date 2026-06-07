"""会話応答のテキスト整形。

高齢者向けに「1回の発話を短く」保つための後処理。
LFM2 がたまに長文を返しても、文単位で丸めて聞き手の負担を抑える。
（読み上げ用の整形は voice/jp_text.py が担当。役割を混ぜない。）
"""

from __future__ import annotations

from ..config import COMPANION_MAX_CHARS

# 文末とみなす句読点（全角・半角）。これらの直後で文を区切れる。
_SENTENCE_ENDS = frozenset("。！？!?")


def trim_reply(text: str, max_chars: int = COMPANION_MAX_CHARS) -> str:
    """応答を max_chars 以内に整える（不変・副作用なし）。

    - 前後の空白を除いた長さが max_chars 以内ならそのまま返す。
    - 超える場合は、max_chars 以内に収まる最後の文末記号までで丸める。
    - 文末記号が無ければ max_chars で切る（フォールバック）。
    """
    if not text:
        return ""
    stripped = text.strip()
    if len(stripped) <= max_chars:
        return stripped

    window = stripped[:max_chars]
    cut = max((window.rfind(end) for end in _SENTENCE_ENDS), default=-1)
    if cut >= 0:
        return window[: cut + 1]
    return window
