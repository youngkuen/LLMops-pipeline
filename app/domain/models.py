from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SessionMode(str, Enum):
    A = "A"
    B = "B"


class SessionStatus(str, Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    AWAITING_SELECTION = "AWAITING_SELECTION"
    GENERATING = "GENERATING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class ColumnSpec:
    name: str
    description: str = ""
    data_type: Optional[str] = None
    is_target: bool = False
    pii_kind: Optional[str] = None  # 감지된 개인정보 종류 (예: "email", "phone"), 없으면 None


@dataclass
class DataSchema:
    columns: list[ColumnSpec]
    origin: str = "INFERRED"  # "INFERRED" | "USER_PROVIDED"


@dataclass
class AnalysisPlan:
    id: str
    session_id: str
    index: int
    title: str
    description: str
    algorithm_family: str
    feature_strategy: str
    target_column: Optional[str] = None
    is_selected: bool = False
    task_type: str = "classification"  # "classification" | "regression" | "timeseries"
    time_column: Optional[str] = None  # timeseries일 때 시간 축 컬럼


@dataclass
class GeneratedCode:
    id: str
    plan_id: str
    source_code: str
    dependencies: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    id: str
    session_id: str
    metrics: dict
    feature_importance: Optional[dict] = None
    generated_code: str = ""


@dataclass
class AnalysisSession:
    id: str
    mode: SessionMode
    status: SessionStatus
    natural_language_input: Optional[str] = None
    csv_path: Optional[str] = None
    schema: Optional[DataSchema] = None
    plans: list[AnalysisPlan] = field(default_factory=list)
    selected_plan: Optional[AnalysisPlan] = None
    generated_code: Optional[GeneratedCode] = None
    result: Optional[AnalysisResult] = None
    error_message: Optional[str] = None


@dataclass
class ModeARequest:
    csv_path: str
    objective_text: str
    task_type: str = "classification"  # "classification" | "regression"


@dataclass
class ModeBRequest:
    csv_path: str
    schema_columns: list[ColumnSpec]
    task_type: str = "classification"  # "classification" | "regression" | "timeseries"
    time_column: Optional[str] = None  # timeseries일 때 시간 축 컬럼


@dataclass
class OrchestratorResult:
    status: str  # 'completed' | 'failed' | 'awaiting_selection'
    session_id: str
    plans: list[AnalysisPlan] = field(default_factory=list)
    result: Optional[AnalysisResult] = None
    error_message: Optional[str] = None


@dataclass
class ExecutionResult:
    success: bool
    result: Optional[dict] = None
    model: object = None
    stdout: str = ""
    stderr: str = ""
    error_message: Optional[str] = None
