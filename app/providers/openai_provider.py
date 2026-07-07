"""OpenAI LLMProvider 구현체 — Data Layer"""
from __future__ import annotations
import os
from openai import OpenAI
from app.providers.base import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini") -> None:
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
        self._client = OpenAI(api_key=key)
        self._model = model

    def chat(self, messages: list[dict], temperature: float = 0.2) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    def get_model_name(self) -> str:
        return self._model
