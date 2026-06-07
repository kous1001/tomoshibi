"""転倒ヒューリスティック（純粋・ハードウェア非依存）。

MediaPipe 等から得た1フレーム分の姿勢特徴 `PoseSample` を畳み込み、転倒候補を判定する。
これは2段階パイプラインの第1段（安価）。候補が立ったら LFM2-VL（vision.py）が画像で確認する。

「倒れて静止3秒」セマンティクス（実映像URFDで検証した知見に基づく頑健版）:
1. **転倒の遷移**を検知: 直前まで上体が立っていた人が、短時間で「水平＋低位置」になった瞬間。
2. その後 **`confirm_s` 秒以内に“起き上がり(立位)”が観測されなければ転倒確定**。
   - 床に倒れると MediaPipe が人物を見失う（present=0）ことが多いが、
     **「起き上がりを見ていない＝まだ倒れている」** とみなすため、検出が途切れても確定できる。
   - 逆に confirm_s 以内に立位へ戻れば「ただの座り込み/しゃがみ」として取消。

設計方針: 純粋関数 `update(state, sample, *, stillness_s) -> (new_state, candidate)`（不変）。
`stillness_s` は「転倒後に起き上がらなければ確定するまでの秒数（=confirm_s）」。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

# --- しきい値（マジックナンバーをここで命名） ---
TORSO_HORIZONTAL_DEG = 55.0  # これ以上で「水平（倒れ）」（0=直立, 90=水平）
TORSO_UPRIGHT_DEG = 45.0  # これ未満なら「上体が立っている（立位/座位）」
LOW_CENTROID = 0.55  # 重心がフレーム下方(>=0.55)なら「低い位置」
STANDING_CENTROID = 0.50  # 「起き上がった」とみなす重心の高さ上限（これ未満＝立位の高さ）
TRANSITION_WINDOW_S = 2.5  # 直立→水平がこの秒内なら「転倒の遷移」
RECOVERY_S = 0.4  # 起き上がりがこの秒継続したら取消（床の単発誤推定では取消さない）
MIN_KEYPOINT_CONF = 0.3  # これ未満の検出は無視（ノイズ抑制）

# --- 俯瞰(overhead/真上)カメラ用しきい値 ---
# 真上視点では画像の上下が重力と一致しないため角度/重心は無意味。代わりに画像上の
# 胴体長(肩中点−腰中点の距離=見かけの大きさ≒カメラからの距離)を使う。
# 高所から見下ろす配置の実測(2026-06-07): 立位は頭がカメラに近く大きく写り len≈0.77、
# 転倒は床に倒れて遠く小さく写り len≈0.28。よって「立位=長い / 転倒=短い」。
# 値は正規化座標(0..1)。デッドゾーン(FALLEN<x<UPRIGHT)でちらつきを防ぐ。実画角で要微調整。
OVERHEAD_UPRIGHT_LEN = 0.50  # これ以上なら「立位（近い＝大きく写る）」
OVERHEAD_FALLEN_LEN = 0.40  # これ以下なら「転倒（床に倒れ遠い＝小さく写る）」

VIEW_SIDE = "side"  # 横から（既存・デモ動画）
VIEW_OVERHEAD = "overhead"  # 真上から（俯瞰・ライブカメラ）


@dataclass(frozen=True)
class PoseSample:
    """1フレーム分の姿勢特徴（正規化済み）。"""

    t: float  # タイムスタンプ(秒)
    torso_angle_deg: float  # 体幹の傾き 0=直立, 90=水平
    centroid_y: float  # 重心の縦位置 0=上端, 1=下端
    confidence: float  # 検出信頼度 0..1
    person_present: bool = True
    torso_length: float = 0.0  # 画像上の胴体長(肩中点−腰中点距離, 正規化)。俯瞰判定用。


@dataclass(frozen=True)
class FallDetectorState:
    """転倒検知器の状態（不変）。`update` で新しい状態を返す。"""

    pending_since: Optional[float] = None  # 転倒を検知し「未回復」を待っている開始時刻
    last_upright_t: Optional[float] = None  # 最後に上体が立っていた時刻（遷移判定用）
    recover_since: Optional[float] = None  # 待機中に「起き上がり」が続いている開始時刻
    last: Optional[PoseSample] = None  # 直前サンプル
    candidate_fired: bool = False  # 候補確定済み（多重発火防止）

    # 互換: 旧名 fallen_since を参照する箇所向け（カメラ描画など）
    @property
    def fallen_since(self) -> Optional[float]:
        return self.pending_since


def _is_fallen_posture(s: PoseSample, view: str = VIEW_SIDE) -> bool:
    if view == VIEW_OVERHEAD:
        # 俯瞰: 胴体が画像上で小さい（床に倒れて遠い）＝「倒れ」
        return s.torso_length <= OVERHEAD_FALLEN_LEN
    return s.torso_angle_deg >= TORSO_HORIZONTAL_DEG and s.centroid_y >= LOW_CENTROID


def _torso_upright(s: PoseSample, view: str = VIEW_SIDE) -> bool:
    """上体が立っている（遷移判定用）。"""
    if not (s.person_present and s.confidence >= MIN_KEYPOINT_CONF):
        return False
    if view == VIEW_OVERHEAD:
        # 俯瞰: 胴体が画像上で大きい（カメラに近い）＝「立位」
        return s.torso_length >= OVERHEAD_UPRIGHT_LEN
    return s.torso_angle_deg < TORSO_UPRIGHT_DEG


def _is_recovery(s: PoseSample, view: str = VIEW_SIDE) -> bool:
    """「起き上がった」と判定。"""
    if view == VIEW_OVERHEAD:
        # 俯瞰: 胴体が再び大きく写れば（立ち上がってカメラに近づけば）回復
        return _torso_upright(s, view)
    # side: 立位 かつ 重心が高い（床の単発誤推定を除外するため高さも要求）
    return _torso_upright(s, view) and s.centroid_y < STANDING_CENTROID


def update(
    state: FallDetectorState,
    sample: PoseSample,
    *,
    stillness_s: float,
    view: str = VIEW_SIDE,
) -> tuple[FallDetectorState, bool]:
    """状態を更新し (新状態, 候補が今フレームで確定したか) を返す。

    view: "side"(横/デモ動画・既存) または "overhead"(俯瞰/ライブカメラ)。
    判定述語のみ view で切り替わり、遷移→未回復→確定の状態機械は共通。
    """
    now = sample.t

    # --- 待機(pending)中: 起き上がり監視＋タイムアウト確定（present に関わらず評価） ---
    if state.pending_since is not None:
        if _is_recovery(sample, view):
            # 起き上がりが RECOVERY_S 継続したら取消（単発の床誤推定では取消さない）
            rec = state.recover_since if state.recover_since is not None else now
            if now - rec >= RECOVERY_S:
                return FallDetectorState(last_upright_t=now, last=sample), False
            return replace(state, recover_since=rec, last=sample), False
        if (not state.candidate_fired) and (now - state.pending_since) >= stillness_s:
            # confirm_s 経過しても起き上がらない → 転倒確定
            return replace(state, recover_since=None, last=sample, candidate_fired=True), True
        # まだ待機（検出途切れ・床での誤推定は待機継続。起き上がり計時はリセット）
        return replace(state, recover_since=None, last=sample), False

    # --- 非pending: 転倒の遷移を探す ---
    if not sample.person_present or sample.confidence < MIN_KEYPOINT_CONF:
        return replace(state, last=sample), False

    upright_t = now if _torso_upright(sample, view) else state.last_upright_t

    transitioned = (
        _is_fallen_posture(sample, view)
        and upright_t is not None
        and (now - upright_t) <= TRANSITION_WINDOW_S
    )
    if transitioned:
        # 立位→倒れの遷移を検知 → 「未回復」待機を開始
        return FallDetectorState(pending_since=now, last_upright_t=upright_t, last=sample), False

    return FallDetectorState(last_upright_t=upright_t, last=sample), False
