"""EvalAgent 룰 기반 체크 단위 테스트 — 다중공선성 검사 + PII 마스킹"""
import json
from app.agents.eval_agent import EvalAgent, _rule_checks
from app.domain.models import AnalysisResult
from app.providers.base import LLMProvider

BASE_METRICS = {"n_train": 400, "n_test": 100, "accuracy": 0.8}


class _CapturingLLM(LLMProvider):
    """evaluate()가 실제로 LLM에 보내는 user 메시지를 가로채 검사용으로 저장한다."""

    def __init__(self) -> None:
        self.last_user_message = ""

    def chat(self, messages, temperature=0.2) -> str:
        self.last_user_message = next(m["content"] for m in messages if m["role"] == "user")
        return json.dumps({"summary": "ok", "risks": [], "recommendations": []})

    def get_model_name(self) -> str:
        return "mock"


def test_evaluate_masks_pii_looking_class_labels_before_llm_call():
    llm = _CapturingLLM()
    agent = EvalAgent(llm_provider=llm)
    result = AnalysisResult(
        id="r1", session_id="s1",
        metrics={
            **BASE_METRICS,
            "eda": {"class_distribution": {"hong@example.com": 30, "other@x.com": 70}},
        },
    )
    agent.evaluate(result)
    assert "hong@example.com" not in llm.last_user_message
    assert "other@x.com" not in llm.last_user_message


def test_evaluate_passes_normal_labels_unmasked():
    llm = _CapturingLLM()
    agent = EvalAgent(llm_provider=llm)
    result = AnalysisResult(
        id="r1", session_id="s1",
        metrics={**BASE_METRICS, "eda": {"class_distribution": {"생존": 30, "사망": 70}}},
    )
    agent.evaluate(result)
    assert "생존" in llm.last_user_message and "사망" in llm.last_user_message


def test_multicollinearity_flagged_when_high_corr_pairs_present():
    metrics = {
        **BASE_METRICS,
        "eda": {"high_correlation_pairs": [["age", "age_years", 0.98]]},
    }
    checks = _rule_checks(metrics)
    items = {c["item"] for c in checks}
    assert "다중공선성" in items
    corr_check = next(c for c in checks if c["item"] == "다중공선성")
    assert corr_check["level"] == "warning"
    assert "age" in corr_check["msg"] and "age_years" in corr_check["msg"]


def test_no_multicollinearity_check_when_pairs_absent():
    metrics = {**BASE_METRICS, "eda": {"high_correlation_pairs": []}}
    checks = _rule_checks(metrics)
    assert "다중공선성" not in {c["item"] for c in checks}


def test_no_multicollinearity_check_when_eda_missing():
    checks = _rule_checks(dict(BASE_METRICS))
    assert "다중공선성" not in {c["item"] for c in checks}


def test_multicollinearity_message_truncates_to_three_pairs():
    pairs = [["a", "b", 0.95], ["c", "d", 0.93], ["e", "f", 0.92], ["g", "h", 0.91]]
    metrics = {**BASE_METRICS, "eda": {"high_correlation_pairs": pairs}}
    corr_check = next(c for c in _rule_checks(metrics) if c["item"] == "다중공선성")
    assert "외 1쌍" in corr_check["msg"]
