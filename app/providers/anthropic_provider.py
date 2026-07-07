"""Anthropic Claude LLMProvider 구현체 — Data Layer
토큰 사용량을 누적 추적하고, 모델별 단가로 비용(USD)을 계산한다.
"""
from __future__ import annotations
import os
from anthropic import Anthropic
from app.providers.base import LLMProvider

# 모델별 단가 (USD per 1M tokens) — (input, output). 2026-06 기준, 변동 가능.
_PRICING_USD_PER_1M: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-fable-5": (10.0, 50.0),
}


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-6") -> None:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        self._client = Anthropic(api_key=key)
        self._model = model
        self._usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0}

    def chat(self, messages: list[dict], temperature: float = 0.2) -> str:
        system = ""
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                user_messages.append(msg)

        kwargs: dict = {
            "model": self._model,
            # 생성 ML 스크립트가 길어 4096이면 중간에 잘렸다(문법 오류 유발).
            # 비스트리밍 요청의 안전 상한인 16000으로 상향.
            "max_tokens": 16000,
            "messages": user_messages,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        response = self._client.messages.create(**kwargs)

        # 사용량 누적
        usage = getattr(response, "usage", None)
        if usage is not None:
            self._usage["input_tokens"] += getattr(usage, "input_tokens", 0) or 0
            self._usage["output_tokens"] += getattr(usage, "output_tokens", 0) or 0
            self._usage["calls"] += 1

        return response.content[0].text

    def get_model_name(self) -> str:
        return self._model

    def usage_snapshot(self) -> dict:
        return dict(self._usage)

    def cost_usd(self, usage: dict) -> float:
        pin, pout = _PRICING_USD_PER_1M.get(self._model, (0.0, 0.0))
        return (
            usage.get("input_tokens", 0) / 1_000_000 * pin
            + usage.get("output_tokens", 0) / 1_000_000 * pout
        )
