"""W&B Weave トレースの薄いラッパ。

Weave 無効/未インストールでも完全に動く no-op デコレータを提供する。
有効時は対話ターンやエスカレーション判断が Weave のトレースに記録され、
スポンサー(W&B)向けの観測性デモになる。
"""

from __future__ import annotations

import functools
from typing import Callable

_ENABLED = False


def init(project: str, enabled: bool) -> bool:
    """Weave を初期化。成功で True。失敗/無効では no-op のまま False。"""
    global _ENABLED
    if not enabled:
        return False
    try:
        import weave

        weave.init(project)
        _ENABLED = True
    except Exception:
        _ENABLED = False
    return _ENABLED


def op(name: str) -> Callable:
    """関数を Weave op として記録するデコレータ（無効時は素通し）。"""

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        if _ENABLED:
            try:
                import weave

                return weave.op(name=name)(fn)
            except Exception:
                return wrapper
        return wrapper

    return deco
