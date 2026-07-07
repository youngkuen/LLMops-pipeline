"""LLMProvider 추상 인터페이스 — Data Layer"""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: list[dict], temperature: float = 0.2) -> str:
        """
        messages: [{'role': 'system'|'user'|'assistant', 'content': str}]
        returns: 모델의 텍스트 응답
        """
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        ...

    # ── 비용 추적 (선택적 — 미지원 provider는 0을 반환) ──────────────
    def usage_snapshot(self) -> dict:
        """지금까지 누적된 토큰 사용량 스냅샷. {input_tokens, output_tokens, calls}."""
        return {"input_tokens": 0, "output_tokens": 0, "calls": 0}

    def cost_usd(self, usage: dict) -> float:
        """주어진 usage 딕셔너리에 대한 USD 비용. 단가 미상이면 0."""
        return 0.0
