"""T-008 검증 — Plan Agent 단위 테스트 (MockLLMProvider 사용)"""
import json
import pytest
from app.agents.plan_agent import PlanAgent
from app.domain.models import ColumnSpec, DataSchema
from app.providers.base import LLMProvider


class MockLLMProvider(LLMProvider):
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.call_count = 0

    def chat(self, messages, temperature=0.2) -> str:
        self.call_count += 1
        if self._responses:
            return self._responses.pop(0)
        return "{}"

    def get_model_name(self) -> str:
        return "mock"


SAMPLE_SCHEMA = DataSchema(
    columns=[
        ColumnSpec(name="age", data_type="NUMERIC"),
        ColumnSpec(name="income", data_type="NUMERIC"),
        ColumnSpec(name="label", data_type="CATEGORICAL"),
    ]
)

VALID_MODE_A_RESPONSE = json.dumps({
    "title": "Logistic Regression Classifier",
    "description": "Classify labels using logistic regression",
    "algorithm_family": "logistic_regression",
    "feature_strategy": "standard scaling",
    "target_column": "label",
})

VALID_MODE_B_3PLANS = json.dumps([
    {"index": 1, "title": "LR", "description": "desc1", "algorithm_family": "logistic_regression", "feature_strategy": "scale", "target_column": "label"},
    {"index": 2, "title": "RF", "description": "desc2", "algorithm_family": "random_forest", "feature_strategy": "none", "target_column": "label"},
    {"index": 3, "title": "XGB", "description": "desc3", "algorithm_family": "gradient_boosting", "feature_strategy": "none", "target_column": "label"},
])

INVALID_2PLANS = json.dumps([
    {"index": 1, "title": "LR", "description": "d", "algorithm_family": "logistic_regression", "feature_strategy": "s", "target_column": "label"},
    {"index": 2, "title": "RF", "description": "d", "algorithm_family": "random_forest", "feature_strategy": "n", "target_column": "label"},
])

DUPLICATE_ALGO_PLANS = json.dumps([
    {"index": 1, "title": "LR1", "description": "d", "algorithm_family": "logistic_regression", "feature_strategy": "s", "target_column": "label"},
    {"index": 2, "title": "LR2", "description": "d", "algorithm_family": "logistic_regression", "feature_strategy": "n", "target_column": "label"},
    {"index": 3, "title": "RF", "description": "d", "algorithm_family": "random_forest", "feature_strategy": "n", "target_column": "label"},
])


def test_mode_a_creates_one_plan():
    provider = MockLLMProvider([VALID_MODE_A_RESPONSE])
    agent = PlanAgent(llm_provider=provider)
    plan = agent.create_plan_mode_a("session-1", SAMPLE_SCHEMA, "label 분류해줘")
    assert plan.algorithm_family == "logistic_regression"
    assert plan.is_selected is True
    assert provider.call_count == 1


def test_mode_b_creates_exactly_3_plans():
    provider = MockLLMProvider([VALID_MODE_B_3PLANS])
    agent = PlanAgent(llm_provider=provider)
    plans = agent.propose_plans_mode_b("session-2", SAMPLE_SCHEMA)
    assert len(plans) == 3


def test_mode_b_ensures_different_algorithms():
    provider = MockLLMProvider([VALID_MODE_B_3PLANS])
    agent = PlanAgent(llm_provider=provider)
    plans = agent.propose_plans_mode_b("session-2", SAMPLE_SCHEMA)
    algos = {p.algorithm_family for p in plans}
    assert len(algos) == 3


def test_mode_b_retries_on_only_2_plans():
    provider = MockLLMProvider([INVALID_2PLANS, VALID_MODE_B_3PLANS])
    agent = PlanAgent(llm_provider=provider)
    plans = agent.propose_plans_mode_b("session-3", SAMPLE_SCHEMA)
    assert len(plans) == 3
    assert provider.call_count == 2


def test_mode_b_retries_on_duplicate_algorithms():
    provider = MockLLMProvider([DUPLICATE_ALGO_PLANS, VALID_MODE_B_3PLANS])
    agent = PlanAgent(llm_provider=provider)
    plans = agent.propose_plans_mode_b("session-4", SAMPLE_SCHEMA)
    assert len(plans) == 3


def test_mode_b_raises_after_max_retries():
    bad_response = INVALID_2PLANS
    provider = MockLLMProvider([bad_response] * 10)
    agent = PlanAgent(llm_provider=provider)
    with pytest.raises(RuntimeError, match="실패"):
        agent.propose_plans_mode_b("session-5", SAMPLE_SCHEMA)
