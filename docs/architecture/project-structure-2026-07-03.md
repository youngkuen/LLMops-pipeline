# 2026-07-03 — 이사님모델 프로젝트 구조 정리

> 개발자 관점에서 전체 폴더/파일의 역할을 정리한 문서.
> 다이어그램 상세는 [`architecture-diagrams.md`](./architecture-diagrams.md) 참고.

**한 줄 요약**: Streamlit UI에서 데이터를 업로드하면 Claude(Anthropic)가 분석 계획을 세우고, ML 코드를 생성·검증·실행·진단하는 3-tier 아키텍처의 AI 모델 자동 생성 파이프라인.

---

## 1. 실제 동작하는 애플리케이션 — `app/` (3-tier)

```
app/
├── main.py                     # 진입점, DI 조립 (64줄)
├── domain/
│   └── models.py                # DTO/엔티티 (AnalysisSession, Plan, Result 등) — 레이어 간 공용 계약
├── ui/                          # 🖥️ Presentation Layer
├── agents/                      # 🧠 Logic Layer
└── loaders/ executor/ storage/ providers/   # 🗄️ Data Layer
```

### 🖥️ Presentation — `app/ui/`

| 파일 | 역할 |
|---|---|
| `mode_b.py` (259줄) | **현재 유일하게 활성화된 화면**. 데이터 업로드 → 컬럼 확인 → 3개 분석안 제안 → 선택 실행까지의 전체 흐름 |
| `mode_a.py` (83줄) | 자연어 목표 입력 방식(구버전). 코드는 남아있지만 UI에서 숨김 처리됨 |
| `theme.py` (230줄) | 다크 모던 테마 CSS |
| `components/data_loader.py` (266줄) | 다중 형식(CSV/Excel/JSON/TSV) 업로드 + PII 배지 표시 |
| `components/progress.py` (131줄) | 라운드별 진행 상황 표시 |
| `components/result_view.py` (258줄) | 결과 6탭(성능·피처중요도·비용카드 등) |
| `components/result_chat.py` (38줄) | 결과에 대해 후속 질문하는 챗봇 UI |

### 🧠 Logic — `app/agents/`

| 파일 | 역할 |
|---|---|
| `orchestrator.py` (430줄) | **핵심 지휘자**. 세션 상태 관리 + "통합 개선 루프"(최대 3라운드: 코드생성 → 검증 → 실행 → 진단 → 재시도) |
| `plan_agent.py` (187줄) | LLM에게 서로 다른 알고리즘 3개의 분석 계획을 요청 (시계열 지원 포함) |
| `code_agent.py` (223줄) | 분석 계획 → 학습 코드 생성 (seed 고정, 다중공선성 규칙 반영) |
| `ml_gates.py` 🆕 (341줄) | **AST 기반** ML 방법론 검증 6종 (데이터 누수, CV 무결성, SMOTE 순서, 평가셋 분리, 시계열 shuffle 금지, 재현성) — 정규식 우회 문제를 AST 변수 추적으로 해결 |
| `eval_agent.py` (198줄) | 실행 결과 룰체크(샘플수/성능/불균형/다중공선성) + LLM 해석(PII 마스킹 후) |
| `spec_agent.py` 🆕 (65줄) | 사용자가 첨부한 명세서 텍스트에서 컬럼 설명·타겟·task_type 자동 추출 |
| `chat_agent.py` (72줄) | 결과 화면의 후속 질의응답 처리 |
| `validator.py` (46줄) | 생성된 코드의 보안 화이트리스트 검사 (import/exec 제한) |

### 🗄️ Data — `loaders/`, `executor/`, `storage/`, `providers/`

| 파일 | 역할 |
|---|---|
| `loaders/csv_loader.py` (165줄) | 다중 포맷 파일 읽기 + 컬럼 스키마 추론 |
| `loaders/spec_loader.py` 🆕 (56줄) | 명세서 파일(txt) 로딩 |
| `loaders/anonymizer.py` 🆕 (97줄) | PII 탐지(이름패턴+값샘플 정규식)·마스킹 |
| `executor/code_executor.py` (69줄) | 생성된 코드를 격리 실행하고 결과 수집 |
| `storage/session_store.py` (34줄) | 세션 상태 저장(인메모리) |
| `providers/base.py` (25줄) | `LLMProvider` 추상 인터페이스 (`chat()`, `cost_usd()` 등) |
| `providers/anthropic_provider.py` (70줄) | Claude API 연동 + 토큰/비용 추적 |
| `providers/caching_provider.py` 🆕 (49줄) | 동일 요청 캐시 재사용 데코레이터 (base를 감싸는 구조라 다른 provider에도 적용 가능) |
| `providers/openai_provider.py` (25줄) | OpenAI 연동 (보조/대안 provider) |

> 데이터는 로컬 `exec()`로만 처리되어 외부로 나가지 않으며, LLM에 텍스트가 실리는 두 지점(명세서 분석, 결과 진단)에서만 PII 마스킹이 적용된다.

---

## 2. 테스트 — `tests/` (레이어별 분리)

```
tests/
├── data/    test_anonymizer.py, test_caching_provider.py, test_code_executor.py,
│            test_csv_loader.py, test_provider_cost.py, test_read_formats.py
└── logic/   test_code_agent.py, test_eval_agent.py, test_ml_gates.py,
             test_orchestrator.py, test_plan_agent.py, test_validator.py
```

Presentation 레이어 테스트는 아직 없음 (E2E/스냅샷 규칙상 갭).

---

## 3. 프로젝트 거버넌스 문서 — `docs/`, 루트

| 파일 | 역할 |
|---|---|
| `ARCHITECTURE_INVARIANTS.md` | **최상위 규칙** — 레이어 분리 등 절대 불변 사항 (일부 TODO 미채움) |
| `docs/architecture/architecture-diagrams.md` | Mermaid로 그린 전체 구조/시퀀스/상태머신/게이트 로직 다이어그램 (가장 상세) |
| `docs/architecture/ARCHITECTURE.md`, `diagrams-explained.md`, `deployment-and-local-model.md` | 텍스트 설명 + 배포/로컬모델(Ollama 전환 계획) 문서 |
| `docs/adr.yaml` | 아키텍처 결정 기록 |
| `docs/code-convention.yaml` | 코딩 컨벤션 |
| `docs/TRD.md` | 기술 설계 문서 |
| `requirements.txt` | streamlit, anthropic, pandas/numpy/scipy, scikit-learn, xgboost, lightgbm, imbalanced-learn, matplotlib, python-dotenv |
| `run.bat` | 로컬 실행 스크립트 |
| `.streamlit/config.toml` | Streamlit 서버/테마 설정 |
| `test_data/` | 샘플 데이터셋 + 명세서 예시(캘리포니아 주택, 시계열) |

---

## 4. AI 개발 하네스 (Ouroboros 워크플로우) — `.claude/`, `.harness/`

런타임 앱 코드가 아니라, Claude Code로 이 프로젝트를 개발할 때 쓰는 스펙 주도 워크플로우 시스템.

- `.claude/commands/`, `.claude/agents/` — `/interview`, `/seed`, `/trd`, `/decompose`, `/run`, `/evaluate`, `/evolve` 등 슬래시 커맨드와 9개 에이전트 페르소나 정의
- `.harness/gates/` — 커밋 전 자동 검사(레이어 위반, 시크릿 유출, 구조 규칙 등)
- `.harness/methodologies/` — BDD, TDD, DDD, Shape Up 등 선택적으로 켤 수 있는 개발 방법론 플러그인 모음 (미사용 다수)
- `.harness/ouroboros/` — 실제 이 프로젝트에서 진행한 인터뷰(`seed-v1.yaml` 등) 산출물
- `ai-harness-template/` — 위 하네스 시스템 자체의 **템플릿 원본 저장소**(다른 프로젝트에 설치용). 이사님모델 앱과는 무관, 통째로 벤더링된 것

---

## 5. 개발자 관점 핵심 포인트

1. 실질적으로 손댈 코드는 `app/` 하나뿐이며, 나머지(`.claude`, `.harness`, `ai-harness-template`)는 개발 프로세스 도구다.
2. `orchestrator.py`가 사실상 시스템의 심장이고, `ml_gates.py`(AST 검증)와 `anonymizer.py`(PII)가 최근 추가된 핵심 안전장치다.
3. `providers/base.py` 인터페이스 덕분에 Anthropic → Ollama(온프레미스) 전환이 데코레이터 교체만으로 가능하도록 설계돼 있다.

> 교수 피드백(도커 격리, Mode B 단일화, Redis/Celery 등)은 아직 코드에 반영 전이며, 위 구조가 그 확장의 출발점이다.
