"""T-009 검증 — Code Agent 단위 테스트 (MockLLMProvider 사용)"""
from app.agents.code_agent import CodeAgent
from app.domain.models import AnalysisPlan, ColumnSpec, DataSchema
from app.providers.base import LLMProvider

GENERATED_CODE = """
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

X = df[['age', 'income']]
y = df['label']
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
model = LogisticRegression()
model.fit(X_train, y_train)
y_pred = model.predict(X_test)
result = {'accuracy': float(accuracy_score(y_test, y_pred)), 'algorithm': 'LogisticRegression', 'n_train': len(X_train), 'n_test': len(X_test)}
"""

FENCED_CODE = f"```python\n{GENERATED_CODE}\n```"

SAMPLE_PLAN = AnalysisPlan(
    id="plan-1",
    session_id="sess-1",
    index=1,
    title="LR Classifier",
    description="Classify label using logistic regression",
    algorithm_family="logistic_regression",
    feature_strategy="scale",
    target_column="label",
    is_selected=True,
)

SAMPLE_SCHEMA = DataSchema(columns=[
    ColumnSpec(name="age", data_type="NUMERIC"),
    ColumnSpec(name="income", data_type="NUMERIC"),
    ColumnSpec(name="label", data_type="CATEGORICAL"),
])


class MockLLMProvider(LLMProvider):
    def __init__(self, response: str) -> None:
        self._response = response
        self.call_count = 0

    def chat(self, messages, temperature=0.2) -> str:
        self.call_count += 1
        return self._response

    def get_model_name(self) -> str:
        return "mock"


def test_generated_code_contains_result_variable():
    provider = MockLLMProvider(GENERATED_CODE)
    agent = CodeAgent(llm_provider=provider)
    code = agent.generate_code(SAMPLE_PLAN, SAMPLE_SCHEMA)
    assert "result" in code.source_code


def test_generated_code_contains_model_variable():
    provider = MockLLMProvider(GENERATED_CODE)
    agent = CodeAgent(llm_provider=provider)
    code = agent.generate_code(SAMPLE_PLAN, SAMPLE_SCHEMA)
    assert "model" in code.source_code


def test_markdown_fences_are_stripped():
    provider = MockLLMProvider(FENCED_CODE)
    agent = CodeAgent(llm_provider=provider)
    code = agent.generate_code(SAMPLE_PLAN, SAMPLE_SCHEMA)
    assert not code.source_code.startswith("```")
    assert not code.source_code.endswith("```")


def test_dependencies_are_detected():
    provider = MockLLMProvider(GENERATED_CODE)
    agent = CodeAgent(llm_provider=provider)
    code = agent.generate_code(SAMPLE_PLAN, SAMPLE_SCHEMA)
    assert "sklearn" in code.dependencies or "pandas" in code.dependencies


def test_plan_id_is_set_on_generated_code():
    provider = MockLLMProvider(GENERATED_CODE)
    agent = CodeAgent(llm_provider=provider)
    code = agent.generate_code(SAMPLE_PLAN, SAMPLE_SCHEMA)
    assert code.plan_id == "plan-1"
