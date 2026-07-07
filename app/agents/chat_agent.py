"""Chat Agent — Logic Layer
분석 결과를 컨텍스트로 사용자 질문에 답변한다.
"""
from __future__ import annotations
import json
from app.domain.models import AnalysisResult
from app.providers.base import LLMProvider


def _build_system(result: AnalysisResult) -> str:
    m = result.metrics
    lines = [
        "당신은 ML 분석 결과를 쉽게 설명하는 데이터 사이언티스트입니다.",
        "아래 분석 결과를 바탕으로 사용자의 질문에 한국어로 친절하게 답하세요.",
        "수치는 구체적으로 인용하고, 비전문가도 이해할 수 있게 설명하세요.",
        "",
        "=== 분석 결과 ===",
        f"알고리즘: {m.get('algorithm', '알 수 없음')}",
        f"학습 샘플: {m.get('n_train', '?')}개 / 테스트 샘플: {m.get('n_test', '?')}개",
    ]

    for key, label in [
        ("accuracy", "정확도"), ("f1", "F1 점수"),
        ("rmse", "RMSE"), ("mae", "MAE"), ("r2", "R²"),
    ]:
        if key in m:
            val = m[key]
            lines.append(f"{label}: {val:.4f}" if isinstance(val, float) else f"{label}: {val}")

    if m.get("model_selection_reason"):
        lines += ["", f"모델 선택 이유: {m['model_selection_reason']}"]

    if m.get("preprocessing"):
        lines += ["", "전처리 단계:"] + [f"  - {s}" for s in m["preprocessing"]]

    if m.get("derived_features"):
        lines += ["", "파생변수:"] + [f"  - {f}" for f in m["derived_features"]]

    if m.get("hyperparameter_tuning"):
        ht = m["hyperparameter_tuning"]
        lines += [
            "",
            f"하이퍼파라미터 튜닝: {ht.get('method', '')}",
            f"최적 파라미터: {json.dumps(ht.get('best_params', {}), ensure_ascii=False)}",
            f"최적 CV 점수: {ht.get('best_cv_score', '?')}",
        ]

    if m.get("eda"):
        eda = m["eda"]
        shape = eda.get("shape", [])
        if shape:
            lines += ["", f"원본 데이터 크기: {shape[0]:,}행 × {shape[1]}열"]
        null_counts = eda.get("null_counts", {})
        if null_counts:
            lines.append(f"결측치 컬럼: {list(null_counts.keys())}")

    if result.feature_importance:
        top = sorted(result.feature_importance.items(), key=lambda x: -x[1])[:10]
        lines += ["", "주요 특성 (상위 10개):"] + [f"  {i+1}. {k}: {v:.4f}" for i, (k, v) in enumerate(top)]

    return "\n".join(lines)


class ChatAgent:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    def chat(self, result: AnalysisResult, history: list[dict]) -> str:
        system = _build_system(result)
        user_messages = [m for m in history if m["role"] != "system"]
        messages = [{"role": "system", "content": system}] + user_messages
        return self._llm.chat(messages, temperature=0.3)
