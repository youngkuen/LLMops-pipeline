# Technical Requirements Document
# AI 모델 생성 파이프라인 자동 구성 — POC

**작성일**: 2026-06-24
**Seed Ref**: seed-v1.yaml
**아키텍처 패턴**: 3-tier Layered (Presentation / Logic / Data)

---

## 1. Overview

비기술자 비즈니스 담당자가 CSV 파일과 자연어(Mode A) 또는 데이터 명세서(Mode B)를 입력하면,
LLM 멀티에이전트가 분석 계획을 수립하고 Python ML 코드를 생성·실행하여 결과를 화면에 출력하는 POC.

**핵심 목표**: 기술 실현 가능성 시연. 정확도·보안·대용량은 이 단계에서 제외.

---

## 2. Layer Design

### 2.1 Presentation Layer

**역할**: 사용자 입력 수집, 진행 상태 표시, 결과 시각화. 비즈니스 로직 없음.

**기술**: Streamlit

| 파일 | 역할 |
|------|------|
| `app/main.py` | Streamlit 앱 진입점, Mode A/B 탭 분기 |
| `app/ui/mode_a.py` | CSV 업로드 + 자연어 입력 + 결과 출력 페이지 |
| `app/ui/mode_b.py` | DataSchema 입력 + 3가지 제안 선택 + 결과 출력 페이지 |
| `app/ui/components/progress.py` | 에이전트 단계별 진행 표시 컴포넌트 (threading 기반) |
| `app/ui/components/result_view.py` | 지표·feature importance 시각화 컴포넌트 |

**입력 DTO** (Presentation → Logic):
```python
# Mode A
@dataclass
class ModeARequest:
    csv_path: str          # 업로드된 CSV 임시 파일 경로
    objective_text: str    # 사용자 자연어 입력

# Mode B
@dataclass
class ModeBRequest:
    schema_columns: list[ColumnSpec]  # 컬럼 이름 + 설명 목록

@dataclass
class ColumnSpec:
    name: str
    description: str
```

**규칙**:
- `st.session_state`에 세션 데이터 저장 (POC용 인메모리)
- LLM 호출·코드 실행은 threading으로 비동기 실행, `st.empty()`로 단계 진행 표시
- Logic 레이어 함수만 호출, Data 레이어 직접 접근 금지

---

### 2.2 Logic Layer

**역할**: 에이전트 오케스트레이션, 비즈니스 규칙. UI 코드 없음, LLM SDK 직접 의존 없음.

| 파일 | 역할 |
|------|------|
| `app/agents/orchestrator.py` | Mode 판단 → 에이전트 실행 순서 제어 |
| `app/agents/plan_agent.py` | LLMProvider 호출 → AnalysisPlan 생성 |
| `app/agents/code_agent.py` | LLMProvider 호출 → Python 코드 생성 |
| `app/agents/validator.py` | 생성된 코드의 import 화이트리스트 검증 |
| `app/services/session_service.py` | AnalysisSession 상태 전이 관리 |
| `app/domain/models.py` | 도메인 dataclass (AnalysisSession, AnalysisPlan, GeneratedCode, AnalysisResult) |

**비즈니스 규칙**:

1. **Plan Agent 규칙**
   - Mode A: `objective_text` + DataSchema(자동 추론) → AnalysisPlan 1개 생성
   - Mode B: DataSchema → AnalysisPlan **정확히 3개** 생성 (3개 미만이면 재시도)
   - 각 Plan은 서로 다른 `algorithm_family`를 가져야 함

2. **Code Agent 규칙**
   - 선택된 AnalysisPlan을 기반으로 Python 코드 생성
   - 코드는 반드시 `result` 변수와 `model` 변수를 정의해야 함 (Executor 추출 규칙)
   - `result`: dict 형태의 평가 지표 (`{'accuracy': 0.91, 'f1': 0.88, ...}`)
   - `model`: 학습된 scikit-learn 호환 모델 객체

3. **Validator 규칙**
   - 허용 라이브러리: `pandas`, `numpy`, `scikit-learn` (sklearn), `xgboost`, `lightgbm`, `matplotlib`
   - 허용 목록 외 import 발견 시 실행 거부, 에러 반환

4. **Session 상태 전이**
   ```
   PENDING → PLANNING → AWAITING_SELECTION (Mode B만) → GENERATING → RUNNING → COMPLETED
                                                                              → FAILED
   ```

**출력 DTO** (Logic → Presentation):
```python
@dataclass
class OrchestratorResult:
    status: str                        # 'completed' | 'failed'
    plans: list[AnalysisPlan]          # Mode B: 3개, Mode A: 1개
    result: AnalysisResult | None
    error_message: str | None

@dataclass
class AnalysisResult:
    metrics: dict                      # {'accuracy': 0.91, ...}
    feature_importance: dict | None    # {'col_name': 0.32, ...}
    generated_code: str                # 투명성을 위해 UI에 표시 가능
```

---

### 2.3 Data Layer

**역할**: 외부 시스템(LLM, 파일시스템, 실행 환경) 접근. 비즈니스 로직 없음.

| 파일 | 역할 |
|------|------|
| `app/providers/base.py` | `LLMProvider` 추상 기반 클래스 |
| `app/providers/openai_provider.py` | OpenAI API 구현체 |
| `app/providers/anthropic_provider.py` | Anthropic API 구현체 (추후 교체용) |
| `app/executor/code_executor.py` | Python 코드 실행 (`exec()` + 공유 딕셔너리) |
| `app/loaders/csv_loader.py` | CSV 파싱, DataSchema 자동 추론 |
| `app/storage/session_store.py` | `SessionStore` 추상 클래스 + `InMemorySessionStore` 구현 |

**LLMProvider 인터페이스**:
```python
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: list[dict], temperature: float = 0.2) -> str:
        """messages: [{'role': 'user'|'assistant'|'system', 'content': str}]"""
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        ...
```

**CodeExecutor 동작**:
```python
# 실행 규칙
# 1. Validator가 import 검증 통과 후 호출됨
# 2. exec(code, global_namespace)로 실행
# 3. global_namespace['result'] → 평가 지표 추출
# 4. global_namespace['model']  → 모델 객체 추출
# 5. stdout/stderr 캡처 (io.StringIO redirect)

@dataclass
class ExecutionResult:
    success: bool
    result: dict | None       # 평가 지표
    model: object | None      # 학습된 모델
    stdout: str
    stderr: str
    error_message: str | None
```

**SessionStore 인터페이스** (나중에 DB로 교체 가능하게):
```python
class SessionStore(ABC):
    @abstractmethod
    def save(self, session: AnalysisSession) -> None: ...

    @abstractmethod
    def get(self, session_id: str) -> AnalysisSession | None: ...

    @abstractmethod
    def update_status(self, session_id: str, status: str) -> None: ...

class InMemorySessionStore(SessionStore):
    # st.session_state를 백엔드로 사용 (POC)
    ...
```

---

## 3. Layer Communication

| 방향 | 방식 | 데이터 형식 |
|------|------|------------|
| Presentation → Logic | 서비스 함수 직접 호출 (threading으로 비동기 래핑) | `ModeARequest` / `ModeBRequest` dataclass |
| Logic → Data | 생성자 주입 (LLMProvider, CodeExecutor, SessionStore) | 추상 클래스 인터페이스 |
| Logic → Presentation 반환 | `OrchestratorResult` dataclass 반환 | dataclass |

**의존성 주입 패턴**:
```python
# main.py에서 조립
provider = OpenAIProvider(api_key=os.environ['OPENAI_API_KEY'])
executor = CodeExecutor()
store = InMemorySessionStore()

orchestrator = Orchestrator(
    llm_provider=provider,
    executor=executor,
    session_store=store,
)
```

---

## 4. Directory Structure

```
이사님모델/
├── app/
│   ├── main.py                          # Streamlit 진입점
│   ├── ui/                              # [Presentation] Streamlit UI
│   │   ├── mode_a.py
│   │   ├── mode_b.py
│   │   └── components/
│   │       ├── progress.py              # 단계 진행 표시
│   │       └── result_view.py           # 결과 시각화
│   ├── agents/                          # [Logic] LLM 에이전트
│   │   ├── orchestrator.py
│   │   ├── plan_agent.py
│   │   ├── code_agent.py
│   │   └── validator.py
│   ├── services/                        # [Logic] 비즈니스 규칙
│   │   └── session_service.py
│   ├── domain/                          # [Logic] 도메인 모델
│   │   └── models.py
│   ├── providers/                       # [Data] LLM 클라이언트
│   │   ├── base.py
│   │   ├── openai_provider.py
│   │   └── anthropic_provider.py
│   ├── executor/                        # [Data] 코드 실행기
│   │   └── code_executor.py
│   ├── loaders/                         # [Data] 데이터 로더
│   │   └── csv_loader.py
│   └── storage/                         # [Data] 세션 저장소
│       └── session_store.py
├── tests/
│   ├── logic/
│   │   ├── test_plan_agent.py
│   │   ├── test_code_agent.py
│   │   ├── test_validator.py
│   │   └── test_orchestrator.py
│   └── data/
│       ├── test_code_executor.py
│       └── test_csv_loader.py
├── requirements.txt
└── .env.example
```

---

## 5. Test Strategy

### Logic Layer 테스트 (단위 테스트, 우선순위 최고)

LLMProvider와 Executor를 mock으로 교체하여 순수 비즈니스 로직만 검증.

```python
# tests/logic/test_plan_agent.py 예시
def test_mode_b_produces_exactly_3_plans():
    mock_provider = MockLLMProvider(response=SAMPLE_3_PLAN_RESPONSE)
    agent = PlanAgent(llm_provider=mock_provider)
    plans = agent.propose(schema=SAMPLE_SCHEMA)
    assert len(plans) == 3
    assert len({p.algorithm_family for p in plans}) == 3  # 서로 다른 알고리즘

def test_mode_b_retries_if_fewer_than_3_plans():
    mock_provider = MockLLMProvider(responses=[
        SAMPLE_2_PLAN_RESPONSE,   # 첫 시도: 2개 (재시도)
        SAMPLE_3_PLAN_RESPONSE,   # 두 번째: 3개 (성공)
    ])
    agent = PlanAgent(llm_provider=mock_provider)
    plans = agent.propose(schema=SAMPLE_SCHEMA)
    assert len(plans) == 3
    assert mock_provider.call_count == 2
```

| 테스트 파일 | 검증 대상 |
|------------|---------|
| `test_plan_agent.py` | Plan 개수 3개 보장, 알고리즘 다양성, 재시도 로직 |
| `test_code_agent.py` | 생성 코드에 `result`·`model` 변수 포함 여부 |
| `test_validator.py` | 화이트리스트 통과/거부 케이스 |
| `test_orchestrator.py` | Mode A/B 흐름 전체, 상태 전이 순서 |

### Data Layer 테스트 (통합 테스트)

실제 실행 환경 연동 검증. LLM 호출은 제외 (비용), Executor는 실제 exec 실행.

```python
# tests/data/test_code_executor.py 예시
def test_executor_extracts_result_and_model():
    code = """
import pandas as pd
from sklearn.linear_model import LogisticRegression
# ... 간단한 학습 코드 ...
result = {'accuracy': 0.9}
model = LogisticRegression()
"""
    executor = CodeExecutor()
    output = executor.run(code, dataset_path=SAMPLE_CSV)
    assert output.success is True
    assert 'accuracy' in output.result
    assert output.model is not None

def test_executor_rejects_disallowed_import():
    code = "import requests\nresult = {}"
    executor = CodeExecutor()
    output = executor.run(code, dataset_path=SAMPLE_CSV)
    assert output.success is False
    assert 'requests' in output.error_message
```

### Presentation Layer 테스트

POC에서는 수동 테스트(Manual). AC-001, AC-002 시나리오를 직접 시연으로 검증.

---

## 6. Decisions & Trade-offs

| 결정 | 근거 | 트레이드오프 |
|------|------|------------|
| Streamlit + threading | 1인 개발, 빠른 프로토타이핑. threading으로 단계 진행 표시 | Streamlit의 threading 지원이 제한적, 복잡한 상태 동기화 주의 |
| `exec()` + 공유 딕셔너리 | POC에서 가장 단순한 코드 실행 방법. 결과 추출 규칙(`result`, `model` 변수명)이 명확 | 보안 격리 없음 — 프로덕션 전환 시 반드시 Docker sandbox로 교체 |
| SessionStore 추상화 | POC는 InMemory지만 DB 전환 시 구현체만 교체 | 인터페이스 설계 비용 소량 발생 |
| LLMProvider 추상화 | 공급자 미결정. OpenAI → Anthropic → Local 전환 가능 | 추상 클래스 작성 비용 소량 발생 |
| 인메모리 세션 (POC) | DB 없이 `st.session_state` 활용. 새로고침 시 초기화 | 이력 보존 불가 — 프로덕션 전환 시 SessionStore 구현체 교체로 해결 |

---

## 7. Implementation Order

Data → Logic → Presentation 순서. 각 단계마다 테스트 먼저 또는 동시 작성.

```
Step 1. [Data] domain/models.py          — 도메인 dataclass 정의 (테스트 없음, 단순 구조)
Step 2. [Data] providers/base.py         — LLMProvider 추상 클래스
Step 3. [Data] providers/openai_provider — OpenAI 구현체
Step 4. [Data] loaders/csv_loader.py     — CSV 파싱, DataSchema 추론 + 테스트
Step 5. [Data] executor/code_executor.py — exec 실행기 + 테스트 (AC-006 포함)
Step 6. [Data] storage/session_store.py  — 추상 클래스 + InMemory 구현
Step 7. [Logic] agents/validator.py      — 화이트리스트 검증 + 테스트 (AC-006)
Step 8. [Logic] agents/plan_agent.py     — Plan Agent + 테스트 (AC-004)
Step 9. [Logic] agents/code_agent.py     — Code Agent + 테스트 (AC-004)
Step 10. [Logic] agents/orchestrator.py  — 전체 흐름 오케스트레이션 + 테스트
Step 11. [Presentation] ui/mode_a.py     — Mode A UI (수동 테스트)
Step 12. [Presentation] ui/mode_b.py     — Mode B UI (수동 테스트)
Step 13. [Presentation] ui/components/   — 진행 표시, 결과 시각화
Step 14. [전체] main.py                  — 조립 + 의존성 주입 + AC-001/002 시연 검증
```

---

## 8. 프로덕션 전환 시 필수 과제 (현재 제외)

| 항목 | 현재 | 프로덕션 |
|------|------|---------|
| 코드 실행 격리 | `exec()` 직접 | Docker sandbox |
| 세션 저장소 | InMemorySessionStore | PostgreSQL + SessionStore 구현체 교체 |
| 인증 | 없음 | OAuth2 / SSO |
| 데이터 입력 | CSV 파일만 | DB 연결, S3, 외부 API |
| LLM 공급자 | OpenAI | 공급자 교체 또는 로컬 LLM (구현체만 교체) |
