"""Mode A 페이지 — Presentation Layer
CSV 파일 업로드 + 자연어 목표 입력 → 분류 모델 생성 → 결과 출력
"""
from __future__ import annotations
import os
import streamlit as st
from app.domain.models import ModeARequest
from app.ui.components.data_loader import (
    folders_to_temp, is_folder_ready, is_upload_ready,
    render_folder_section, render_upload_section, upload_to_temp,
)
from app.ui.components.progress import progress_status
from app.ui.components.result_view import show_result
from app.ui.theme import section_header


def render(orchestrator) -> None:
    section_header(
        "📁", "파일 업로드 + 자연어 목표",
        "CSV 파일을 올리고, 원하는 분석 목표를 자연어로 설명하세요.",
    )

    input_mode = st.radio(
        "데이터 입력 방식",
        options=["upload", "folder"],
        format_func=lambda x: "📁 파일 직접 업로드" if x == "upload" else "📂 폴더에서 불러오기",
        key="mode_a_input_mode",
        horizontal=True,
    )

    files, folder_configs, merge_params = [], [], {}
    if input_mode == "upload":
        files, merge_params = render_upload_section("mode_a")
    else:
        folder_configs, merge_params = render_folder_section("mode_a")

    task_type = st.radio(
        "분석 유형",
        options=["classification", "regression"],
        format_func=lambda x: "📊 분류 (Classification)" if x == "classification" else "📈 회귀 (Regression)",
        key="mode_a_task_type",
        horizontal=True,
    )

    objective = st.text_area(
        "분석 목표를 자연어로 입력하세요",
        placeholder="예: 이메일을 긴급/일반/스팸으로 분류해줘" if task_type == "classification" else "예: 다음 달 매출을 예측해줘",
        key="mode_a_objective",
        height=80,
    )

    data_ready = (
        is_upload_ready(files, merge_params)
        if input_mode == "upload"
        else is_folder_ready(folder_configs, merge_params)
    )
    can_run = data_ready and bool(objective.strip())

    if st.button("🚀 분석 시작", key="mode_a_run", disabled=not can_run):
        st.session_state.pop("mode_a_result", None)
        try:
            tmp_path = (
                upload_to_temp(files, merge_params)
                if input_mode == "upload"
                else folders_to_temp(folder_configs, merge_params)
            )
        except Exception as e:
            st.error(f"데이터 로드 오류: {e}")
            return

        try:
            request = ModeARequest(csv_path=tmp_path, objective_text=objective, task_type=task_type)
            with progress_status("🤖 Mode A 분석 진행 중...") as notify:
                orch_result = orchestrator.run_mode_a(request=request, progress=notify)
            if orch_result.status == "completed":
                st.session_state["mode_a_result"] = orch_result.result
            else:
                st.error(f"분석 실패: {orch_result.error_message}")
        finally:
            os.unlink(tmp_path)

    if st.session_state.get("mode_a_result"):
        show_result(st.session_state["mode_a_result"], orchestrator)
