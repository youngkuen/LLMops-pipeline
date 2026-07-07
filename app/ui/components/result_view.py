"""분석 결과 시각화 컴포넌트 — Presentation Layer"""
from __future__ import annotations
import streamlit as st
import pandas as pd
from app.domain.models import AnalysisResult

_CORE_KEYS = {"accuracy", "f1", "f1_score", "rmse", "mae", "r2", "n_train", "n_test", "algorithm"}

_METRIC_LABELS = {
    "accuracy": "정확도",
    "f1": "F1 점수",
    "f1_score": "F1 점수",
    "rmse": "RMSE",
    "mae": "MAE",
    "r2": "R² (결정계수)",
    "n_train": "학습 샘플 수",
    "n_test": "테스트 샘플 수",
    "algorithm": "알고리즘",
}

_STAT_LABELS = {
    "mean": "평균",
    "std": "표준편차",
    "min": "최솟값",
    "max": "최댓값",
}


def show_result(result: AnalysisResult, orchestrator=None) -> None:
    st.subheader("📊 분석 결과")
    m = result.metrics

    _show_cost(m.get("__cost"))

    tab_diag, tab_perf, tab_eda, tab_prep, tab_model, tab_code = st.tabs([
        "🩺 결과 진단", "📈 성능 지표", "🔍 EDA", "🔧 전처리 & 파생변수", "🤖 모델 선택 & 튜닝", "💻 생성된 코드",
    ])

    with tab_diag:
        _show_diagnosis(m.get("__eval"))

    with tab_perf:
        _show_performance(m, result.feature_importance)

    with tab_eda:
        _show_eda(m.get("eda", {}))

    with tab_prep:
        _show_preprocessing(m.get("preprocessing", []), m.get("derived_features", []))

    with tab_model:
        _show_model_info(
            m.get("model_selection_reason", ""),
            m.get("hyperparameter_tuning", {}),
        )

    with tab_code:
        if result.generated_code:
            st.code(result.generated_code, language="python")

    if orchestrator is not None:
        from app.ui.components.result_chat import show_chat
        show_chat(result, orchestrator)


def _show_cost(cost: dict | None) -> None:
    if not cost:
        return
    usd = cost.get("usd", 0.0)
    tok_in = cost.get("input_tokens", 0)
    tok_out = cost.get("output_tokens", 0)
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;
            padding:14px 18px;border-radius:14px;margin-bottom:10px;
            background:rgba(34,211,238,0.10);border:1px solid rgba(34,211,238,0.35);">
            <span style="font-size:20px;">💰</span>
            <div>
                <span style="font-size:0.72rem;font-weight:700;letter-spacing:0.1em;
                    text-transform:uppercase;color:#94a3b8;">이번 분석 LLM 비용 (누적)</span>
                <div style="font-size:1.25rem;font-weight:800;color:#67e8f9;">${usd:.4f}</div>
            </div>
            <div style="margin-left:auto;color:#94a3b8;font-size:0.82rem;text-align:right;">
                입력 {tok_in:,} 토큰<br>출력 {tok_out:,} 토큰</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _show_diagnosis(eval_data: dict | None) -> None:
    if not eval_data:
        st.info("결과 진단 정보가 없습니다.")
        return

    verdict = eval_data.get("verdict", "")
    summary = eval_data.get("summary", "")
    verdict_config = {
        "신뢰 가능":  ("✅", "#10b981", "rgba(16,185,129,0.14)", "rgba(16,185,129,0.45)"),
        "주의 필요":  ("⚠️", "#f59e0b", "rgba(245,158,11,0.14)", "rgba(245,158,11,0.45)"),
        "신뢰 어려움": ("❌", "#ef4444", "rgba(239,68,68,0.14)", "rgba(239,68,68,0.45)"),
    }
    icon, accent, bg, glow = verdict_config.get(
        verdict, ("ℹ️", "#6366f1", "rgba(99,102,241,0.14)", "rgba(99,102,241,0.45)")
    )

    summary_html = (
        f"<div style='margin-top:10px;color:#cbd5e1;font-size:0.96rem;"
        f"line-height:1.6;'>{summary}</div>" if summary else ""
    )
    st.markdown(
        f"""
        <div style="padding:20px 22px;border-radius:16px;margin-bottom:8px;
            background:{bg};border:1px solid {glow};
            box-shadow:0 8px 28px rgba(2,6,23,0.4), 0 0 22px {bg};">
            <div style="display:flex;align-items:center;gap:10px;">
                <span style="font-size:24px;">{icon}</span>
                <span style="font-size:0.72rem;font-weight:700;letter-spacing:0.12em;
                    text-transform:uppercase;color:#94a3b8;">종합 판정</span>
                <span style="font-size:1.25rem;font-weight:800;color:{accent};
                    margin-left:2px;">{verdict}</span>
            </div>
            {summary_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    checks = eval_data.get("checks", [])
    if checks:
        st.markdown("**세부 진단 항목**")
        level_icon = {"ok": "✅", "warning": "⚠️", "critical": "❌"}
        for c in checks:
            icon_c = level_icon.get(c["level"], "•")
            st.markdown(f"{icon_c} **{c['item']}** — {c['msg']}")

    risks = eval_data.get("risks", [])
    if risks:
        st.divider()
        st.markdown("**실무 사용 시 리스크**")
        for r in risks:
            st.markdown(f"- {r}")

    recs = eval_data.get("recommendations", [])
    if recs:
        st.divider()
        st.markdown("**개선 및 다음 단계 제안**")
        for i, r in enumerate(recs, 1):
            st.markdown(f"{i}. {r}")


def _show_performance(m: dict, feature_importance: dict | None) -> None:
    core = {k: v for k, v in m.items() if k in _CORE_KEYS}
    if core:
        cols = st.columns(len(core))
        for col, (k, v) in zip(cols, core.items()):
            label = _METRIC_LABELS.get(k, k.replace("_", " ").title())
            col.metric(label, f"{v:.4f}" if isinstance(v, float) else str(v))

    if feature_importance:
        st.subheader("🔑 Feature Importance")
        fi_df = (
            pd.DataFrame.from_dict(feature_importance, orient="index", columns=["importance"])
            .sort_values("importance", ascending=False)
            .head(15)
        )
        st.bar_chart(fi_df)


def _show_eda(eda: dict) -> None:
    if not eda:
        st.info("EDA 정보가 없습니다.")
        return

    shape = eda.get("shape", [])
    if shape:
        st.markdown(f"**데이터 크기:** {shape[0]:,}행 × {shape[1]}열")

    class_dist = eda.get("class_distribution", {})
    if class_dist:
        st.markdown("**클래스 분포 (타겟 변수)**")
        dist_df = pd.DataFrame.from_dict(class_dist, orient="index", columns=["건수"])
        st.bar_chart(dist_df)

    target_stats = eda.get("target_stats", {})
    if target_stats:
        st.markdown("**타겟 변수 통계 (회귀)**")
        st.dataframe(
            pd.DataFrame([target_stats]).rename(columns=_STAT_LABELS),
            use_container_width=True,
        )

    null_counts = eda.get("null_counts", {})
    if null_counts:
        st.markdown("**결측치**")
        st.dataframe(
            pd.DataFrame.from_dict(null_counts, orient="index", columns=["결측 수"]),
            use_container_width=True,
        )
    else:
        st.success("결측치 없음")

    numeric_stats = eda.get("numeric_stats", {})
    if numeric_stats:
        st.markdown("**수치형 변수 기초 통계**")
        stats_df = pd.DataFrame(numeric_stats).T.round(4)
        stats_df = stats_df.rename(columns=_STAT_LABELS)
        st.dataframe(stats_df, use_container_width=True)


def _show_preprocessing(preprocessing: list, derived_features: list) -> None:
    st.markdown("**전처리 단계**")
    if preprocessing:
        for i, step in enumerate(preprocessing, 1):
            st.markdown(f"{i}. {step}")
    else:
        st.info("전처리 정보가 없습니다.")

    st.divider()

    st.markdown("**파생변수 (Feature Engineering)**")
    if derived_features:
        for feat in derived_features:
            st.markdown(f"- `{feat}`")
    else:
        st.info("추가된 파생변수 없음")


def _show_model_info(reason: str, tuning: dict) -> None:
    if reason:
        st.markdown("**모델 선택 이유**")
        st.info(reason)

    st.divider()

    st.markdown("**하이퍼파라미터 튜닝**")
    if not tuning:
        st.info("튜닝 정보가 없습니다.")
        return

    method = tuning.get("method", "")
    cv_score = tuning.get("best_cv_score")
    if method:
        st.markdown(f"방법: `{method}`")
    if cv_score is not None:
        st.metric("최적 교차검증 점수", f"{float(cv_score):.4f}")

    best_params = tuning.get("best_params", {})
    if best_params:
        st.markdown("**최적 파라미터**")
        st.json(best_params)

    param_grid = tuning.get("param_grid", {})
    if param_grid:
        with st.expander("탐색한 파라미터 범위"):
            st.json(param_grid)
