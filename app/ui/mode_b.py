"""Mode B 페이지 — Presentation Layer
CSV 파일 업로드 → 컬럼 자동 감지 → 질문지형 폼(컬럼별 설명·타겟 지정)
→ 3가지 분석 방향 제안 → 선택 → 결과 출력

교수 자문(2026-07): 자유 텍스트 입력을 '스키마 기반 동적 폼'으로 전환하여 입력을 제어.
폼은 데이터 형식이 아니라 '로드된 스키마'에 의존하므로, 향후 CSV 외 형식 확장에도 재사용된다.
"""
from __future__ import annotations
import streamlit as st
from app.domain.models import ColumnSpec, ModeBRequest
from app.loaders.anonymizer import PII_LABELS_KR, detect_pii_columns
from app.loaders.csv_loader import infer_schema, load_dataframe
from app.loaders.spec_loader import extract_spec_text
from app.ui.components.data_loader import (
    folders_to_temp, is_folder_ready, is_upload_ready,
    render_folder_section, render_upload_section, upload_to_temp,
)
from app.ui.components.progress import progress_status
from app.ui.components.result_view import show_result
from app.ui.theme import section_header

_DTYPE_LABELS = {
    "NUMERIC": "숫자",
    "CATEGORICAL": "범주",
    "TEXT": "텍스트",
    "DATETIME": "날짜/시간",
    "BOOLEAN": "참/거짓",
}

_TASK_LABELS = {
    "classification": "📊 분류 (범주 맞히기)",
    "regression": "📈 회귀 (숫자 맞히기)",
    "timeseries": "⏱️ 시계열 예측 (미래값 예측)",
}


def render(orchestrator) -> None:
    section_header(
        "📋", "데이터 명세서 입력 + 분석 방향 선택",
        "데이터를 불러오면 컬럼을 자동 감지합니다. 각 컬럼의 의미와 예측 목표를 지정하면 "
        "AI가 3가지 분석 방향을 제안하고, 선택한 방향으로 모델을 만들어 드립니다.",
    )

    input_mode = st.radio(
        "데이터 입력 방식",
        options=["upload", "folder"],
        format_func=lambda x: "📁 파일 직접 업로드" if x == "upload" else "📂 폴더에서 불러오기",
        key="mode_b_input_mode",
        horizontal=True,
    )

    files, folder_configs, merge_params = [], [], {}
    if input_mode == "upload":
        files, merge_params = render_upload_section("mode_b")
    else:
        folder_configs, merge_params = render_folder_section("mode_b")

    data_ready = (
        is_upload_ready(files, merge_params)
        if input_mode == "upload"
        else is_folder_ready(folder_configs, merge_params)
    )

    # 명세서 파일(선택) — 올리면 컬럼 설명·타겟·분석유형을 자동으로 채운다
    spec_file = st.file_uploader(
        "📄 명세서 파일 (선택) — 컬럼 설명이 담긴 문서를 올리면 자동으로 채워드립니다",
        type=["txt", "md", "csv", "tsv", "xlsx", "xls"],
        key="mode_b_spec_file",
        help="데이터 딕셔너리, 컬럼 설명서 등. 표·문장 형식 모두 가능합니다.",
    )

    # ── 1단계: 데이터 불러오기 → 컬럼 자동 감지 (+ 명세서 자동 채움) ────────
    if st.button("📥 데이터 불러오기 / 컬럼 감지", key="mode_b_load", disabled=not data_ready):
        for k in ("mode_b_plans", "mode_b_session_id", "mode_b_result"):
            st.session_state.pop(k, None)

        with st.status("📥 데이터 처리 중...", expanded=True) as status:
            try:
                st.write("📂 데이터 파일 읽는 중...")
                tmp_path = (
                    upload_to_temp(files, merge_params)
                    if input_mode == "upload"
                    else folders_to_temp(folder_configs, merge_params)
                )
                df = load_dataframe(tmp_path)
                st.write(f"🔍 컬럼 감지 중... ({len(df):,}행 × {len(df.columns)}열)")
                schema = infer_schema(df)
            except Exception as e:
                status.update(label="❌ 데이터 로드 실패", state="error")
                st.error(f"데이터 로드 오류: {e}")
                return

            # 내부 메타 컬럼(__로 시작)은 제외
            visible = [c for c in schema.columns if not c.name.startswith("__")]
            st.session_state["mode_b_csv_path"] = tmp_path
            st.session_state["mode_b_detected"] = [
                {"name": c.name, "data_type": c.data_type} for c in visible
            ]
            st.session_state["mode_b_nrows"] = len(df)
            st.session_state["mode_b_spec_applied"] = False

            pii_map = detect_pii_columns(df, [c.name for c in visible])
            st.session_state["mode_b_pii"] = pii_map
            st.write(f"✅ 컬럼 {len(visible)}개 감지 완료")
            if pii_map:
                kinds = ", ".join(f"{c}({PII_LABELS_KR.get(k, k)})" for c, k in pii_map.items())
                st.write(f"  └─ 🔒 민감정보 의심 컬럼 {len(pii_map)}개 발견: {kinds}")

            # 명세서가 있으면 LLM으로 설명·타겟·분석유형을 자동 채움 (위젯 렌더 전 세팅)
            if spec_file is not None:
                st.write("📄 명세서 분석 중... (AI가 컬럼 설명을 읽고 있습니다)")
                try:
                    spec_text = extract_spec_text(spec_file.name, spec_file.getvalue())
                    parsed = orchestrator.parse_spec([c.name for c in visible], spec_text)
                    for name, info in parsed["columns"].items():
                        st.session_state[f"mode_b_desc_{name}"] = info["description"]
                    target = next(
                        (n for n, i in parsed["columns"].items() if i["is_target"]), None
                    )
                    if target:
                        st.session_state["mode_b_target"] = target
                    if parsed["task_type"]:
                        st.session_state["mode_b_task_type"] = parsed["task_type"]
                    st.session_state["mode_b_spec_applied"] = bool(parsed["columns"])
                    if parsed["columns"]:
                        st.write(f"✅ 명세서에서 {len(parsed['columns'])}개 컬럼 정보 추출 완료")
                    else:
                        st.write("⚠️ 명세서에서 매칭되는 컬럼을 찾지 못했습니다 (수동 입력 가능)")
                    _c = parsed.get("cost")
                    if _c and _c.get("usd"):
                        st.write(
                            f"  └─ 💰 명세서 분석 비용: ${_c['usd']:.4f} · "
                            f"입력 {_c['input_tokens']:,} / 출력 {_c['output_tokens']:,} 토큰"
                        )
                except Exception as e:
                    st.write("⚠️ 명세서 자동 분석 실패 (수동 입력 가능)")
                    st.warning(f"명세서 분석 오류: {e}")

            status.update(label="✅ 준비 완료! 아래에서 컬럼을 확인하세요.", state="complete")

    detected = st.session_state.get("mode_b_detected")

    # ── 2단계: 질문지형 폼 (컬럼별 설명 + 타겟 + 분석 유형) ─────────────
    if detected:
        st.divider()
        st.markdown(f"**감지된 컬럼 {len(detected)}개** · 데이터 {st.session_state.get('mode_b_nrows', 0):,}행")
        if st.session_state.get("mode_b_spec_applied"):
            st.success("📄 명세서를 읽어 컬럼 설명·타겟·분석 유형을 자동으로 채웠습니다. 확인 후 필요하면 수정하세요.")
        else:
            st.caption("각 컬럼의 의미를 적고, 예측하려는 타겟 컬럼과 분석 유형을 지정하세요. (명세서 파일을 올리면 자동으로 채워집니다)")

        col_names = [c["name"] for c in detected]
        target_col = st.selectbox(
            "🎯 예측할 타겟 컬럼 (무엇을 맞히고 싶나요?)",
            options=col_names,
            key="mode_b_target",
        )

        task_type = st.radio(
            "분석 유형",
            options=["classification", "regression", "timeseries"],
            format_func=lambda x: _TASK_LABELS[x],
            key="mode_b_task_type",
            horizontal=True,
        )

        time_column = None
        if task_type == "timeseries":
            time_column = st.selectbox(
                "⏱️ 시간 컬럼 (날짜·시간이 담긴 컬럼을 고르세요)",
                options=col_names,
                key="mode_b_time_col",
            )
            st.caption("이 컬럼을 기준으로 과거값(lag)·이동평균을 만들어 미래를 예측합니다.")

        pii_map = st.session_state.get("mode_b_pii", {})
        if pii_map:
            st.warning(
                f"🔒 민감정보로 의심되는 컬럼 {len(pii_map)}개가 있습니다. "
                "AI 분석 시 실제 값은 마스킹되어 전달되지만, 필요 없다면 제외를 고려하세요."
            )

        st.markdown("**컬럼별 설명**")
        for c in detected:
            name, dtype = c["name"], c["data_type"]
            label = _DTYPE_LABELS.get(dtype, dtype or "?")
            is_target = name == target_col
            pii_kind = pii_map.get(name)
            c1, c2 = st.columns([1, 2])
            with c1:
                tag = " 🎯타겟" if is_target else ""
                pii_tag = f" 🔒{PII_LABELS_KR.get(pii_kind, pii_kind)}" if pii_kind else ""
                st.markdown(f"`{name}`  ·  {label}{tag}{pii_tag}")
            with c2:
                st.text_input(
                    f"{name} 설명",
                    key=f"mode_b_desc_{name}",
                    placeholder="예: 승객 나이 / 티켓 요금 / 생존 여부(0·1)",
                    label_visibility="collapsed",
                )

        if st.button("💡 분석 방향 3가지 제안받기", key="mode_b_propose"):
            columns = [
                ColumnSpec(
                    name=c["name"],
                    description=st.session_state.get(f"mode_b_desc_{c['name']}", "").strip(),
                    data_type=c["data_type"],
                    is_target=(c["name"] == target_col),
                    pii_kind=pii_map.get(c["name"]),
                )
                for c in detected
            ]
            for k in ("mode_b_plans", "mode_b_session_id", "mode_b_result"):
                st.session_state.pop(k, None)

            request = ModeBRequest(
                csv_path=st.session_state["mode_b_csv_path"],
                schema_columns=columns,
                task_type=task_type,
                time_column=time_column,
            )
            with progress_status("🤖 분석 방향 탐색 중...") as notify:
                result = orchestrator.propose_plans(request=request, progress=notify)

            if result.status == "awaiting_selection":
                st.session_state["mode_b_plans"] = result.plans
                st.session_state["mode_b_session_id"] = result.session_id
            else:
                st.error(f"제안 실패: {result.error_message}")

    # ── 3단계: 방향 선택 + 실행 ──────────────────────────────────────────
    plans = st.session_state.get("mode_b_plans")
    session_id = st.session_state.get("mode_b_session_id")

    if plans:
        st.divider()
        st.subheader("📌 분석 방향 선택")
        options = {f"{p.index}. {p.title} ({p.algorithm_family})": p.id for p in plans}
        selected_label = st.radio("하나를 선택하세요", list(options.keys()), key="mode_b_selected")
        selected_plan_id = options[selected_label]

        selected_plan = next(p for p in plans if p.id == selected_plan_id)
        st.info(f"**{selected_plan.title}**\n\n{selected_plan.description}")

        if st.button("🚀 선택한 방향으로 분석 시작", key="mode_b_run"):
            st.session_state.pop("mode_b_result", None)
            with progress_status("🤖 모델 학습 중...") as notify:
                exec_result = orchestrator.execute_selected_plan(
                    session_id=session_id,
                    plan_id=selected_plan_id,
                    progress=notify,
                )
            if exec_result.status == "completed":
                st.session_state["mode_b_result"] = exec_result.result
            else:
                st.error(f"분석 실패: {exec_result.error_message}")

    if st.session_state.get("mode_b_result"):
        show_result(st.session_state["mode_b_result"], orchestrator)
