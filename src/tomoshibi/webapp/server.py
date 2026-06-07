"""FastAPI サーバ — sobani風 Live2D 会話UI に対話＋見守りを配信する。

Pythonロジック(runtime.py)はそのまま再利用し、表示層だけ HTML/JS フロントに置き換える。
sobani app/server.py の構造（単一スレッド推論executor・静的マウント・b64音声）を踏襲。

起動:
  PYTHONPATH=src python -m uvicorn tomoshibi.webapp.server:app --port 8000
"""

from __future__ import annotations

import asyncio
import base64
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import FALL_STILLNESS_S, OVERHEAD_STILLNESS_S
from ..guardian.camera import CameraMonitor
from ..guardian.fsm import Event, Phase
from ..runtime import Runtime
from .serialize import guardian_state

WEB_DIR = Path(__file__).resolve().parents[3] / "web"

# モデル推論を直列化する単一スレッド（LFM2/MLX のスレッド切替オーバーヘッド回避）
_INFER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tomoshibi-infer")
# 視覚(LFM2-VL)は別スレッドに分離（モデルロード~数十秒や推論が対話をブロックしないように）
_VL_INFER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tomoshibi-vl")
_state: dict = {}


async def _run(fn):
    return await asyncio.get_running_loop().run_in_executor(_INFER, fn)


@asynccontextmanager
async def lifespan(app: FastAPI):
    rt = Runtime.build()
    _state["rt"] = rt

    # カメラ転倒検知: 候補成立時の重い処理(VL確認)は VL専用スレッドで（対話を止めない）。
    def _on_fall_candidate(image):
        print("[灯] 姿勢検知が転倒候補を検出 → LFM2-VL 確認へ投入", flush=True)
        _VL_INFER.submit(rt.report_fall_candidate, image)

    monitor = CameraMonitor(
        camera_index=rt.settings.guardian_camera_index,
        fps=rt.settings.guardian_fps,
        on_fall_candidate=_on_fall_candidate,
        stillness_s=FALL_STILLNESS_S,
        can_trigger=lambda: rt.escalation.phase == Phase.MONITORING,
    )
    _state["camera"] = monitor

    print("[灯] backends:", rt.backends())
    try:
        yield
    finally:
        monitor.stop()


app = FastAPI(title="灯 Tomoshibi", lifespan=lifespan)


# ---------- スキーマ ----------
class ChatIn(BaseModel):
    text: str


class EventIn(BaseModel):
    event: str  # resident_ok | resident_help | family_ack | cancel


class CameraStartIn(BaseModel):
    source: str = "camera"  # camera（実カメラ）| demo（デモ動画）
    demo: int = 1  # source=demo のとき data/demos/demo{N}.mp4 を再生（1..4）


class TranscribeIn(BaseModel):
    audio: str  # base64 エンコードされた録音（webm/ogg/wav 等）
    ext: str = "webm"  # ブラウザの MediaRecorder 形式（Chrome=webm, Safari=mp4）


# ---------- ヘルパ ----------
def _speak_payload(text: str, wav_path: str | None) -> dict:
    """応答テキストに音声(base64 wav)を添える。mock時 wav_path=None → 音声なし。"""
    audio = None
    if wav_path:
        try:
            audio = base64.b64encode(Path(wav_path).read_bytes()).decode("ascii")
        except Exception:  # 音声読み込み失敗でもテキストは返す
            audio = None
    return {"text": text, "character_name": "灯", "audio": audio}


def _rt() -> Runtime:
    return _state["rt"]


def _camera() -> CameraMonitor:
    return _state["camera"]


def _camera_dict() -> dict:
    m = _state.get("camera")
    if not m:
        return {"running": False, "error": ""}
    return {"running": m.is_running(), "error": m.status.error}


def _gstate() -> dict:
    """見守り状態（カメラ状態込み）。"""
    return guardian_state(_rt(), camera=_camera_dict())


# ---------- 会話 API ----------
@app.post("/api/greet")
async def greet():
    def work():
        text, wav = _rt().companion_greet()
        return _speak_payload(text, wav)

    return JSONResponse(await _run(work))


@app.post("/api/chat")
async def chat(body: ChatIn):
    def work():
        text, wav = _rt().companion_say(body.text)
        return _speak_payload(text, wav)

    return JSONResponse(await _run(work))


def _to_wav16k(src: Path) -> Path | None:
    """ブラウザ録音(webm/opus等)を 16kHz mono wav に変換（whisper系が好む形式）。"""
    out = src.with_suffix(".16k.wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-ar", "16000", "-ac", "1", str(out)],
            capture_output=True,
            timeout=30,
            check=True,
        )
        return out if out.exists() else None
    except Exception:
        return None


@app.post("/api/transcribe")
async def transcribe(body: TranscribeIn):
    """マイク録音(base64) → 日本語テキスト。空文字なら認識不可（mock/失敗）。"""

    def work():
        tmp = Path(tempfile.mktemp(suffix="." + body.ext.lstrip(".")))
        try:
            tmp.write_bytes(base64.b64decode(body.audio))
        except Exception:
            return {"text": "", "error": "invalid base64"}
        wav = _to_wav16k(tmp) or tmp
        text = _rt().transcribe(str(wav))
        return {"text": text}

    return JSONResponse(await _run(work))


# ---------- 見守り API ----------
@app.get("/api/guardian/state")
def guardian_get_state():
    return JSONResponse(_gstate())


@app.post("/api/guardian/fall")
async def guardian_fall():
    def work():
        _rt().simulate_fall()  # 🧪手動シミュレート（VL省略で直接確定）
        return _gstate()

    return JSONResponse(await _run(work))


@app.post("/api/guardian/event")
async def guardian_event(body: EventIn):
    try:
        ev = Event(body.event)
    except ValueError:
        return JSONResponse({"error": f"unknown event: {body.event}"}, status_code=400)

    def work():
        _rt().feed_event(ev)
        return _gstate()

    return JSONResponse(await _run(work))


@app.post("/api/guardian/tick")
async def guardian_tick():
    def work():
        _rt().tick()
        return _gstate()

    return JSONResponse(await _run(work))


@app.post("/api/guardian/reset")
def guardian_reset():
    _rt().reset_guardian()
    return JSONResponse(_gstate())


# ---------- 見守りカメラ ----------
@app.post("/api/guardian/camera/start")
def camera_start(body: CameraStartIn | None = None):
    source = (body.source if body else "camera")
    video = None
    view = "side"  # デモ動画は常に横視点（既存挙動を維持）
    stillness = FALL_STILLNESS_S  # デモは従来どおり3秒
    if source == "demo":
        n = body.demo if body else 1
        n = n if n in (1, 2, 3, 4) else 1
        p = _rt().settings.resolve(f"data/demos/demo{n}.mp4")
        if not p.exists():  # 後方互換: 個別ファイルが無ければ既定動画
            p = _rt().settings.resolve(_rt().settings.guardian_video_path)
        video = str(p)
    else:  # ライブカメラは設定の視点（既定 overhead/俯瞰）で判定
        view = _rt().settings.guardian_camera_view
        stillness = OVERHEAD_STILLNESS_S  # 俯瞰ライブは10秒（短時間横になる動作の誤検知抑制）
        # 監視開始＝新セッション。FSMをMONITORINGへ戻し can_trigger を確実に有効化
        # （前回の検知/解決フェーズに留まると候補がVLへ届かないため）。
        _rt().reset_guardian()
    _camera().start(video_path=video, view=view, stillness_s=stillness)
    _VL_INFER.submit(_rt().warm_vision)  # VLモデルを裏で先読み（VL専用スレッド）
    return JSONResponse(_gstate())


@app.post("/api/guardian/camera/stop")
def camera_stop():
    _camera().stop()
    return JSONResponse(_gstate())


@app.get("/api/guardian/camera.mjpg")
def camera_stream():
    """骨格＋状態を描いた注釈フレームを MJPEG で配信。"""
    monitor = _camera()
    boundary = "frame"

    def gen():
        import time as _t

        blank_wait = 0
        while monitor.is_running():
            jpeg = monitor.latest_jpeg()
            if jpeg is None:
                blank_wait += 1
                if blank_wait > 100:  # ~5秒待っても来なければ終了
                    break
                _t.sleep(0.05)
                continue
            blank_wait = 0
            yield (
                b"--" + boundary.encode() + b"\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            )
            _t.sleep(1.0 / max(1, _rt().settings.guardian_fps))

    return StreamingResponse(
        gen(), media_type=f"multipart/x-mixed-replace; boundary={boundary}"
    )


# ---------- 静的配信 ----------
@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/favicon.ico")
def favicon():
    return FileResponse(WEB_DIR / "favicon.ico", media_type="image/x-icon")


app.mount("/vendor", StaticFiles(directory=WEB_DIR / "vendor"), name="vendor")
app.mount("/models", StaticFiles(directory=WEB_DIR / "models"), name="models")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
