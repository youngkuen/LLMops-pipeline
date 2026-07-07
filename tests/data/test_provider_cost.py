"""AnthropicProvider 비용 계산 단위 테스트"""
from app.providers.anthropic_provider import AnthropicProvider


def test_cost_sonnet_1m_tokens():
    # sonnet-4-6: input $3 / output $15 per 1M → 1M+1M = $18
    p = AnthropicProvider(api_key="test-key", model="claude-sonnet-4-6")
    usd = p.cost_usd({"input_tokens": 1_000_000, "output_tokens": 1_000_000})
    assert abs(usd - 18.0) < 1e-6


def test_cost_opus_partial():
    # opus-4-8: input $5 / output $25 → 200k in + 100k out = 1.0 + 2.5 = 3.5
    p = AnthropicProvider(api_key="test-key", model="claude-opus-4-8")
    usd = p.cost_usd({"input_tokens": 200_000, "output_tokens": 100_000})
    assert abs(usd - 3.5) < 1e-6


def test_cost_unknown_model_zero():
    p = AnthropicProvider(api_key="test-key", model="some-unknown-model")
    assert p.cost_usd({"input_tokens": 1_000_000, "output_tokens": 1_000_000}) == 0.0


def test_usage_snapshot_starts_zero():
    p = AnthropicProvider(api_key="test-key", model="claude-sonnet-4-6")
    snap = p.usage_snapshot()
    assert snap == {"input_tokens": 0, "output_tokens": 0, "calls": 0}
