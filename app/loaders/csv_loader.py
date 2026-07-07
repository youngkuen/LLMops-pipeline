"""CSV 파싱 + DataSchema 자동 추론 — Data Layer"""
from __future__ import annotations
import glob
import os
import pandas as pd
from app.domain.models import ColumnSpec, DataSchema


def concat_dataframes(dfs: list[pd.DataFrame]) -> pd.DataFrame:
    return pd.concat(dfs, ignore_index=True)


def join_dataframes(dfs: list[pd.DataFrame], key_col: str) -> pd.DataFrame:
    result = dfs[0]
    for df in dfs[1:]:
        result = result.merge(df, on=key_col, how="outer")
    return result


def time_join_dataframes(
    left: pd.DataFrame,
    right: pd.DataFrame,
    left_time_col: str,
    right_time_col: str,
    direction: str = "nearest",
    tolerance_seconds: int | None = None,
) -> pd.DataFrame:
    """merge_asof — 정확히 일치하지 않아도 가장 가까운 시점으로 병합."""
    left = left.copy()
    right = right.copy()
    left[left_time_col] = pd.to_datetime(left[left_time_col], errors="coerce")
    right[right_time_col] = pd.to_datetime(right[right_time_col], errors="coerce")
    left = left.dropna(subset=[left_time_col]).sort_values(left_time_col).reset_index(drop=True)
    right = right.dropna(subset=[right_time_col]).sort_values(right_time_col).reset_index(drop=True)
    if left.empty or right.empty:
        raise ValueError(
            f"시간 기반 병합 실패: datetime 파싱 후 유효한 행이 없습니다. "
            f"(left={len(left)}행, right={len(right)}행) "
            f"컬럼명과 datetime 포맷을 확인하세요."
        )
    tolerance = pd.Timedelta(seconds=tolerance_seconds) if tolerance_seconds else None
    return pd.merge_asof(
        left, right,
        left_on=left_time_col,
        right_on=right_time_col,
        direction=direction,
        tolerance=tolerance,
    )


def load_folder(
    folder_path: str,
    date_col: str = "DATE",
    time_col: str = "TIME",
    date_format: str = "%m.%d.%Y %H:%M:%S",
    datetime_col: str = "",
) -> pd.DataFrame:
    """폴더 내 모든 CSV를 읽어 연결하고 __datetime 컬럼을 파싱한다.

    datetime_col이 지정되면 그 컬럼 하나를 datetime으로 파싱한다.
    지정되지 않으면 date_col + time_col을 합쳐 파싱한다.
    """
    csv_files = sorted(glob.glob(os.path.join(folder_path.strip(), "*.csv")))
    if not csv_files:
        raise ValueError(f"CSV 파일을 찾을 수 없습니다: {folder_path}")

    dfs = []
    for path in csv_files:
        df = _read_csv_safe(path)
        df["__source"] = os.path.basename(path)
        dfs.append(df)

    merged = pd.concat(dfs, ignore_index=True)

    if datetime_col and datetime_col in merged.columns:
        merged["__datetime"] = pd.to_datetime(merged[datetime_col], errors="coerce")
    elif date_col in merged.columns and time_col in merged.columns:
        dt_str = (
            merged[date_col].astype(str).str.strip('"').str.strip()
            + " "
            + merged[time_col].astype(str).str.strip('"').str.strip()
        )
        merged["__datetime"] = pd.to_datetime(dt_str, format=date_format, errors="coerce")

    return merged


def _read_csv_safe(path: str) -> pd.DataFrame:
    """인코딩·상단 메타데이터를 자동 감지하여 CSV를 읽는다."""
    for enc in ("utf-8-sig", "cp949", "utf-8"):
        try:
            skiprows = _find_header_row(path, enc)
            df = pd.read_csv(path, encoding=enc, skiprows=skiprows, on_bad_lines="skip")
            df.columns = df.columns.str.strip()
            return df
        except UnicodeDecodeError:
            continue
    raise ValueError(f"파일 인코딩을 인식할 수 없습니다: {path}")


def _find_header_row(path: str, encoding: str) -> int:
    """쉼표가 없는 상단 메타데이터 행을 건너뛰고 첫 번째 CSV 헤더 행 번호를 반환한다."""
    try:
        with open(path, encoding=encoding, errors="replace") as f:
            lines = [f.readline() for _ in range(30)]
    except OSError:
        return 0
    for i, line in enumerate(lines):
        if line.strip() and "," in line:
            return i
    return 0


def read_uploaded_table(file) -> pd.DataFrame:
    """업로드된 파일 객체(name 속성 보유)를 형식에 맞게 DataFrame으로 읽는다.
    지원: csv, txt, tsv, xlsx, xls, xlsm, json. 그 외 확장자는 CSV로 시도한다.
    """
    name = getattr(file, "name", "").lower()
    if name.endswith((".xlsx", ".xls", ".xlsm")):
        return pd.read_excel(file)
    if name.endswith(".json"):
        return pd.read_json(file)
    if name.endswith(".tsv"):
        return pd.read_csv(file, sep="\t")
    return pd.read_csv(file)  # .csv, .txt, 기타


def load_dataframe(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    if df.empty:
        raise ValueError(f"CSV 파일이 비어 있습니다: {csv_path}")
    return df


def infer_schema(df: pd.DataFrame) -> DataSchema:
    columns = []
    for col in df.columns:
        dtype = df[col].dtype
        if pd.api.types.is_numeric_dtype(dtype):
            data_type = "NUMERIC"
        elif pd.api.types.is_bool_dtype(dtype):
            data_type = "BOOLEAN"
        elif pd.api.types.is_datetime64_any_dtype(dtype):
            data_type = "DATETIME"
        else:
            n_unique = df[col].nunique()
            data_type = "CATEGORICAL" if n_unique < 20 else "TEXT"

        columns.append(ColumnSpec(name=col, data_type=data_type))

    return DataSchema(columns=columns, origin="INFERRED")


def schema_to_text(schema: DataSchema, df: pd.DataFrame | None = None) -> str:
    lines = []
    for col in schema.columns:
        desc = col.description or ""
        dtype = col.data_type or "unknown"
        target_mark = " [예측 타겟]" if col.is_target else ""
        sample = ""
        if df is not None and col.name in df.columns:
            samples = df[col.name].dropna().head(3).tolist()
            sample = f" | 샘플: {samples}"
        lines.append(f"- {col.name} ({dtype}){target_mark}{': ' + desc if desc else ''}{sample}")
    return "\n".join(lines)
