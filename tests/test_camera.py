"""カメラ姿勢変換(guardian/camera.py landmarks_to_sample)のユニットテスト。

cv2/mediapipe 不要の純関数のみを検証する。
"""

from collections import namedtuple

from tomoshibi.guardian.camera import landmarks_to_sample, pose_debug_features

LM = namedtuple("LM", ["x", "y", "visibility"])


def _make(points: dict, n: int = 33, vis: float = 0.9):
    """index→(x,y) の辞書から 33点のランドマーク列を作る（未指定は中央・低可視性）。"""
    out = []
    for i in range(n):
        if i in points:
            x, y = points[i]
            out.append(LM(x, y, vis))
        else:
            out.append(LM(0.5, 0.5, vis))
    return out


# 肩=11,12 / 腰=23,24
def _standing():
    return _make({11: (0.45, 0.30), 12: (0.55, 0.30), 23: (0.47, 0.60), 24: (0.53, 0.60)})


def _lying():
    # 体が水平: 肩と腰が同じ高さ(y)、左右(x)に離れる
    return _make({11: (0.30, 0.78), 12: (0.30, 0.82), 23: (0.70, 0.78), 24: (0.70, 0.82)})


def test_standing_is_upright():
    s = landmarks_to_sample(_standing(), t=1.0)
    assert s.person_present is True
    assert s.torso_angle_deg < 20  # ほぼ直立
    assert s.centroid_y < 0.6


def test_lying_is_horizontal():
    s = landmarks_to_sample(_lying(), t=2.0)
    assert s.person_present is True
    assert s.torso_angle_deg > 70  # ほぼ水平
    assert s.centroid_y > 0.6  # フレーム下方（低い位置）


def test_low_visibility_means_no_person():
    s = landmarks_to_sample(_make({11: (0.4, 0.3)}, vis=0.1), t=3.0)
    assert s.person_present is False


def test_none_landmarks_is_safe():
    s = landmarks_to_sample(None, t=4.0)
    assert s.person_present is False
    assert s.confidence == 0.0


# --- 俯瞰校正用デバッグ特徴量 ---

def test_debug_features_none_landmarks_returns_none():
    assert pose_debug_features(None) is None


def test_debug_features_standing_keys_and_values():
    f = pose_debug_features(_standing())
    assert f is not None
    # 期待キーが揃う
    assert set(f) == {"len", "ar", "bw", "bh", "sw", "cy", "a"}
    # 肩幅(11,12 が x=0.45/0.55)= 0.10、胴体長(肩中点y0.30→腰中点y0.60)≈0.30
    assert abs(f["sw"] - 0.10) < 1e-6
    assert abs(f["len"] - 0.30) < 1e-6
    # 立位は縦長 → アスペクト比(幅/高さ) < 1
    assert f["ar"] < 1.0


def test_debug_features_lying_aspect_ratio_gt1():
    # 横たわり: 体が左右(x)に広がり上下(y)は狭い → bbox 幅>高さ → ar>1
    f = pose_debug_features(_lying())
    assert f is not None
    assert f["ar"] > 1.0


def test_debug_features_ignores_low_visibility_points():
    # 低可視性の外れ点はbboxに含めない（可視点のみで算出）
    pts = {11: (0.45, 0.30), 12: (0.55, 0.30), 23: (0.47, 0.60), 24: (0.53, 0.60)}
    lms = _make(pts)
    # 1点だけ遠方・低可視性に差し替え
    lms[0] = LM(0.99, 0.99, 0.05)
    f = pose_debug_features(lms)
    assert f is not None
    assert f["bw"] < 0.5 and f["bh"] < 0.5  # 外れ点が混ざっていない


def test_fall_heuristic_fires_from_camera_samples():
    """直立→横たわり継続を流すと、既存ヒューリスティックが候補を立てる。"""
    from tomoshibi.guardian.pose import FallDetectorState, update

    state = FallDetectorState()
    fired = False
    # t=0 直立
    state, f = update(state, landmarks_to_sample(_standing(), 0.0), stillness_s=3.0)
    fired = fired or f
    # t=1..7 横たわり継続
    for t in range(1, 8):
        lying = _lying()
        state, f = update(state, landmarks_to_sample(lying, float(t)), stillness_s=3.0)
        fired = fired or f
    assert fired is True
