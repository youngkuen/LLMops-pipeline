"""LLM 응답 캐싱 Provider — Data Layer
동일한 요청(messages + temperature + 모델)이 반복되면 실제 API를 다시 호출하지 않고
이전 응답을 그대로 재사용한다.

목적: 재현성(같은 입력 → 같은 결과) 확보. Claude API 자체는 OpenAI의 seed 파라미터
같은 완전 결정성 보장이 없으므로, 입력 단위 캐싱으로 "동일 입력 → 동일 출력"을 달성한다.
부가 효과로 캐시 히트 시 API 비용이 $0이다.

LLMProvider를 감싸는 데코레이터라 다른 Provider 구현체와 자유롭게 조합할 수 있다
(인터페이스 추상화 원칙 — LLMProvider를 구현하는 것은 이 클래스도 마찬가지).
"""
from __future__ import annotations
import hashlib
import json
from app.providers.base import LLMProvider


class CachingLLMProvider(LLMProvider):
    def __init__(self, inner: LLMProvider) -> None:
        self._inner = inner
        self._cache: dict[str, str] = {}

    def chat(self, messages: list[dict], temperature: float = 0.2) -> str:
        key = self._cache_key(messages, temperature)
        if key in self._cache:
            return self._cache[key]
        response = self._inner.chat(messages, temperature)
        self._cache[key] = response
        return response

    def _cache_key(self, messages: list[dict], temperature: float) -> str:
        payload = json.dumps(
            {"model": self._inner.get_model_name(), "temperature": temperature, "messages": messages},
            sort_keys=True, ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get_model_name(self) -> str:
        return self._inner.get_model_name()

    def usage_snapshot(self) -> dict:
        return self._inner.usage_snapshot()

    def cost_usd(self, usage: dict) -> float:
        return self._inner.cost_usd(usage)

    def cache_size(self) -> int:
        """현재까지 캐시된 고유 요청 수 (관찰·디버그용)."""
        return len(self._cache)
