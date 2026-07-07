# 아키텍처 상세 — AI 모델 생성 파이프라인

> 이 문서는 시스템의 **구조와 각 구성 요소의 역할**을 개발자 관점에서 상세히 기술한다.
> 비전문가용 기능 개요는 [`PROJECT_OVERVIEW.md`](../../PROJECT_OVERVIEW.md)를, 시각화는 [`architecture-diagrams.md`](./architecture-diagrams.md)를 참고하라.
> 🆕 표시는 최초 작성 이후 추가된 컴포넌트/규칙을 뜻한다.

---

## 1. 설계 철학

| 원칙 | 적용 방식 |
|------|----------|
| **3-Tier 레이어 분리** | Presentation → Logic → Data 단방향 의존. 상위 레이어는 하위만 호출하고, 레이어를 건너뛰지 않는다 |
| **의존성 주입(DI)** | `main.py`가 모든 구현체를 조립해 `Orchestrator`에 주입한다. 각 에이전트는 `LLMProvider` 인터페이스에만 의존 |
| **인터페이스 추상화** | `LLMProvider`, `SessionStore`는 추상 클래스. 구현체 교체만으로 LLM/저장소 변경 가능 (예: Anthropic → 캐싱 래퍼 → Ollama) |
| **에이전트 단일 책임** | 각 에이전트(Plan/Code/Eval/Chat/Spec)는 한 가지 역할만 수행하고, Orchestrator가 이들을 조율 |
| **방법론 게이트** | 생성된 ML 코드는 검증 게이트(`ml_gates`, `validator`)를 통과해야 실행된다. 성능이 기준에 못 미치면 통합 개선 루프가 재시도한다 🆕 |
| **점진적 확장** | "심플하게 먼저 완성 → 기능을 하나씩 추가"(교수 자문). Mode A/B 중 Mode B로 단일화 후 그 위에 기능을 쌓는 방식으로 진행 중 |

---

## 2. 레이어 구성

### 2.1 Presentation Layer (`app/ui/`, `app/main.py`)

사용자와의 모든 상호작용(입력 수집, 진행 표시, 결과 시각화)을 담당한다. **비즈니스 로직과 데이터 접근을 직접 수행하지 않는다.**

| 파일 | 역할 | 핵심 함수/요소 |
|------|------|---------------|
| `main.py` | 앱 진입점. DI 조립(캐싱 Provider 포함) + 테마 적용 | `_build_orchestrator()`, `main()` |
| `ui/mode_b.py` | **현재 유일하게 활성화된 화면.** 데이터 업로드 → 컬럼 자동 감지 → 명세서 자동 채움 → PII 배지 → 계획 3개 제안 → 선택 실행 | `render(orchestrator)` |
| `ui/mode_a.py` | 자연어 목표 입력 화면. **현재 숨김** — `main.py`가 import는 유지하되 렌더링하지 않음. 코드는 그대로 남아있어 필요시 복원 가능 | `render(orchestrator)` |
| `ui/theme.py` | 다크 모던 SaaS 디자인 — 전역 CSS, Hero/섹션 헤더 | `inject_theme()`, `render_hero()`, `section_header()` |
| `ui/components/data_loader.py` | 파일 업로드(다중 형식) / 폴더 입력 UI + 병합 옵션 수집 | `render_upload_section()`, `upload_to_temp()` (내부에서 `read_uploaded_table` 호출) |
| `ui/components/progress.py` | 실시간 진행 표시 — 파이프라인 칩 + 타임스탬프 로그 (비용·캐시 알림도 이 로그에 표시됨) | `progress_status()` (context manager) |
| `ui/components/result_view.py` | 분석 결과 6탭 시각화 + 비용 카드 | `show_result()`, `_show_cost()` |
| `ui/components/result_chat.py` | 결과 기반 챗봇 UI. 답변마다 비용을 표시 | `show_chat()` |

**핵심 패턴 — `progress_status`**
Presentation이 Logic에 `notify` 콜백을 주입하고, Orchestrator가 단계마다 이를 호출한다. UI는 콜백으로 받은 문자열의 접두 이모지(`📂📋💻🔍🚀🩺💰⚡`)를 보고 파이프라인 단계·비용·캐시 재사용 여부를 함께 추적한다.

### 2.2 Logic Layer (`app/agents/`)

비즈니스 규칙의 핵심. LLM 호출, 코드 검증, 결과 진단 등 "두뇌" 역할.

| 파일 | 역할 | 입력 → 출력 | LLM 호출 |
|------|------|------------|:-------:|
| `agents/orchestrator.py` | 전체 파이프라인 조율자. **통합 개선 루프**(최대 3라운드) + 비용 추적 | Request → `OrchestratorResult` | (간접) |
| `agents/plan_agent.py` | 분석 계획 수립. Mode B는 서로 다른 알고리즘 3개, 시계열 task_type 지원 🆕 | Schema+목표 → `AnalysisPlan` | ✅ |
| `agents/code_agent.py` | 실행 가능한 Python ML 코드 생성. seed 고정·다중공선성 계산 규칙 포함 🆕. 게이트 위반 시 최대 3회 재생성 | Plan+Schema(+개선 피드백) → `GeneratedCode` | ✅ (재시도) |
| `agents/spec_agent.py` 🆕 | 사용자가 올린 명세서 텍스트에서 컬럼 설명·타겟·분석유형을 추출 (수동 입력 대체) | 컬럼목록+명세서텍스트 → 컬럼설명 dict | ✅ |
| `agents/eval_agent.py` | 결과 신뢰성 진단. 룰 기반 체크(다중공선성 포함 🆕) + LLM 해석. **PII 마스킹 후** LLM 호출 🆕 | `AnalysisResult` → 진단 dict | ✅ |
| `agents/chat_agent.py` | 결과 컨텍스트 기반 질의응답. 비용도 함께 반환 | Result+대화이력 → (답변, 비용) | ✅ |
| `agents/validator.py` | import 화이트리스트 검증 (보안). `scipy` 포함 | source_code → `ValidationResult` | ❌ |
| `agents/ml_gates.py` | ML 방법론 무결성 게이트. **AST(추상구문트리) 기반**으로 재작성 🆕, 6개 규칙 | source_code → 위반 목록 | ❌ |

**Orchestrator의 5개 진입점**
- `run_mode_a(request, progress)` — Mode A 전체 파이프라인 (현재 UI에서 호출 안 됨, 코드는 유지)
- `propose_plans(request, progress)` — Mode B 1단계 (계획 3개 제안 후 사용자 선택 대기)
- `execute_selected_plan(session_id, plan_id, progress)` — Mode B 2단계 (통합 개선 루프 실행)
- `parse_spec(column_names, spec_text)` 🆕 — 명세서 텍스트 자동 분석 (PII 마스킹 후 SpecAgent 호출)
- `chat_about_result(result, history)` — 결과 챗봇 위임 (비용 포함 반환)

**통합 개선 루프 — `_run_improvement_loop` 🆕**
기존에는 "코드 생성 → 검증 → 실행 → 진단"을 한 번만 수행했다. 지금은 **최대 3라운드** 반복하며, 매 라운드 끝에 진단 결과(verdict)를 확인한다.
- 진단이 **"신뢰 가능"** 이면 즉시 종료
- 그 외(주의 필요/신뢰 어려움)면 진단 내용(경고 항목, 개선 제안)을 `improvement_feedback`으로 CodeAgent에 넘겨 다음 라운드에서 코드를 다시 생성
- 매 라운드의 성능 점수(분류=F1/정확도, 회귀=R²)를 비교해 **가장 좋았던 결과**를 최종 채택 (라운드가 진행되며 성능이 나빠져도 손해 보지 않음)
- 실행 자체가 오류로 실패하면: 이미 성공한 라운드가 있으면 그걸 채택, 없으면 오류를 피드백 삼아 재시도

**검증 게이트 2계층 (역할 구분)**
- `validator.py` — **보안**. 허용되지 않은 라이브러리 import 차단(`os`, `subprocess` 등). 위반 시 즉시 실패(재시도 없음).
- `ml_gates.py` — **방법론**. AST 기반 6개 규칙:
  1. **데이터 누수** — 테스트 데이터로 fit 금지 (변수를 재할당해도 별칭을 추적해 탐지)
  2. **교차검증 무결성** 🆕 — `RandomizedSearchCV`/`GridSearchCV`가 학습 데이터가 아닌 전체·테스트 데이터로 수행되면 위반
  3. **SMOTE 순서** — `train_test_split` 이전에 SMOTE 적용 금지 (분류만)
  4. **평가 무결성** — 최종 `predict`가 `X_train`으로만 수행되면 위반
  5. **시계열 분할** — 시계열 task는 `shuffle=False` 필수
  6. **재현성** 🆕 — `train_test_split`/`RandomizedSearchCV`/`GridSearchCV`/`SMOTE`에 고정된 `random_state`가 없으면 위반 (단, `random_state`가 아예 없는 추정기까지 강제하면 `TypeError`가 나므로 확실한 대상만 게이트로 강제하고 나머지는 프롬프트로 유도)
  - 위반 시 CodeAgent가 LLM에 피드백을 주고 재생성 (최대 3회)
  - **정규식 → AST 전환 이유**: 정규식은 `X_test`라는 리터럴 문자열만 찾아서 `xt = X_test` 같은 변수 재할당으로 우회 가능했다(교수 자문 2026-06-30). AST는 sklearn의 고정 반환 순서(`train, test, train, test`)로 실제 역할을 판별하고 별칭 체인을 끝까지 추적하므로 이름을 바꿔도 탐지된다.

### 2.3 Data Layer (`app/loaders/`, `app/executor/`, `app/storage/`, `app/providers/`)

외부와의 소통(파일, 코드 실행, LLM API, 저장소). 비즈니스 로직을 포함하지 않는다.

| 파일 | 역할 | 핵심 함수 |
|------|------|----------|
| `loaders/csv_loader.py` | CSV 읽기, 인코딩/헤더 자동 감지, 다중 파일·폴더 병합, datetime 파싱, 스키마 추론. `read_uploaded_table`로 **다중 형식**(csv/tsv/txt/xlsx/xls/xlsm/json) 지원 🆕 | `load_dataframe()`, `read_uploaded_table()`, `infer_schema()`, `schema_to_text()` |
| `loaders/spec_loader.py` 🆕 | 업로드된 명세서 파일(형식 무관)을 평문 텍스트로 추출 | `extract_spec_text(filename, data)` |
| `loaders/anonymizer.py` 🆕 | 개인정보(PII) 탐지·마스킹. 컬럼명 패턴 + 실제 값 샘플(정규식) 둘 다 검사 | `detect_pii_columns()`, `mask_value()`, `mask_text()` |
| `executor/code_executor.py` | 생성된 코드를 `exec()`로 실행하고 `result`/`model`/`feature_importance` 변수 추출 | `run_code(source_code, df)` |
| `storage/session_store.py` | 세션 상태 저장 (인메모리). 추상 클래스로 DB 교체 대비 | `SessionStore` (ABC), `InMemorySessionStore` |
| `providers/base.py` | LLM 공통 인터페이스 (추상). `usage_snapshot()`/`cost_usd()` 기본 구현 포함 🆕 | `LLMProvider.chat()`, `.get_model_name()`, `.usage_snapshot()`, `.cost_usd()` |
| `providers/anthropic_provider.py` | Claude API 연동 구현체. **토큰 사용량 누적 + 모델별 단가표**로 비용 계산 🆕 | `AnthropicProvider.chat()`, `.usage_snapshot()`, `.cost_usd()` |
| `providers/caching_provider.py` 🆕 | `LLMProvider`를 감싸는 캐싱 데코레이터. 동일 요청(모델+temperature+messages 해시)이면 API 재호출 없이 이전 응답 재사용 | `CachingLLMProvider.chat()` |

**PII 탐지 방식 (`anonymizer.py`)** — 컬럼명 우선 매칭(이름/이메일/전화/주민번호/주소/카드 패턴) → 못 잡으면 실제 값 샘플(최대 50개)이 정규식에 50% 이상 맞는지로 판정. 탐지되면 ① UI에 🔒 배지로 표시, ② 명세서 텍스트를 SpecAgent에 넘기기 전, ③ 결과 진단(EvalAgent)에서 타겟 라벨 값을 LLM에 넘기기 전, 각각 `mask_text()`로 마스킹한다.

**비용 추적 방식** — `AnthropicProvider`가 API 응답의 `usage` 필드를 누적하고, 모델별 단가표(예: `claude-sonnet-4-6` = 입력 $3/출력 $15 per 1M 토큰)로 비용을 계산한다. `Orchestrator`는 각 단계 전후로 `usage_snapshot()`을 찍어 델타를 계산해 `notify` 콜백으로 사용자에게 보여준다. 델타가 0이면(=API를 호출했는데 토큰 증가가 없으면) `CachingLLMProvider`의 캐시 히트로 간주해 "⚡ 캐시 재사용" 메시지를 표시한다.

### 2.4 Domain Models (`app/domain/models.py`)

레이어 간 데이터 전달용 DTO/엔티티. dataclass로 정의.

| 모델 | 의미 |
|------|------|
| `SessionMode` / `SessionStatus` | 모드(A/B) / 세션 상태 enum |
| `ColumnSpec` | 컬럼 명세. `pii_kind` 필드 추가 🆕 — 감지된 개인정보 종류(`email`/`phone`/`resident_id`/`address`/`card`/`name`), 없으면 `None` |
| `DataSchema` | 전체 스키마 (`INFERRED` \| `USER_PROVIDED`) |
| `AnalysisPlan` | 분석 계획. `task_type`에 `"timeseries"` 추가 🆕, `time_column` 필드 추가 🆕(시계열의 시간축 컬럼) |
| `GeneratedCode` | 생성된 코드 + 의존성 목록 |
| `AnalysisResult` | 최종 결과 (`metrics`에 `__eval`(진단), `__cost`(비용 dict) 키가 실행 중 추가됨) |
| `AnalysisSession` | 세션 전체 상태 집합체 (스키마·계획·코드·결과) |
| `ModeARequest` | Mode A 입력 요청 DTO |
| `ModeBRequest` | Mode B 입력 요청 DTO. `time_column` 필드 추가 🆕 |
| `OrchestratorResult` | 파이프라인 실행 결과 (status, plans, result, error) |
| `ExecutionResult` | 코드 실행 결과 (success, result, model, stdout/stderr) |

---

## 3. 데이터 흐름 (Mode B 기준 — 현재 유일 활성 경로)

```
[사용자] 데이터 파일 업로드 (CSV/Excel/JSON/TSV 등)
   │
   ▼ Presentation: mode_b.render()
   │   - read_uploaded_table()로 형식 무관하게 읽어 임시 CSV로 저장
   │   - infer_schema()로 컬럼 자동 감지
   │   - detect_pii_columns()로 민감 컬럼 스캔 → 🔒 배지 표시
   │
   ├─(선택) 명세서 파일 첨부 시:
   │   ▼ Logic: orchestrator.parse_spec(column_names, spec_text)
   │       - Data: anonymizer.mask_text(spec_text) — PII 마스킹
   │       - Logic: spec_agent.extract() → chat() → 컬럼설명/타겟/task_type 추출
   │       - 폼에 자동 채움 + 비용 표시
   │
   ▼ [사용자] 타겟 컬럼·분석유형 확정 → [분석 방향 제안받기]
   ▼ Logic: orchestrator.propose_plans(request, notify)
   │   - plan_agent.propose_plans_mode_b() → chat() → 서로 다른 알고리즘 3개
   │   - AWAITING_SELECTION 상태로 세션 저장
   │
   ▼ [사용자] 방향 선택 → [분석 시작]
   ▼ Logic: orchestrator.execute_selected_plan(session_id, plan_id, notify)
   │
   └─▼ Logic: _run_improvement_loop()  (최대 3라운드)
       ├─① code_agent.generate_code(plan, schema, feedback)
       │     → chat() → 코드 → ml_gates.run_all() 6개 게이트 검사
       │     → 위반 시 재생성(최대 3회, 내부 루프)
       ├─② validator.validate_code()  (import 화이트리스트)
       ├─③ code_executor.run_code(code, df)
       │     → exec() → result/model/feature_importance 추출
       ├─④ eval_agent.evaluate(result)
       │     → 룰 체크(다중공선성 포함) + anonymizer.mask_text()로 라벨 마스킹
       │     → chat() 해석 → 진단 dict (verdict/checks/risks/recs)
       ├─⑤ 성능 점수 비교 → best 갱신
       └─⑥ verdict가 '신뢰 가능'이면 종료, 아니면 피드백으로 ①부터 재시도
   │
   ▼ Presentation: result_view.show_result()
       비용 카드 + 6탭 시각화 + result_chat (챗봇, 답변마다 비용 표시)
```

> Mode A(자연어 목표 입력)는 `run_mode_a()`로 코드가 남아있으며, 위 흐름에서 "계획 3개 제안 → 선택" 단계가 없고 대신 목표 텍스트로 단일 계획을 바로 생성한다는 점만 다르다. 현재 UI에서 호출되지 않는다.

---

## 4. 세션 상태 전이

```
PENDING → PLANNING → GENERATING → RUNNING → COMPLETED
                                              └ (실패 시 어느 단계든) → FAILED

Mode B: PENDING → PLANNING → AWAITING_SELECTION → (선택) → GENERATING → RUNNING → COMPLETED
```

`GENERATING ↔ RUNNING` 구간은 통합 개선 루프로 인해 내부적으로 최대 3회 반복되지만, 세션 레벨에서 노출되는 상태 자체는 변하지 않는다(반복은 상태 전이가 아니라 같은 상태 내의 재시도). 상태는 `SessionStore`에 저장된다.

---

## 5. 확장 포인트 (교체/추가 지점)

| 바꾸고 싶은 것 | 손대야 할 곳 | 영향 범위 |
|---------------|-------------|----------|
| **LLM 교체** (Claude → 로컬 모델) | `providers/`에 `LLMProvider` 구현체 추가 + `main.py` 분기 | `CachingLLMProvider`가 감싸는 형태라 어떤 구현체든 캐싱 혜택을 그대로 받음 ([deployment 문서](./deployment-and-local-model.md) 참고) |
| **저장소 교체** (메모리 → DB) | `storage/`에 `SessionStore` 구현체 추가 | Orchestrator 무변경 (아직 미착수 — Docker와 함께 후순위) |
| **새 알고리즘 추가** | `plan_agent.py`의 `_ALGO_*` 상수 | 프롬프트만 수정 |
| **방법론 게이트 추가** | `ml_gates.py`에 `check_*` 함수 추가 후 `run_all()`에 등록 | AST 기반이라 새 검사도 `_find_splits`/`_build_alias_map` 등 기존 헬퍼 재사용 가능 |
| **PII 패턴 추가** | `anonymizer.py`의 `_COLUMN_NAME_PATTERNS`/`_VALUE_PATTERNS` | 컬럼명 패턴은 즉시 반영, 값 패턴은 정규식만 추가하면 됨 |
| **데이터 형식 추가** (Parquet 등) | `csv_loader.py`의 `read_uploaded_table()`에 분기 추가 | 새 라이브러리(`pyarrow` 등) 승인 필요 시 별도 논의 |
| **결과 탭 추가** | `result_view.py`에 탭 + `_show_*()` 추가 | 다른 레이어 무변경 |
| **UI 디자인 변경** | `theme.py`의 CSS 토큰/헬퍼 | 컴포넌트 로직 무변경 |
| **Mode A 복원** | `main.py`에서 탭 라우팅을 되살리기만 하면 됨 | 코드가 그대로 보존돼 있어 삭제된 것 없음 |

---

## 6. 보안 및 한계

**보안 설계**
- API 키는 `.env`(환경변수)로만 주입, 코드에 하드코딩 금지
- 생성 코드는 `validator`(import 화이트리스트) + `ml_gates`(AST 기반 6개 방법론 게이트)를 모두 통과해야 실행
- 실행 코드는 파일 직접 접근 금지 — 데이터는 `df`로 메모리 전달
- **개인정보(PII) 마스킹** 🆕 — 컬럼명·값 패턴으로 민감정보를 탐지해 LLM 호출 2곳(명세서 분석, 결과 진단)에서 실제 값을 마스킹 후 전송. 코드 실행(`exec()`) 자체는 로컬이라 원본 데이터가 외부로 나가지 않음

**재현성 대응** 🆕
- **ML 코드 레벨**: `ml_gates`의 재현성 게이트가 `random_state` 고정을 강제 (완전 통제 가능한 영역)
- **LLM 응답 레벨**: Claude API는 완전한 결정성 보장(OpenAI의 seed 파라미터 같은 것)이 없음. `CachingLLMProvider`로 "동일 입력 → 동일 출력"을 실용적으로 달성 (앱 프로세스 생명주기 동안 유지, 재시작 시 초기화)

**현재 한계 (PoC)**
- `code_executor`는 `exec()` 기반으로 **OS 수준 격리가 없다** → 신뢰 환경에서만 사용. 상용화 시 컨테이너/서브프로세스 샌드박싱 필요 (교수 자문: Docker/RestrictedPython/nsjail 검토, 의도적으로 최후순위로 미룸)
- 세션이 인메모리 → 앱 재시작 시 소실 (Redis/PostgreSQL 영속화는 후순위)
- 단일 프로세스 동기 실행 → 동시 사용자 다수 시 성능 미검증 (Celery+Worker Pool 등은 후순위)
- 캐싱은 프로세스 생명주기 동안만 유지되는 인메모리 캐시 — 완전 영속화는 세션 저장소 영속화와 함께 다룰 예정
