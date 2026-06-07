"""転倒の視覚確認（2段階パイプラインの第2段）= LFM2-VL。

姿勢ヒューリスティック(pose.py)が候補を立てたフレームだけを LFM2-VL に渡し、
「高齢者が倒れて助けが必要か」を確認して誤検知を抑える（=工学的な質の担保）。

- MockVL          … モデル無し。常に確認成立を返す（デモ/テスト）。
- TransformersVL  … LFM2-VL を transformers で実行（イベント発火時のみ・低頻度）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import VL_CONFIRM_MIN_CONFIDENCE, Settings

# 未FTのLFM2-VL-450Bでは、英語の単純なyes/noが最も安定して正答する（実映像で検証）。
# 「助けが必要か」等の主観条件や日本語の冗長指示だと誤って no を返しやすい。
VL_PROMPT = "Is there a person lying on the floor or ground in this image? Answer yes or no."


@dataclass(frozen=True)
class VLResult:
    is_fall: bool
    confidence: float
    rationale: str
    backend: str


def _parse(text: str) -> tuple[bool, float, str]:
    head = text.strip()
    # 先頭の鉤括弧・引用符・空白を除いて「はい/いいえ」を判定（「はい」表記に対応）
    lead = head.lstrip("「『\"' 　")
    is_fall = lead.startswith("はい") or bool(re.match(r"(yes|fall)\b", lead, re.I))
    # 雑な信頼度推定（語気から）。実機では logprob 等に置換可能。
    conf = 0.85 if is_fall else 0.2
    return is_fall, conf, head


class MockVL:
    backend = "mock"

    def ensure_loaded(self) -> None:  # 互換用（mockは何もしない）
        pass

    def confirm(self, image) -> VLResult:  # image は未使用（デモ）
        return VLResult(True, 0.9, "（モック）転倒姿勢を確認しました", self.backend)


class TransformersVL:
    backend = "transformers"

    def __init__(self, hf_id: str):
        from transformers.utils import is_torch_available

        # torch が使えない環境（例: Intel Mac の torch<2.4）では早期に失敗させ、
        # build_vision の mock フォールバックに任せる（巨大DLも回避）。
        if not is_torch_available():
            raise RuntimeError("PyTorch backend unavailable; LFM2-VL needs torch>=2.4")

        self.hf_id = hf_id
        self.processor = None
        self.model = None

    def ensure_loaded(self) -> None:
        """モデルを遅延ロード（初回のみ）。サーバ起動を速く保つ。"""
        if self.model is not None:
            return
        from transformers import AutoModelForImageTextToText, AutoProcessor

        self.processor = AutoProcessor.from_pretrained(self.hf_id)
        self.model = AutoModelForImageTextToText.from_pretrained(
            self.hf_id, device_map="auto", dtype="bfloat16"
        )

    def confirm(self, image) -> VLResult:
        self.ensure_loaded()
        conv = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": VL_PROMPT},
                ],
            }
        ]
        inputs = self.processor.apply_chat_template(
            conv,
            add_generation_prompt=True,
            tokenize=True,  # これが無いと整形済み文字列が返り .to() で失敗する
            return_tensors="pt",
            return_dict=True,
        ).to(self.model.device)
        out = self.model.generate(**inputs, max_new_tokens=64)
        # 入力プロンプト分を除き、生成された応答だけをデコードする
        gen = out[0][inputs["input_ids"].shape[-1]:]
        text = self.processor.batch_decode([gen], skip_special_tokens=True)[0]
        is_fall, conf, rationale = _parse(text)
        return VLResult(is_fall and conf >= VL_CONFIRM_MIN_CONFIDENCE, conf, rationale, self.backend)


def build_vision(settings: Settings):
    if settings.mode == "mock":
        return MockVL()
    try:
        return TransformersVL(settings.lfm2_vl_hf_id)
    except Exception:
        return MockVL()
