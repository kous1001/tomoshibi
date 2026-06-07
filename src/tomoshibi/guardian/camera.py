"""カメラ転倒検知（サーバ側・2段階の第1段）。

cv2 でカメラ取得 → MediaPipe Pose → `landmarks_to_sample` で姿勢特徴に変換 →
既存 `pose.py` のヒューリスティックで畳み込み → 候補成立時にコールバック（LFM2-VL確認へ）。

`landmarks_to_sample` は純粋関数でカメラ/mediapipe非依存（テスト可能）。
cv2/mediapipe は `CameraMonitor.run` 内で遅延import（依存が無い環境でもモジュールはimport可）。
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from .pose import VIEW_OVERHEAD, VIEW_SIDE, FallDetectorState, PoseSample, update

# MediaPipe Pose のランドマーク番号
_L_SHOULDER, _R_SHOULDER = 11, 12
_L_HIP, _R_HIP = 23, 24
_MIN_VISIBILITY = 0.3  # これ未満は人物不在扱い

# オーバーレイ文字色（BGR）。濃いめの紫。
_OVERLAY_COLOR = (170, 20, 110)


def _mid(a, b, attr: str) -> float:
    return (getattr(a, attr) + getattr(b, attr)) / 2.0


def landmarks_to_sample(landmarks: Optional[Sequence], t: float) -> PoseSample:
    """MediaPipe Pose ランドマーク → PoseSample（純粋）。

    landmarks は index で引け、各要素が .x .y .visibility を持つ（0..1正規化, y下向き）。
    None / 不足 / 低可視性なら person_present=False のサンプルを返す。
    """
    if not landmarks or len(landmarks) <= _R_HIP:
        return PoseSample(t=t, torso_angle_deg=0.0, centroid_y=0.0, confidence=0.0,
                          person_present=False)

    ls, rs = landmarks[_L_SHOULDER], landmarks[_R_SHOULDER]
    lh, rh = landmarks[_L_HIP], landmarks[_R_HIP]
    confidence = sum(getattr(p, "visibility", 0.0) for p in (ls, rs, lh, rh)) / 4.0
    if confidence < _MIN_VISIBILITY:
        return PoseSample(t=t, torso_angle_deg=0.0, centroid_y=0.0,
                          confidence=confidence, person_present=False)

    sh_x, sh_y = _mid(ls, rs, "x"), _mid(ls, rs, "y")
    hip_x, hip_y = _mid(lh, rh, "x"), _mid(lh, rh, "y")

    # 体幹ベクトル(肩中点−腰中点)と鉛直のなす角。0=直立, 90=水平。
    dx = sh_x - hip_x
    dy = sh_y - hip_y
    torso_angle_deg = math.degrees(math.atan2(abs(dx), abs(dy))) if (dx or dy) else 0.0

    # 重心の縦位置（4点平均y, 0=上,1=下）
    centroid_y = (sh_y + hip_y) / 2.0
    # 画像上の胴体長（俯瞰判定用: 立位は潰れて短く, 転倒は床に広がって長い）。
    torso_length = math.hypot(dx, dy)
    return PoseSample(
        t=t,
        torso_angle_deg=torso_angle_deg,
        centroid_y=centroid_y,
        confidence=confidence,
        person_present=True,
        torso_length=torso_length,
    )


def pose_debug_features(landmarks: Optional[Sequence]) -> Optional[dict]:
    """俯瞰しきい値の校正用に複数の候補特徴量を算出する（純粋・cv2非依存）。

    どの特徴が立位/転倒を最も分離するか実機で見極めるための計装。
    可視性>=0.3 のランドマークのみを使う。十分なら dict、不足なら None を返す。
    キー: len(胴体長), ar(全身bboxの幅/高さ), bw, bh, sw(肩幅), cy(重心y), a(体幹角deg)。
    """
    if not landmarks or len(landmarks) <= _R_HIP:
        return None
    ls, rs = landmarks[_L_SHOULDER], landmarks[_R_SHOULDER]
    lh, rh = landmarks[_L_HIP], landmarks[_R_HIP]

    sh_x, sh_y = _mid(ls, rs, "x"), _mid(ls, rs, "y")
    hip_x, hip_y = _mid(lh, rh, "x"), _mid(lh, rh, "y")
    dx, dy = sh_x - hip_x, sh_y - hip_y

    # 全身バウンディングボックス（可視性>=0.3 の点のみ）
    vis_pts = [p for p in landmarks if getattr(p, "visibility", 0.0) >= _MIN_VISIBILITY]
    if not vis_pts:
        return None
    xs = [p.x for p in vis_pts]
    ys = [p.y for p in vis_pts]
    bw = max(xs) - min(xs)
    bh = max(ys) - min(ys)
    ar = bw / bh if bh > 1e-6 else 0.0

    return {
        "len": math.hypot(dx, dy),  # 胴体長
        "ar": ar,  # 全身アスペクト比 幅/高さ（横たわると >1 になりやすい）
        "bw": bw,  # bbox 幅
        "bh": bh,  # bbox 高さ
        "sw": math.hypot(ls.x - rs.x, ls.y - rs.y),  # 肩幅（遠近の代理）
        "cy": (sh_y + hip_y) / 2.0,  # 重心y
        "a": math.degrees(math.atan2(abs(dx), abs(dy))) if (dx or dy) else 0.0,  # 体幹角
    }


# MediaPipe Pose の主要ボーン（Tasks API は描画ユーティリティが無いので自前で描く）
_POSE_CONNECTIONS = [
    (11, 12), (11, 23), (12, 24), (23, 24),  # 胴体
    (11, 13), (13, 15), (12, 14), (14, 16),  # 腕
    (23, 25), (25, 27), (24, 26), (26, 28),  # 脚
]

_POSE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)


def _ensure_pose_model() -> str:
    """MediaPipe Tasks の Pose モデル(.task)を models/ に用意（無ければDL）。"""
    import urllib.request

    dest = Path(__file__).resolve().parents[3] / "models" / "pose_landmarker_lite.task"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(_POSE_MODEL_URL, dest)
    return str(dest)


def _draw_pose(frame, lms) -> None:
    """フレームに骨格（線＋点）を自前で描画する（cv2）。lms は正規化座標のリスト。"""
    import cv2

    if not lms:
        return
    h, w = frame.shape[:2]
    pts = [(int(p.x * w), int(p.y * h)) for p in lms]
    for a, b in _POSE_CONNECTIONS:
        if a < len(pts) and b < len(pts):
            cv2.line(frame, pts[a], pts[b], (80, 230, 210), 2, cv2.LINE_AA)
    for x, y in pts:
        cv2.circle(frame, (x, y), 3, (255, 200, 80), -1, cv2.LINE_AA)


@dataclass
class CameraStatus:
    running: bool = False
    error: str = ""


class CameraMonitor:
    """カメラ＋MediaPipeで姿勢を監視し、転倒候補をコールバックする背景スレッド。

    on_fall_candidate(image): 候補確定時に呼ばれる（image は PIL.Image）。重い処理は
      呼び出し側で executor に投げる想定（このループはブロックしない）。
    can_trigger(): True のときのみ候補をコールバック（例: 見守りがMONITORINGのとき）。
    """

    def __init__(
        self,
        *,
        camera_index: int,
        fps: int,
        on_fall_candidate: Callable[[object], None],
        stillness_s: float,
        can_trigger: Callable[[], bool] = lambda: True,
    ):
        self.camera_index = camera_index
        self.fps = max(1, fps)
        self.on_fall_candidate = on_fall_candidate
        self.stillness_s = stillness_s
        self.can_trigger = can_trigger

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._jpeg: Optional[bytes] = None
        self._video_path: Optional[str] = None  # 指定時はカメラでなく動画ファイルを再生
        self._view: str = VIEW_SIDE  # 転倒判定の視点（side=横/デモ, overhead=俯瞰/ライブ）
        self.status = CameraStatus()

    # ------------------------------------------------------------------ #
    def start(
        self,
        video_path: Optional[str] = None,
        view: str = VIEW_SIDE,
        stillness_s: Optional[float] = None,
    ) -> CameraStatus:
        if self._thread and self._thread.is_alive():
            return self.status
        self._video_path = video_path
        self._view = view
        if stillness_s is not None:  # セッション毎に確定待ち秒数を上書き（俯瞰=長め）
            self.stillness_s = stillness_s
        self._stop.clear()
        self.status = CameraStatus(running=True)
        self._thread = threading.Thread(target=self._run, name="guardian-camera", daemon=True)
        self._thread.start()
        return self.status

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self.status = CameraStatus(running=False)
        with self._lock:
            self._jpeg = None

    def latest_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self._jpeg

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ------------------------------------------------------------------ #
    def _run(self) -> None:
        try:
            import cv2
            import mediapipe as mp
            import numpy as np  # noqa: F401  (cv2が依存)
            from PIL import Image
        except Exception as e:  # 依存未導入
            self.status = CameraStatus(running=False, error=f"依存未導入: {e}")
            return

        import sys

        try:
            if self._video_path:
                cap = cv2.VideoCapture(self._video_path)  # デモ動画ファイル
            else:
                # macOS は AVFoundation を明示（cv2同梱ffmpegのlibavdevice衝突を回避）。
                backend = cv2.CAP_AVFOUNDATION if sys.platform == "darwin" else cv2.CAP_ANY
                cap = cv2.VideoCapture(self.camera_index, backend)
        except Exception as e:
            self.status = CameraStatus(running=False, error=f"カメラ初期化失敗: {e}")
            return
        if not cap.isOpened():
            src = "動画" if self._video_path else "カメラ"
            self.status = CameraStatus(running=False, error=f"{src}を開けませんでした")
            return

        # MediaPipe Tasks API（0.10.x で legacy solutions は廃止）
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision

        try:
            model_path = _ensure_pose_model()
            options = mp_vision.PoseLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=model_path),
                running_mode=mp_vision.RunningMode.VIDEO,
                num_poses=1,
            )
            landmarker = mp_vision.PoseLandmarker.create_from_options(options)
        except Exception as e:
            self.status = CameraStatus(running=False, error=f"姿勢モデル初期化失敗: {e}")
            cap.release()
            return

        state = FallDetectorState()
        interval = 1.0 / self.fps
        start_ts = time.time()
        last_ts_ms = -1
        dbg_last = 0.0  # 診断ログのスロットル用

        try:
            while not self._stop.is_set():
                loop_start = time.time()
                ok, frame = cap.read()
                if not ok:
                    if self._video_path:  # デモ動画は先頭へ巻き戻してループ（状態もリセット）
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        state = FallDetectorState()
                        continue
                    time.sleep(0.05)
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                ts_ms = int((time.time() - start_ts) * 1000)
                if ts_ms <= last_ts_ms:  # VIDEOモードは厳密に増加するタイムスタンプが必要
                    ts_ms = last_ts_ms + 1
                last_ts_ms = ts_ms
                result = landmarker.detect_for_video(mp_image, ts_ms)
                lms = result.pose_landmarks[0] if result.pose_landmarks else None

                now = time.time()
                sample = landmarks_to_sample(lms, now)
                state, candidate = update(
                    state, sample, stillness_s=self.stillness_s, view=self._view
                )

                # 診断ログ（俯瞰時のみ・約2Hz、候補発火時は即時）。校正後に削除予定。
                if self._view == VIEW_OVERHEAD and (candidate or now - dbg_last >= 0.5):
                    dbg_last = now
                    pend = state.pending_since
                    pend_age = f"{now - pend:0.1f}s" if pend is not None else "-"
                    print(
                        f"[overhead] present={int(sample.person_present)} "
                        f"len={sample.torso_length:0.2f} conf={sample.confidence:0.2f} "
                        f"pending={pend_age} candidate={int(candidate)} "
                        f"can_trigger={int(self.can_trigger())}",
                        flush=True,
                    )

                # 注釈描画（骨格＋状態）
                label = "Monitoring"
                label2 = ""  # 俯瞰校正用の2行目（特徴量）
                if sample.person_present:
                    if self._view == VIEW_OVERHEAD:
                        # 俯瞰: しきい値校正のため複数特徴量を常時表示
                        f = pose_debug_features(lms)
                        if f:
                            label = f"len={f['len']:0.2f} ar={f['ar']:0.2f} sw={f['sw']:0.2f}"
                            label2 = (f"bw={f['bw']:0.2f} bh={f['bh']:0.2f} "
                                      f"y={f['cy']:0.2f} a={f['a']:0.0f}")
                    else:
                        label = f"angle={sample.torso_angle_deg:0.0f} y={sample.centroid_y:0.2f}"
                if state.fallen_since is not None:
                    label = "FALL?  " + label
                _draw_pose(frame, lms)
                cv2.putText(frame, label, (12, 28), cv2.FONT_HERSHEY_SIMPLEX,
                            0.7, _OVERLAY_COLOR, 2, cv2.LINE_AA)
                if label2:
                    cv2.putText(frame, label2, (12, 54), cv2.FONT_HERSHEY_SIMPLEX,
                                0.7, _OVERLAY_COLOR, 2, cv2.LINE_AA)
                ok2, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok2:
                    with self._lock:
                        self._jpeg = buf.tobytes()

                # 候補成立 かつ ゲート許可 → LFM2-VL確認へ（PIL Imageで渡す）
                if candidate and self.can_trigger():
                    try:
                        self.on_fall_candidate(Image.fromarray(rgb))
                    except Exception:
                        pass

                dt = time.time() - loop_start
                if dt < interval:
                    time.sleep(interval - dt)
        except Exception as e:  # ループの致命的例外を状態に残す（静かな死を防ぐ）
            self.status = CameraStatus(running=False, error=f"カメラ処理エラー: {e}")
        finally:
            try:
                landmarker.close()
            except Exception:
                pass
            try:
                cap.release()
            except Exception:
                pass
            if not self.status.error:
                self.status = CameraStatus(running=False)
