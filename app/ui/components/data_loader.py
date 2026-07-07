"""데이터 불러오기 UI 컴포넌트 — Presentation Layer
파일 업로드 / 폴더 경로 두 가지 입력 방식을 공통으로 제공한다.
"""
from __future__ import annotations
import os
import tempfile
import pandas as pd
import streamlit as st
from app.loaders.csv_loader import (
    concat_dataframes,
    join_dataframes,
    load_folder,
    read_uploaded_table,
    time_join_dataframes,
)

_DIRECTION_LABELS = {
    "backward": "이전 시점 기준 — 왼쪽 시간 이전의 가장 최근 값으로 매칭",
    "nearest":  "가장 가까운 시점 — 앞뒤 중 가장 가까운 값으로 매칭",
    "forward":  "이후 시점 기준 — 왼쪽 시간 이후의 가장 빠른 값으로 매칭",
}
_TOLERANCE_UNITS = {"초": 1, "분": 60, "시간": 3600}


# ── 파일 업로드 모드 ──────────────────────────────────────────────────────────

def render_upload_section(prefix: str) -> tuple[list, dict]:
    """파일 업로드 UI를 그린다. (files, merge_params) 반환."""
    files = st.file_uploader(
        "데이터 파일 업로드 (여러 개 선택 가능)",
        type=["csv", "txt", "tsv", "xlsx", "xls", "xlsm", "json"],
        key=f"{prefix}_file",
        accept_multiple_files=True,
        help="지원 형식: CSV · TSV · TXT · Excel(xlsx/xls) · JSON",
    )
    merge_params: dict = {"strategy": "concat"}

    if len(files) > 1:
        st.caption(f"선택된 파일: {', '.join(f.name for f in files)}")
        strategy = st.radio(
            "파일 병합 방식",
            options=["concat", "join", "time"],
            format_func=lambda x: {
                "concat": "행 결합 — 같은 컬럼 구조의 파일을 위아래로 합치기",
                "join":   "키 기반 병합 — 공통 컬럼으로 Join",
                "time":   "시간 기반 병합 — 시간 컬럼 기준으로 가장 가까운 값 매칭",
            }[x],
            key=f"{prefix}_merge_strategy",
            horizontal=True,
        )
        merge_params["strategy"] = strategy

        if strategy == "join":
            merge_params["key_col"] = st.text_input("Join 기준 컬럼명", key=f"{prefix}_key_col")

        elif strategy == "time":
            if len(files) > 2:
                st.warning("시간 기반 병합은 파일 2개만 지원합니다. 처음 두 파일만 사용됩니다.")
            c1, c2 = st.columns(2)
            with c1:
                merge_params["left_time_col"] = st.text_input(
                    f"'{files[0].name}' 시간 컬럼명", key=f"{prefix}_left_time"
                )
            with c2:
                merge_params["right_time_col"] = st.text_input(
                    f"'{files[1].name}' 시간 컬럼명", key=f"{prefix}_right_time"
                )
            merge_params["direction"] = st.radio(
                "매칭 방향", list(_DIRECTION_LABELS.keys()),
                format_func=lambda x: _DIRECTION_LABELS[x],
                key=f"{prefix}_direction",
            )
            merge_params["tolerance_seconds"] = _tolerance_ui(prefix)

    return files, merge_params


def is_upload_ready(files: list, merge_params: dict) -> bool:
    if not files:
        return False
    s = merge_params.get("strategy", "concat")
    if s == "join" and not merge_params.get("key_col", "").strip():
        return False
    if s == "time" and not (
        merge_params.get("left_time_col", "").strip()
        and merge_params.get("right_time_col", "").strip()
    ):
        return False
    return True


def upload_to_temp(files: list, merge_params: dict) -> str:
    dfs = [read_uploaded_table(f) for f in files]
    strategy = merge_params.get("strategy", "concat")

    if len(dfs) == 1 or strategy == "concat":
        df = concat_dataframes(dfs) if len(dfs) > 1 else dfs[0]
    elif strategy == "join":
        df = join_dataframes(dfs, merge_params["key_col"].strip())
    else:
        df = time_join_dataframes(
            left=dfs[0], right=dfs[1],
            left_time_col=merge_params["left_time_col"].strip(),
            right_time_col=merge_params["right_time_col"].strip(),
            direction=merge_params.get("direction", "nearest"),
            tolerance_seconds=merge_params.get("tolerance_seconds"),
        )

    return _df_to_temp(df)


# ── 폴더 불러오기 모드 ────────────────────────────────────────────────────────

def render_folder_section(prefix: str) -> tuple[list[dict], dict]:
    """폴더 경로 입력 UI를 그린다. (folder_configs, merge_params) 반환."""
    count_key = f"{prefix}_folder_count"
    if count_key not in st.session_state:
        st.session_state[count_key] = 1

    st.caption("각 폴더 안의 모든 CSV 파일을 자동으로 읽어 합칩니다.")

    folder_configs: list[dict] = []
    for i in range(st.session_state[count_key]):
        p_col, dt_col = st.columns([4, 3])
        with p_col:
            path = st.text_input(
                f"폴더 경로 {i + 1}",
                placeholder=r"예: C:\data\Sampling",
                key=f"{prefix}_folder_path_{i}",
            )
        with dt_col:
            dt_mode = st.radio(
                "datetime 방식",
                options=["split", "single"],
                format_func=lambda x: "날짜+시간 (두 컬럼)" if x == "split" else "통합 datetime (한 컬럼)",
                key=f"{prefix}_dt_mode_{i}",
                horizontal=True,
            )

        if dt_mode == "split":
            d_col, t_col = st.columns(2)
            with d_col:
                date_col = st.text_input("날짜 컬럼", value="DATE", key=f"{prefix}_date_col_{i}")
            with t_col:
                time_col = st.text_input("시간 컬럼", value="TIME", key=f"{prefix}_time_col_{i}")
            datetime_col = ""
        else:
            datetime_col = st.text_input(
                "datetime 컬럼명",
                placeholder="예: TimeString, timestamp, datetime",
                key=f"{prefix}_datetime_col_{i}",
            )
            date_col, time_col = "DATE", "TIME"

        if path.strip():
            folder_configs.append({
                "path": path.strip(),
                "date_col": date_col.strip() if dt_mode == "split" else "DATE",
                "time_col": time_col.strip() if dt_mode == "split" else "TIME",
                "datetime_col": datetime_col.strip(),
            })

    add_col, _ = st.columns([1, 5])
    with add_col:
        if st.session_state[count_key] < 4:
            if st.button("＋ 폴더 추가", key=f"{prefix}_add_folder"):
                st.session_state[count_key] += 1
                st.rerun()

    merge_params: dict = {"strategy": "time"}
    if len(folder_configs) > 1:
        strategy = st.radio(
            "폴더 간 병합 방식",
            options=["time", "concat", "join"],
            format_func=lambda x: {
                "time":   "시간 기반 병합 (권장) — __datetime 기준으로 가장 가까운 값 매칭",
                "concat": "행 결합 — 같은 컬럼 구조의 폴더를 위아래로 합치기",
                "join":   "키 기반 병합 — 공통 컬럼으로 Join",
            }[x],
            key=f"{prefix}_folder_merge_strategy",
        )
        merge_params["strategy"] = strategy

        if strategy == "time":
            merge_params["direction"] = st.radio(
                "매칭 방향", list(_DIRECTION_LABELS.keys()),
                format_func=lambda x: _DIRECTION_LABELS[x],
                key=f"{prefix}_folder_direction",
            )
            merge_params["tolerance_seconds"] = _tolerance_ui(f"{prefix}_folder")

        elif strategy == "join":
            merge_params["key_col"] = st.text_input("Join 기준 컬럼명", key=f"{prefix}_folder_key_col")

    return folder_configs, merge_params


def is_folder_ready(folder_configs: list[dict], merge_params: dict) -> bool:
    if not folder_configs:
        return False
    if merge_params.get("strategy") == "join" and not merge_params.get("key_col", "").strip():
        return False
    return True


def folders_to_temp(folder_configs: list[dict], merge_params: dict) -> str:
    dfs = [
        load_folder(
            cfg["path"],
            date_col=cfg["date_col"],
            time_col=cfg["time_col"],
            datetime_col=cfg.get("datetime_col", ""),
        )
        for cfg in folder_configs
    ]
    for i, df in enumerate(dfs):
        if "__source" in df.columns:
            df.rename(columns={"__source": f"__source_{i + 1}"}, inplace=True)
    strategy = merge_params.get("strategy", "time")

    if len(dfs) == 1:
        df = dfs[0]
    elif strategy == "time":
        for i, d in enumerate(dfs):
            if "__datetime" not in d.columns:
                available = ", ".join(d.columns.tolist()[:10])
                raise ValueError(
                    f"폴더 {i + 1}에서 __datetime 컬럼을 생성하지 못했습니다.\n"
                    f"실제 컬럼 목록 (처음 10개): {available}\n"
                    f"날짜/시간 컬럼명을 확인하거나 '행 결합' 방식으로 변경해보세요."
                )
        df = dfs[0]
        for right in dfs[1:]:
            df = time_join_dataframes(
                df, right,
                left_time_col="__datetime",
                right_time_col="__datetime",
                direction=merge_params.get("direction", "nearest"),
                tolerance_seconds=merge_params.get("tolerance_seconds"),
            )
    elif strategy == "join":
        df = join_dataframes(dfs, merge_params["key_col"].strip())
    else:
        df = concat_dataframes(dfs)

    return _df_to_temp(df)


# ── 공통 헬퍼 ─────────────────────────────────────────────────────────────────

def _tolerance_ui(prefix: str) -> int | None:
    tol_col, unit_col = st.columns([2, 1])
    with tol_col:
        tol_val = st.number_input(
            "허용 시간 차이 (0 = 제한 없음)", min_value=0, value=0, key=f"{prefix}_tol_val"
        )
    with unit_col:
        tol_unit = st.selectbox("단위", list(_TOLERANCE_UNITS.keys()), key=f"{prefix}_tol_unit")
    return int(tol_val * _TOLERANCE_UNITS[tol_unit]) if tol_val > 0 else None


def _df_to_temp(df: pd.DataFrame) -> str:
    fd, tmp_path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    df.to_csv(tmp_path, index=False)
    return tmp_path
