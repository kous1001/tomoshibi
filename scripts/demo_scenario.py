"""ヘッドレスで全シナリオを通す検証/デモ録画用スクリプト。

    PYTHONPATH=src TOMOSHIBI_MODE=mock python scripts/demo_scenario.py

会話 → 転倒 → 無応答 → 家族通知 → 緊急(119読み上げ) までを順に流し、
タイムラインを標準出力に表示する。GUIなしでロジックを確認できる。
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

os.environ.setdefault("TOMOSHIBI_MODE", "mock")

from tomoshibi.config import CHECKIN_TIMEOUT_S, FAMILY_ACK_TIMEOUT_S, Settings  # noqa: E402
from tomoshibi.guardian.fsm import Phase  # noqa: E402
from tomoshibi.runtime import Runtime  # noqa: E402


def _print_timeline(rt: Runtime) -> None:
    print("\n--- タイムライン ---")
    for e in rt.timeline:
        ts = time.strftime("%H:%M:%S", time.localtime(e.t))
        print(f"[{ts}] ({e.kind}) {e.text}")
    print("-------------------\n")


def main() -> None:
    # プロフィール例を使う
    s = Settings.load()
    if not s.resolve(s.profile_path).exists():
        os.environ["PROFILE_PATH"] = "config/profile.example.json"
    rt = Runtime.build()
    print("backends:", rt.backends())

    print("\n# 1) 話し相手")
    for utter in ["こんにちは", "最近ちょっと寂しくてね", "膝が少し痛むのよ"]:
        reply, _ = rt.companion_say(utter)
        print(f"  本人: {utter}\n  灯  : {reply}")

    print("\n# 2) 転倒検知 → 確認")
    rt.report_fall_candidate(image=None)
    assert rt.escalation.phase == Phase.CHECK_IN, rt.escalation.phase

    print("\n# 3) 本人の応答なし → 家族通知へ自動遷移")
    # 時間を進めずに閾値超えをシミュレートするため since を巻き戻す
    rt.escalation = rt.escalation.__class__(
        phase=rt.escalation.phase, since=time.time() - CHECKIN_TIMEOUT_S - 1, reason=""
    )
    rt.tick()
    assert rt.escalation.phase == Phase.NOTIFY_FAMILY, rt.escalation.phase

    print("\n# 4) 家族も応答なし → 緊急(119読み上げ)へ")
    rt.escalation = rt.escalation.__class__(
        phase=rt.escalation.phase, since=time.time() - FAMILY_ACK_TIMEOUT_S - 1, reason=""
    )
    rt.tick()
    assert rt.escalation.phase == Phase.EMERGENCY, rt.escalation.phase

    print("\n# 5) 生成された119読み上げ原稿")
    print(" ", rt.last_emergency_script)

    _print_timeline(rt)
    print("✅ シナリオ完走")


if __name__ == "__main__":
    main()
