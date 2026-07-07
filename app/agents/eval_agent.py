"""Eval Agent — Logic Layer
분석 결과의 신뢰성·실용성을 룰 기반 + LLM으로 평가한다.
"""
from __future__ import annotations
import json
import re
from app.domain.models import AnalysisResult
from app.loaders.anonymizer import mask_text
from app.providers.base import LLMProvider

# ── 룰 기반 체크 ──────────────────────────────────────────────────────────────

def _rule_checks(m: dict, generated_code: str = "") -> list[dict]:
    """결과 딕셔너리를 보고 경고/정보 항목 목록을 반환한다."""
    checks = []
    n_train = m.get("n_train", 0)
    n_test = m.get("n_test", 0)
    n_total = n_train + n_test

    # 샘플 수
    if n_total < 100:
        checks.append({"level": "critical", "item": "샘플 수",
                       "msg": f"전체 {n_total:,}개 — 통계적으로 의미 있는 모델 학습이 어렵습니다. 데이터를 더 수집하세요."})
    elif n_total < 500:
        checks.append({"level": "warning", "item": "샘플 수",
                       "msg": f"전체 {n_total:,}개 — 결과의 일반화 가능성이 제한됩니다."})
    else:
        checks.append({"level": "ok", "item": "샘플 수",
                       "msg": f"전체 {n_total:,}개 — 충분한 수준입니다."})

    # 분류 지표
    accuracy = m.get("accuracy")
    if accuracy is not None:
        if accuracy > 0.995:
            checks.append({"level": "critical", "item": "정확도 과도",
                           "msg": f"정확도 {accuracy:.1%} — 비현실적으로 높습니다. 타겟 변수가 피처에 포함됐거나 데이터 누수(data leakage)를 의심하세요."})
        elif accuracy < 0.55:
            checks.append({"level": "critical", "item": "정확도 부족",
                           "msg": f"정확도 {accuracy:.1%} — 무작위 예측과 비슷한 수준입니다. 실용적 활용이 어렵습니다."})
        elif accuracy < 0.70:
            checks.append({"level": "warning", "item": "정확도",
                           "msg": f"정확도 {accuracy:.1%} — 개선 여지가 있습니다."})
        else:
            checks.append({"level": "ok", "item": "정확도",
                           "msg": f"정확도 {accuracy:.1%} — 실용적 수준입니다."})

    # 클래스 불균형
    class_dist = m.get("eda", {}).get("class_distribution", {})
    preprocessing = [s.lower() for s in m.get("preprocessing", [])]
    code_lower = generated_code.lower()
    smote_applied = (
        any("smote" in s for s in preprocessing)
        or "smote(" in code_lower
    )
    balanced_applied = (
        any("balanced" in s for s in preprocessing)
        or "class_weight='balanced'" in generated_code
        or 'class_weight="balanced"' in generated_code
    )

    if class_dist and len(class_dist) >= 2:
        counts = sorted(class_dist.values())
        ratio = counts[-1] / max(counts[0], 1)
        if ratio > 10:
            if smote_applied:
                checks.append({"level": "ok", "item": "클래스 불균형",
                               "msg": f"불균형 비율 약 {ratio:.0f}:1이었으나 SMOTE 오버샘플링이 적용되었습니다."})
            elif balanced_applied:
                checks.append({"level": "warning", "item": "클래스 불균형",
                               "msg": f"불균형 비율 약 {ratio:.0f}:1 — class_weight=balanced가 적용되었습니다. 심각한 불균형이므로 SMOTE도 고려하세요."})
            else:
                checks.append({"level": "critical", "item": "클래스 불균형",
                               "msg": f"불균형 비율 약 {ratio:.0f}:1 — 정확도보다 F1 점수를 기준으로 판단하세요. SMOTE 등 오버샘플링을 고려하세요."})
        elif ratio > 3:
            if smote_applied or balanced_applied:
                checks.append({"level": "ok", "item": "클래스 불균형",
                               "msg": f"불균형 비율 약 {ratio:.0f}:1이었으나 불균형 처리가 적용되었습니다."})
            else:
                checks.append({"level": "warning", "item": "클래스 불균형",
                               "msg": f"불균형 비율 약 {ratio:.0f}:1 — 소수 클래스 예측이 불리할 수 있습니다."})

    # 회귀 지표
    r2 = m.get("r2")
    if r2 is not None:
        if r2 > 0.995:
            checks.append({"level": "critical", "item": "R² 과도",
                           "msg": f"R² {r2:.4f} — 비현실적으로 높습니다. 데이터 누수를 확인하세요."})
        elif r2 < 0.0:
            checks.append({"level": "critical", "item": "R² 음수",
                           "msg": f"R² {r2:.4f} — 평균 예측보다 성능이 낮습니다. 피처 선택이나 데이터를 재검토하세요."})
        elif r2 < 0.3:
            checks.append({"level": "critical", "item": "설명력 부족",
                           "msg": f"R² {r2:.4f} — 설명력이 매우 낮습니다. 실용적 활용이 어렵습니다."})
        elif r2 < 0.6:
            checks.append({"level": "warning", "item": "설명력",
                           "msg": f"R² {r2:.4f} — 설명력이 다소 낮습니다. 피처 엔지니어링을 고려하세요."})
        else:
            checks.append({"level": "ok", "item": "설명력",
                           "msg": f"R² {r2:.4f} — 적절한 수준입니다."})

    # 다중공선성 (피처 간 높은 상관관계)
    high_corr = m.get("eda", {}).get("high_correlation_pairs", [])
    if high_corr:
        top = high_corr[:3]
        pairs_str = ", ".join(f"{a}~{b}({c:.2f})" for a, b, c in top)
        more = f" 외 {len(high_corr) - 3}쌍" if len(high_corr) > 3 else ""
        checks.append({
            "level": "warning", "item": "다중공선성",
            "msg": f"높은 상관관계 피처 쌍 발견: {pairs_str}{more} — "
                   "회귀 계수처럼 개별 피처의 영향력을 해석해야 한다면 계수가 불안정해질 수 있습니다. "
                   "한쪽 피처 제거나 PCA를 고려하세요."
        })

    # 피처 중요도 쏠림 (데이터 누수 시그널)
    fi = m.get("__feature_importance", {})
    if fi and len(fi) >= 2:
        total = sum(fi.values())
        top_ratio = max(fi.values()) / total if total > 0 else 0
        if top_ratio > 0.85:
            top_feat = max(fi, key=fi.get)
            checks.append({"level": "warning", "item": "피처 쏠림",
                           "msg": f"'{top_feat}' 피처가 중요도의 {top_ratio:.0%}를 차지합니다. 해당 피처가 타겟과 직접 연관된 변수는 아닌지 확인하세요."})

    return checks


def _overall_verdict(checks: list[dict]) -> str:
    levels = {c["level"] for c in checks}
    if "critical" in levels:
        return "신뢰 어려움"
    if "warning" in levels:
        return "주의 필요"
    return "신뢰 가능"


# ── LLM 해석 ──────────────────────────────────────────────────────────────────

_SYSTEM = """당신은 머신러닝 결과의 실용성을 평가하는 시니어 데이터 사이언티스트입니다.
주어진 분석 결과와 진단 항목을 보고, 비즈니스 담당자(비전문가)가 이해할 수 있도록 한국어로 평가해주세요.

반드시 아래 JSON 형식으로만 응답하세요 (마크다운 불필요):
{
  "summary": "이 결과를 실무에서 어떻게 해석해야 하는지 2~3문장 평어체 설명",
  "risks": ["실제 사용 시 주의해야 할 리스크 1", "리스크 2"],
  "recommendations": ["개선하거나 다음 단계로 시도할 것 1", "추천 사항 2"]
}"""


class EvalAgent:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    def evaluate(self, result: AnalysisResult) -> dict:
        m = result.metrics
        checks = _rule_checks(m, generated_code=result.generated_code or "")
        verdict = _overall_verdict(checks)

        # 타겟 라벨 값이 실수로 개인정보(이메일 등)일 경우를 대비해 LLM 전달 전 마스킹
        class_dist = m.get("eda", {}).get("class_distribution")
        masked_class_dist = (
            {mask_text(str(label)): count for label, count in class_dist.items()}
            if class_dist else None
        )

        # LLM에 넘길 컨텍스트
        context = {
            "verdict": verdict,
            "metrics": {k: v for k, v in m.items()
                        if k in ("accuracy", "f1", "rmse", "mae", "r2", "n_train", "n_test", "algorithm")},
            "rule_checks": [{"level": c["level"], "msg": c["msg"]} for c in checks],
            "eda_shape": m.get("eda", {}).get("shape"),
            "class_distribution": masked_class_dist,
            "model_selection_reason": m.get("model_selection_reason", ""),
        }
        user_msg = f"분석 결과:\n{json.dumps(context, ensure_ascii=False, indent=2)}"

        try:
            raw = self._llm.chat(
                [{"role": "system", "content": _SYSTEM},
                 {"role": "user", "content": user_msg}],
                temperature=0.2,
            )
            raw = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
            llm_out = json.loads(raw)
        except Exception:
            llm_out = {
                "summary": "LLM 해석 생성 중 오류가 발생했습니다. 위 진단 항목을 참고하세요.",
                "risks": [],
                "recommendations": [],
            }

        return {
            "verdict": verdict,
            "checks": checks,
            "summary": llm_out.get("summary", ""),
            "risks": llm_out.get("risks", []),
            "recommendations": llm_out.get("recommendations", []),
        }
