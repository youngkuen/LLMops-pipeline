"""CachingLLMProvider 단위 테스트 — 재현성(동일 입력 → 동일 출력·API 호출 생략)"""
from app.providers.base import LLMProvider
from app.providers.caching_provider import CachingLLMProvider


class _CountingLLM(LLMProvider):
    """호출될 때마다 다른 응답을 주는 provider — 캐시가 안 걸리면 값이 달라짐이 드러남."""

    def __init__(self) -> None:
        self.call_count = 0

    def chat(self, messages, temperature=0.2) -> str:
        self.call_count += 1
        return f"response-{self.call_count}"

    def get_model_name(self) -> str:
        return "mock-model"


def test_identical_request_hits_cache():
    inner = _CountingLLM()
    cached = CachingLLMProvider(inner)
    messages = [{"role": "user", "content": "hello"}]

    first = cached.chat(messages, temperature=0.1)
    second = cached.chat(messages, temperature=0.1)

    assert first == second
    assert inner.call_count == 1  # 두 번째 호출은 캐시에서 나옴


def test_different_messages_are_not_cached_together():
    inner = _CountingLLM()
    cached = CachingLLMProvider(inner)

    cached.chat([{"role": "user", "content": "A"}], temperature=0.1)
    cached.chat([{"role": "user", "content": "B"}], temperature=0.1)

    assert inner.call_count == 2


def test_different_temperature_produces_different_cache_entry():
    inner = _CountingLLM()
    cached = CachingLLMProvider(inner)
    messages = [{"role": "user", "content": "hello"}]

    cached.chat(messages, temperature=0.1)
    cached.chat(messages, temperature=0.9)

    assert inner.call_count == 2


def test_get_model_name_forwards_to_inner():
    cached = CachingLLMProvider(_CountingLLM())
    assert cached.get_model_name() == "mock-model"


def test_cache_size_tracks_unique_requests():
    inner = _CountingLLM()
    cached = CachingLLMProvider(inner)
    cached.chat([{"role": "user", "content": "A"}])
    cached.chat([{"role": "user", "content": "A"}])  # 캐시 히트, 개수 안 늘어남
    cached.chat([{"role": "user", "content": "B"}])
    assert cached.cache_size() == 2
