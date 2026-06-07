"""転倒ヒューリスティック(guardian/pose.py)のユニットテスト。

セマンティクス: 「立位→水平の転倒を検知 → confirm_s 秒以内に起き上がらなければ確定」。
床で検出が途切れても（present=False）確定できることを重視する。
"""

from tomoshibi.guardian.pose import FallDetectorState, PoseSample, update

CONFIRM_S = 3.0  # stillness_s = 起き上がらなければ確定するまでの秒数


def _feed(samples: list[PoseSample]) -> bool:
    state = FallDetectorState()
    fired_any = False
    for s in samples:
        state, fired = update(state, s, stillness_s=CONFIRM_S)
        fired_any = fired_any or fired
    return fired_any


def _upright(t):
    return PoseSample(t=t, torso_angle_deg=5.0, centroid_y=0.40, confidence=0.9)


def _fallen(t):
    return PoseSample(t=t, torso_angle_deg=80.0, centroid_y=0.80, confidence=0.9)


def _absent(t):
    return PoseSample(t=t, torso_angle_deg=0.0, centroid_y=0.0, confidence=0.0,
                      person_present=False)


def test_standing_person_never_triggers():
    assert _feed([_upright(float(i)) for i in range(8)]) is False


def test_fall_then_stay_down_confirms_after_3s():
    # 立位→転倒(0.5s)→そのまま床。confirm 3s 経過で確定。
    samples = [_upright(0.0)] + [_fallen(t) for t in (0.5, 1.0, 2.0, 3.0, 3.6)]
    assert _feed(samples) is True


def test_recovery_before_3s_cancels():
    # 転倒検知後、3s以内に起き上がったら取消（ただの座り込み/しゃがみ）
    samples = [_upright(0.0), _fallen(0.5), _fallen(1.5), _upright(2.0), _upright(3.0)]
    assert _feed(samples) is False


def test_detection_dropout_during_down_still_confirms():
    # 転倒後、床で人物を見失っても（present=False）「起き上がっていない」ので確定する（頑健性）
    samples = [_upright(0.0), _fallen(0.5), _absent(1.5), _absent(2.5), _absent(3.6)]
    assert _feed(samples) is True


def test_already_on_floor_without_fall_event_does_not_fire():
    # 監視開始時すでに床（立位の前歴なし）→ 転倒の遷移が無いので発火しない
    samples = [_fallen(float(i)) for i in range(8)]
    assert _feed(samples) is False


def test_low_confidence_frames_ignored():
    samples = [
        PoseSample(t=float(i), torso_angle_deg=80.0, centroid_y=0.8, confidence=0.1)
        for i in range(8)
    ]
    assert _feed(samples) is False


def test_candidate_fires_only_once():
    samples = [_upright(0.0)] + [_fallen(float(t)) for t in range(1, 12)]
    state = FallDetectorState()
    count = 0
    for s in samples:
        state, fired = update(state, s, stillness_s=CONFIRM_S)
        count += int(fired)
    assert count == 1


# --- 俯瞰(overhead)カメラ: 角度/重心でなく胴体長(=見かけの大きさ≒距離)で判定 ---
# 高所カメラ実測: 立位=頭が近く大きく写る(len大), 転倒=床に倒れ遠く小さく写る(len小)。
# 角度や重心は無意味な値でも判定に影響しない。

def _feed_oh(samples: list[PoseSample]) -> bool:
    state = FallDetectorState()
    fired_any = False
    for s in samples:
        state, fired = update(state, s, stillness_s=CONFIRM_S, view="overhead")
        fired_any = fired_any or fired
    return fired_any


def _upright_oh(t):
    # 立位: 胴体が大きく写る（カメラに近い）。実測 len≈0.77。
    return PoseSample(t=t, torso_angle_deg=0.0, centroid_y=1.0, confidence=0.9, torso_length=0.70)


def _fallen_oh(t):
    # 転倒: 胴体が小さく写る（床に倒れて遠い）。実測 len≈0.28。
    return PoseSample(t=t, torso_angle_deg=0.0, centroid_y=0.3, confidence=0.9, torso_length=0.25)


def _absent_oh(t):
    return PoseSample(t=t, torso_angle_deg=0.0, centroid_y=0.0, confidence=0.0,
                      person_present=False, torso_length=0.0)


def test_overhead_standing_never_triggers():
    assert _feed_oh([_upright_oh(float(i)) for i in range(8)]) is False


def test_overhead_fall_then_stay_down_confirms_after_3s():
    samples = [_upright_oh(0.0)] + [_fallen_oh(t) for t in (0.5, 1.0, 2.0, 3.0, 3.6)]
    assert _feed_oh(samples) is True


def test_overhead_recovery_before_3s_cancels():
    samples = [_upright_oh(0.0), _fallen_oh(0.5), _fallen_oh(1.5),
               _upright_oh(2.0), _upright_oh(3.0)]
    assert _feed_oh(samples) is False


def test_overhead_dropout_during_down_still_confirms():
    samples = [_upright_oh(0.0), _fallen_oh(0.5), _absent_oh(1.5),
               _absent_oh(2.5), _absent_oh(3.6)]
    assert _feed_oh(samples) is True


def test_overhead_already_down_without_fall_event_does_not_fire():
    # 監視開始時すでに床（小さく写る・立位の前歴なし）→ 遷移が無いので発火しない
    samples = [_fallen_oh(float(i)) for i in range(8)]
    assert _feed_oh(samples) is False
