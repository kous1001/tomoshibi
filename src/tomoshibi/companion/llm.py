"""LFM2 対話バックエンド抽象。

3実装を同一インターフェイスで提供:
- MockLLM        … モデル不要。Mac開発/オフラインデモ用の温かい定型応答。
- LlamaCppLLM    … llama.cpp サーバ(OpenAI互換) 経由（Ryzen AI: Vulkan/NPU）。
- TransformersLLM… transformers 直叩き（AGENTS.md のチャットテンプレ/生成パラメータ準拠）。

`build_llm(settings)` が mode と可用性から自動選択する。
"""

from __future__ import annotations

import re
from typing import Protocol

from ..config import LFM2_GEN, Settings


class ChatLLM(Protocol):
    def chat(self, system: str, history: list[tuple[str, str]], user: str) -> str: ...

    def complete(self, system: str, user: str, max_tokens: int | None = None) -> str: ...


# --------------------------------------------------------------------------- #
# Mock — モデル無しでデモを成立させる温かい定型応答
# --------------------------------------------------------------------------- #
class MockLLM:
    backend = "mock"

    _RULES: list[tuple[str, str]] = [
        (r"こんにち|おはよう|こんばん|やあ|もしもし",
         "こんにちは。お顔が見られて嬉しいです。今日の調子はいかがですか？"),
        (r"さみし|寂し|ひとり|孤独|だれもいない",
         "そうでしたか。…そばにいますよ。よかったら、昔の楽しかったお話を聞かせてくださいな。"),
        (r"いた|痛|しんど|つらい|具合|気分が悪|めまい|ふらつ",
         "それは心配ですね。無理は禁物ですよ。つらいようなら、ご家族に相談してみましょうか？"),
        (r"くすり|薬|飲み忘れ|服薬",
         "お薬の時間ですね。お水と一緒に、ゆっくりで大丈夫ですからね。"),
        (r"ごはん|食べ|食事|お腹",
         "しっかり召し上がれましたか？温かいものを少しでも食べると、ほっとしますよね。"),
        (r"孫|息子|娘|family|家族",
         "ご家族の話、いいですねえ。最近はどんなご様子ですか？"),
        (r"ありがと|うれし|楽し",
         "そう言っていただけると、私も嬉しいです。"),
        (r"さよなら|またね|おやすみ",
         "はい、また気が向いたらいつでも声をかけてくださいね。おやすみなさい。"),
    ]

    def chat(self, system: str, history: list[tuple[str, str]], user: str) -> str:
        for pat, reply in self._RULES:
            if re.search(pat, user):
                return reply
        return "なるほど、そうなんですね。もう少し詳しく聞かせてもらえますか？"

    def complete(self, system: str, user: str, max_tokens: int | None = None) -> str:
        # 緊急原稿などの単発生成用。Mockでは事実をそのまま整形して返す。
        return ""  # 空を返すと dispatch 側がテンプレートにフォールバックする


# --------------------------------------------------------------------------- #
# llama.cpp サーバ (OpenAI互換 /v1/chat/completions)
# --------------------------------------------------------------------------- #
class LlamaCppLLM:
    backend = "llamacpp"

    def __init__(self, server_url: str):
        self.url = server_url.rstrip("/")

    def _post(self, messages: list[dict], max_tokens: int | None = None) -> str:
        import requests

        resp = requests.post(
            f"{self.url}/v1/chat/completions",
            json={
                "messages": messages,
                "temperature": LFM2_GEN["temperature"],
                "min_p": LFM2_GEN["min_p"],  # AGENTS.md 推奨（LFM2のdoom-loop回避）
                "repeat_penalty": LFM2_GEN["repetition_penalty"],
                "max_tokens": max_tokens or LFM2_GEN["max_new_tokens"],
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    def chat(self, system: str, history: list[tuple[str, str]], user: str) -> str:
        messages = [{"role": "system", "content": system}]
        for u, a in history:
            messages.append({"role": "user", "content": u})
            messages.append({"role": "assistant", "content": a})
        messages.append({"role": "user", "content": user})
        return self._post(messages)

    def complete(self, system: str, user: str, max_tokens: int | None = None) -> str:
        return self._post(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=max_tokens,
        )


# --------------------------------------------------------------------------- #
# transformers 直叩き (AGENTS.md 準拠)
# --------------------------------------------------------------------------- #
class TransformersLLM:
    backend = "transformers"

    def __init__(self, hf_id: str):
        import torch  # noqa: F401  遅延import
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.tok = AutoTokenizer.from_pretrained(hf_id)
        self.model = AutoModelForCausalLM.from_pretrained(
            hf_id, device_map="auto", dtype="bfloat16"
        )

    def _generate(self, messages: list[dict], max_tokens: int | None = None) -> str:
        inputs = self.tok.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt",
            tokenize=True,
            return_dict=True,  # transformers 5.x で必須
        ).to(self.model.device)
        out = self.model.generate(
            **inputs,
            do_sample=LFM2_GEN["do_sample"],
            temperature=LFM2_GEN["temperature"],
            min_p=LFM2_GEN["min_p"],
            repetition_penalty=LFM2_GEN["repetition_penalty"],
            max_new_tokens=max_tokens or LFM2_GEN["max_new_tokens"],
        )
        gen = out[0][inputs["input_ids"].shape[-1]:]
        return self.tok.decode(gen, skip_special_tokens=True).strip()

    def chat(self, system: str, history: list[tuple[str, str]], user: str) -> str:
        messages = [{"role": "system", "content": system}]
        for u, a in history:
            messages += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
        messages.append({"role": "user", "content": user})
        return self._generate(messages)

    def complete(self, system: str, user: str, max_tokens: int | None = None) -> str:
        return self._generate(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=max_tokens,
        )


def build_llm(settings: Settings) -> ChatLLM:
    """mode と可用性から対話バックエンドを選択する。"""
    if settings.mode == "mock":
        return MockLLM()

    if settings.llamacpp_server_url:
        try:
            return LlamaCppLLM(settings.llamacpp_server_url)
        except Exception:
            pass

    if settings.mode == "real":
        # 実機で transformers を強制（失敗時は例外を可視化したいので捕捉しない）
        return TransformersLLM(settings.lfm2_hf_id)

    # auto: transformers が使えれば実モデル、無理ならMock
    try:
        return TransformersLLM(settings.lfm2_hf_id)
    except Exception:
        return MockLLM()
