"""灯(Tomoshibi) — Gradio 2ペイン・ダッシュボード。

左: 話し相手(Companion) / 右: 見守り(Guardian)。
kitのlazy-loadパターン: モデルは main() で構築し、ハンドラに渡す。
"""

from __future__ import annotations

import gradio as gr

from .guardian.fsm import Event
from .runtime import Runtime
from .ui_render import (
    emergency_md,
    profile_card_md,
    status_md,
    timeline_md,
)

CSS = """
:root { --tomoshibi-warm: #e8763a; }
.gradio-container { max-width: 1180px !important; }
#title h1 { font-size: 1.9rem; letter-spacing: .02em; }
.status-box { border-radius: 14px; padding: 6px 14px; }
.big button { font-size: 1.05rem; padding: 12px 8px; }
footer { display: none !important; }
"""


def _guardian_outputs(rt: Runtime):
    return status_md(rt), timeline_md(rt.timeline), emergency_md(rt)


def build_ui(rt: Runtime) -> gr.Blocks:
    with gr.Blocks(title="灯 Tomoshibi") as demo:
        with gr.Row(elem_id="title"):
            gr.Markdown(
                "# 灯 — Tomoshibi\n"
                "一人暮らしの高齢者のための、**100%オンデバイス**の話し相手＆見守り "
                "<small>· LFM2 on AMD Ryzen AI</small>"
            )

        with gr.Row(equal_height=False):
            # ---------------- 左: 話し相手 ----------------
            with gr.Column(scale=5):
                gr.Markdown("### 💬 話し相手")
                chatbot = gr.Chatbot(height=420, label="灯との会話")
                audio_out = gr.Audio(label="灯の声", autoplay=True, visible=True)
                with gr.Row():
                    msg = gr.Textbox(
                        placeholder="話しかけてください（例: 最近ちょっと寂しくてね）",
                        scale=8,
                        show_label=False,
                    )
                    send = gr.Button("送信", variant="primary", scale=2)

            # ---------------- 右: 見守り ----------------
            with gr.Column(scale=5):
                gr.Markdown("### 🛡️ 見守り")
                status = gr.Markdown(status_md(rt), elem_classes="status-box")
                with gr.Row(elem_classes="big"):
                    btn_fall = gr.Button("🧪 転倒をシミュレート", variant="stop")
                    btn_reset = gr.Button("↩︎ リセット")
                with gr.Row(elem_classes="big"):
                    btn_ok = gr.Button("🙆 本人:大丈夫")
                    btn_help = gr.Button("🆘 本人:助けて")
                    btn_ack = gr.Button("👨‍👩‍👧 家族が対応")
                emergency = gr.Markdown("")
                with gr.Accordion("👤 医療プロフィール（ローカル保存）", open=False):
                    gr.Markdown(profile_card_md(rt))
                gr.Markdown("#### 📜 タイムライン")
                timeline = gr.Markdown(timeline_md(rt.timeline))

        # 2秒ごとにタイムアウトを評価（S1→S2→S3 を自動進行）
        ticker = gr.Timer(2.0)

        guardian_targets = [status, timeline, emergency]

        # ---- ハンドラ ----
        def on_send(user_text, history):
            history = history or []
            reply, wav = rt.companion_say(user_text)
            if not reply:
                return history, None, ""
            history = history + [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": reply},
            ]
            return history, wav, ""

        def on_fall():
            rt.report_fall_candidate(image=None)
            return _guardian_outputs(rt)

        def on_event(ev: Event):
            def _handler():
                rt.feed_event(ev)
                return _guardian_outputs(rt)
            return _handler

        def on_reset():
            rt.reset_guardian()
            return _guardian_outputs(rt)

        def on_tick():
            rt.tick()
            return _guardian_outputs(rt)

        # ---- 配線 ----
        send.click(on_send, [msg, chatbot], [chatbot, audio_out, msg])
        msg.submit(on_send, [msg, chatbot], [chatbot, audio_out, msg])

        btn_fall.click(on_fall, None, guardian_targets)
        btn_ok.click(on_event(Event.RESIDENT_OK), None, guardian_targets)
        btn_help.click(on_event(Event.RESIDENT_HELP), None, guardian_targets)
        btn_ack.click(on_event(Event.FAMILY_ACK), None, guardian_targets)
        btn_reset.click(on_reset, None, guardian_targets)
        ticker.tick(on_tick, None, guardian_targets)

    return demo


def main() -> None:
    rt = Runtime.build()  # ← モデル構築はここ（lazy-load）
    print("[灯] backends:", rt.backends())
    demo = build_ui(rt)
    launch_kwargs = dict(server_name="0.0.0.0", inbrowser=False)
    try:
        # Gradio 6: css/theme は launch() で指定
        demo.queue().launch(css=CSS, theme=gr.themes.Soft(), **launch_kwargs)
    except TypeError:
        # Gradio <6 フォールバック
        demo.queue().launch(**launch_kwargs)


if __name__ == "__main__":
    main()
