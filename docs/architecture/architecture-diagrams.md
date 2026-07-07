# 아키텍처 다이어그램 (Mermaid)

> 시스템 구조를 Mermaid로 시각화한 문서. GitHub·VS Code(Mermaid 확장)·Obsidian 등에서 렌더링된다.
> 텍스트 상세는 [`ARCHITECTURE.md`](./ARCHITECTURE.md)를 참고하라.
> 🆕 표시는 최초 작성 이후 추가된 컴포넌트/체크를 뜻한다.

---

## 1. 시스템 컨텍스트 (전체 조감)

```mermaid
flowchart TB
    user(["👤 사용자<br/>(브라우저)"])

    subgraph APP["AI 모델 생성 파이프라인"]
        direction TB
        P["🖥️ Presentation Layer<br/>Streamlit UI"]
        L["🧠 Logic Layer<br/>에이전트 + 오케스트레이터"]
        D["🗄️ Data Layer<br/>로더 · 실행기 · 저장소 · LLM 연동"]
        P --> L --> D
    end

    llm(["☁️ Anthropic Claude API<br/>(캐싱 경유)"])
    fs(["📁 데이터 파일<br/>CSV·Excel·JSON·TSV / 폴더"])

    user -->|업로드 · 목표 입력| P
    P -->|결과 · 진행 · 비용 표시| user
    D <-->|chat 요청/응답 — PII 마스킹 후| llm
    D <-->|읽기| fs

    classDef pres fill:#1e293b,stroke:#6366f1,color:#e2e8f0
    classDef logic fill:#312e81,stroke:#818cf8,color:#e2e8f0
    classDef data fill:#164e63,stroke:#22d3ee,color:#e2e8f0
    class P pres
    class L logic
    class D data
```

---

## 2. 3-Tier 컴포넌트 구조

```mermaid
flowchart TB
    subgraph PRES["🖥️ Presentation Layer (app/ui)"]
        main["main.py<br/>진입점 · DI 조립"]
        modeB["mode_b.py<br/>(현재 유일 활성 모드)"]
        modeA["mode_a.py<br/>(숨김 · 코드 보존)"]
        theme["theme.py<br/>다크 모던 테마"]
        dataloader["data_loader.py<br/>(다중 형식 업로드)"]
        progress["progress.py"]
        resultview["result_view.py<br/>(비용 카드 포함)"]
        resultchat["result_chat.py"]
    end

    subgraph LOGIC["🧠 Logic Layer (app/agents)"]
        orch["orchestrator.py<br/>통합 개선 루프 · 비용 추적"]
        plan["plan_agent.py<br/>(시계열 지원)"]
        code["code_agent.py<br/>(seed·다중공선성 규칙)"]
        evalA["eval_agent.py<br/>(다중공선성 · PII 마스킹)"]
        chat["chat_agent.py"]
        spec["spec_agent.py 🆕<br/>(명세서 자동 분석)"]
        validator["validator.py<br/>(보안 화이트리스트)"]
        mlgates["ml_gates.py 🆕<br/>(AST 기반 · 6개 게이트)"]
    end

    subgraph DATA["🗄️ Data Layer"]
        loader["csv_loader.py<br/>(다중 형식 읽기)"]
        specloader["spec_loader.py 🆕"]
        anonymizer["anonymizer.py 🆕<br/>(PII 탐지·마스킹)"]
        executor["code_executor.py"]
        store["session_store.py"]
        base["base.py<br/>LLMProvider (추상)"]
        caching["caching_provider.py 🆕<br/>(응답 캐싱)"]
        anthropic["anthropic_provider.py<br/>(비용 추적)"]
    end

    subgraph DOMAIN["📦 Domain (app/domain/models.py)"]
        models["DTO / 엔티티<br/>Plan · Result · Session ..."]
    end

    main --> modeB & theme
    main -.import만 유지·화면 미표시.-> modeA
    modeB --> dataloader & progress & resultview
    resultview --> resultchat
    modeB --> orch

    orch --> plan & code & evalA & chat & spec
    orch --> validator
    code --> mlgates
    evalA --> anonymizer
    orch --> loader & specloader & executor & store
    plan & code & evalA & chat & spec -->|의존| base
    base -.구현.-> caching
    caching -.감쌈.-> anthropic

    LOGIC -.->|uses| DOMAIN
    DATA -.->|uses| DOMAIN

    classDef pres fill:#1e293b,stroke:#6366f1,color:#e2e8f0
    classDef logic fill:#312e81,stroke:#818cf8,color:#e2e8f0
    classDef data fill:#164e63,stroke:#22d3ee,color:#e2e8f0
    classDef dom fill:#3f3f46,stroke:#a1a1aa,color:#e2e8f0
    classDef hidden fill:#292524,stroke:#78716c,color:#a8a29e,stroke-dasharray: 4 3
    class main,modeB,theme,dataloader,progress,resultview,resultchat pres
    class modeA hidden
    class orch,plan,code,evalA,chat,spec,validator,mlgates logic
    class loader,specloader,anonymizer,executor,store,base,caching,anthropic data
    class models dom
```

---

## 3. Mode B 전체 파이프라인 시퀀스 (현재 유일 활성 흐름)

```mermaid
sequenceDiagram
    autonumber
    actor U as 사용자
    participant UI as mode_b (UI)
    participant O as Orchestrator
    participant AN as anonymizer
    participant SA as SpecAgent
    participant PA as PlanAgent
    participant ST as SessionStore
    participant IMP as 통합 개선 루프
    participant LLM as Claude API (캐싱 경유)

    rect rgb(30,41,59)
    Note over U,LLM: 0단계 — 데이터 불러오기 + (선택) 명세서 자동 분석
    U->>UI: 데이터 파일 업로드 (CSV/Excel/JSON/TSV 등)
    UI->>UI: 컬럼 자동 감지 + PII 스캔(anonymizer)
    opt 명세서 파일 첨부됨
        UI->>O: parse_spec(columns, spec_text)
        O->>AN: mask_text(spec_text)
        AN-->>O: 마스킹된 텍스트
        O->>SA: extract(columns, masked_text)
        SA->>LLM: chat (컬럼 설명·타겟·유형 추출)
        LLM-->>SA: JSON
        SA-->>O: 컬럼 설명 + 타겟 + task_type
        O-->>UI: 폼 자동 채움 + 분석 비용
    end
    UI->>U: 컬럼 폼 표시 (🔒PII 배지 포함)
    end

    rect rgb(238,242,255)
    Note over U,LLM: 1단계 — 분석 방향 3개 제안
    U->>UI: 타겟·유형 확정 + [제안받기]
    UI->>O: propose_plans(request)
    O->>PA: propose_plans_mode_b(schema, task_type, time_column)
    loop 서로 다른 알고리즘 3개 보장 (최대 3회)
        PA->>LLM: chat (3개 계획 요청)
        LLM-->>PA: JSON 배열
    end
    PA-->>O: [Plan1, Plan2, Plan3]
    O->>ST: save(session, AWAITING_SELECTION)
    O-->>UI: 3개 방향 + 계획 수립 비용
    UI->>U: 방향 라디오 표시
    end

    rect rgb(236,254,255)
    Note over U,LLM: 2단계 — 선택 실행 (통합 개선 루프, 최대 3라운드)
    U->>UI: 방향 선택 + [분석 시작]
    UI->>O: execute_selected_plan(session_id, plan_id)
    O->>ST: get(session_id)
    loop 최대 3라운드 — 성능 개선 또는 '신뢰 가능' 판정까지
        O->>IMP: 코드생성 — 게이트 검증 → 실행 → 진단
        IMP->>LLM: chat (코드 생성, 위반 시 재생성 최대 3회)
        IMP->>LLM: chat (결과 진단 해석)
        IMP-->>O: 결과 + 성능 점수 + 진단 verdict
        O-->>UI: 라운드별 성능 · 비용(⚡캐시 재사용 시 $0)
    end
    O-->>UI: 가장 성능 좋은 결과 채택 + 총 비용
    UI->>U: 결과 6탭(비용 카드 포함) + 챗봇
    end
```

> Mode A(자연어 목표 입력)는 `run_mode_a()`로 코드가 남아있지만 현재 UI에서 숨겨져 있다. 흐름은 위 1·2단계를 하나로 합친 것과 동일하다(사용자 선택 단계만 없음).

---

## 4. 세션 상태 머신

```mermaid
stateDiagram-v2
    [*] --> PENDING: 세션 생성

    PENDING --> PLANNING: 데이터 로드 완료

    state "Mode B 분기" as fork <<choice>>
    PLANNING --> fork
    fork --> AWAITING_SELECTION: Mode B (3개 제안) — 현재 경로
    fork --> GENERATING: Mode A (단일 계획) — 현재 비활성

    AWAITING_SELECTION --> GENERATING: 사용자 선택

    GENERATING --> RUNNING: 검증 통과
    RUNNING --> COMPLETED: 실행 성공

    PLANNING --> FAILED: 오류
    GENERATING --> FAILED: 검증 실패
    RUNNING --> FAILED: 실행 오류

    COMPLETED --> [*]
    FAILED --> [*]
```

> `GENERATING ↔ RUNNING` 구간은 이제 내부적으로 최대 3라운드 반복되지만(통합 개선 루프), 세션 레벨에서 보이는 상태 자체는 동일하다 — 반복은 상태 전이가 아니라 같은 상태 안에서의 재시도이기 때문이다.

---

## 5. 통합 개선 루프 (Orchestrator._run_improvement_loop)

```mermaid
flowchart TD
    start(["_run_improvement_loop 시작"]) --> round["라운드 i 시작 (i = 1..3)"]
    round --> gen["CodeAgent.generate_code<br/>이전 피드백 반영"]

    subgraph GATE["코드 생성 내부 루프 (최대 3회)"]
        gen --> llmcall["LLM chat 호출"]
        llmcall --> gatecheck{"ml_gates.run_all<br/>6개 게이트 위반?"}
        gatecheck -->|위반 + 시도<3| gatefeedback["위반 내용을 대화에 추가"]
        gatefeedback --> llmcall
        gatecheck -->|위반 없음 또는 시도=3| gatedone["코드 확정"]
    end

    gatedone --> validate["Validator: 보안 화이트리스트"]
    validate -->|실패| fail(["FAILED 반환"])
    validate -->|통과| exec["Executor: 코드 실행"]

    exec -->|실행 오류 + 이전 성공 있음| usebest["직전 성공 결과 사용"]
    exec -->|실행 오류 + 이전 성공 없음 + 재시도 가능| feedback2["오류를 피드백으로 재시도"]
    feedback2 --> round
    exec -->|실행 성공| diagnose["EvalAgent: 결과 진단<br/>(PII 마스킹 후 LLM 호출)"]

    diagnose --> score["성능 점수 계산 + best 결과 갱신"]
    score --> verdict{"진단 판정"}
    verdict -->|신뢰 가능| stop(["루프 종료 — best 채택"])
    verdict -->|주의·불신 + 라운드<3| feedback3["진단 피드백으로 재시도"]
    feedback3 --> round
    verdict -->|라운드=3| stop
    usebest --> stop

    classDef ok fill:#064e3b,stroke:#10b981,color:#e2e8f0
    classDef warn fill:#78350f,stroke:#f59e0b,color:#e2e8f0
    classDef bad fill:#7f1d1d,stroke:#ef4444,color:#fff
    class stop,gatedone ok
    class gatefeedback,feedback2,feedback3,usebest warn
    class fail bad
```

**교체 이력**: 이전에는 "코드 생성 재시도 루프"(회색 `GATE` 서브그래프만) 하나뿐이었다. 지금은 그 바깥에 **전처리·모델 개선을 포괄하는 3라운드 루프**가 추가되어 이중 구조가 됐다 — 안쪽 루프는 "규칙 위반 여부", 바깥 루프는 "성능이 충분히 좋은가"를 본다.

---

## 6. ML 방법론 게이트 6종 (AST 기반)

```mermaid
flowchart LR
    code["생성된 코드"] --> ast["AST 파싱<br/>ast.parse"]

    ast --> g1["① check_leakage<br/>테스트 데이터로 fit 금지<br/>(변수 별칭 추적)"]
    ast --> g2["② check_cv_integrity<br/>CV 탐색은 학습 데이터로만"]
    ast --> g3["③ check_smote_order<br/>SMOTE는 split 이후"]
    ast --> g4["④ check_evaluation<br/>최종 평가는 X_test로"]
    ast --> g5["⑤ check_timeseries_split<br/>시계열은 shuffle=False"]
    ast --> g6["⑥ check_reproducibility<br/>random_state 고정"]

    g1 & g2 & g3 & g4 & g5 & g6 --> agg["run_all — 위반 목록 취합"]
    agg --> decision{"위반 있음?"}
    decision -->|있음| retry["CodeAgent에 피드백<br/>→ 재생성"]
    decision -->|없음| pass(["검증 통과"])

    classDef gate fill:#312e81,stroke:#818cf8,color:#e2e8f0
    classDef ok fill:#064e3b,stroke:#10b981,color:#e2e8f0
    classDef warn fill:#78350f,stroke:#f59e0b,color:#e2e8f0
    class g1,g2,g3,g4,g5,g6 gate
    class pass ok
    class retry warn
```

**정규식 → AST 전환 이유**: 정규식은 `X_test`라는 리터럴 문자열만 찾아서, `xt = X_test` 후 `xt`를 쓰면 우회됐다. AST는 sklearn의 고정 반환 순서(`train, test, train, test`)로 실제 역할을 판별하고 변수 별칭 체인을 끝까지 추적하므로 이름을 바꿔도 탐지된다. ⑤·⑥은 이번에 새로 추가된 게이트다.

---

## 7. 결과 진단 로직 (EvalAgent)

```mermaid
flowchart LR
    res["AnalysisResult"] --> rules["룰 기반 체크<br/>_rule_checks"]

    rules --> c1["샘플 수"]
    rules --> c2["성능 임계값<br/>정확도/R²"]
    rules --> c3["클래스 불균형"]
    rules --> c4["다중공선성 🆕<br/>높은 상관관계 피처쌍"]
    rules --> c5["피처 쏠림<br/>누수 시그널"]

    c1 & c2 & c3 & c4 & c5 --> verdict{"종합 판정"}
    verdict -->|critical 존재| v3["❌ 신뢰 어려움"]
    verdict -->|warning 존재| v2["⚠️ 주의 필요"]
    verdict -->|모두 ok| v1["✅ 신뢰 가능"]

    v1 & v2 & v3 --> mask["🔒 mask_text 🆕<br/>타겟 라벨이 PII면 마스킹"]
    mask --> llm["LLM 해석<br/>summary·risks·recommendations"]
    llm --> out["진단 dict"]

    classDef crit fill:#7f1d1d,stroke:#ef4444,color:#fff
    classDef warn fill:#78350f,stroke:#f59e0b,color:#fff
    classDef ok fill:#064e3b,stroke:#10b981,color:#fff
    classDef new fill:#164e63,stroke:#22d3ee,color:#fff
    class v3 crit
    class v2 warn
    class v1 ok
    class c4,mask new
```

---

## 8. 개인정보(PII) 탐지·마스킹 흐름 🆕

```mermaid
flowchart TB
    subgraph DETECT["탐지 (컬럼 로드 시, mode_b.py)"]
        col["컬럼명"] --> namecheck{"이름 패턴 매칭?<br/>이메일·전화·주민번호·주소·카드"}
        namecheck -->|일치| flagged["PII 종류 확정"]
        namecheck -->|불일치| valuecheck["값 샘플 스캔<br/>(최대 50개, 정규식)"]
        valuecheck -->|50% 이상 일치| flagged
        valuecheck -->|미달| clean["일반 컬럼"]
    end

    flagged --> badge["🔒 UI 배지 표시<br/>(컬럼 폼)"]

    flagged --> gate1["명세서 텍스트<br/>→ mask_text 적용"]
    gate1 --> spec["SpecAgent LLM 호출"]

    flagged --> gate2["타겟 라벨 값<br/>(class_distribution 키)<br/>→ mask_text 적용"]
    gate2 --> evalllm["EvalAgent LLM 호출"]

    classDef detect fill:#312e81,stroke:#818cf8,color:#e2e8f0
    classDef gate fill:#164e63,stroke:#22d3ee,color:#e2e8f0
    class namecheck,valuecheck,flagged detect
    class gate1,gate2,spec,evalllm gate
```

> 코드 실행(`exec()`) 자체는 로컬이라 데이터가 밖으로 안 나간다. 이 흐름은 LLM에 텍스트가 실리는 **두 지점**(명세서 분석, 결과 진단)만 막는다.

---

## 9. 도메인 모델 관계

```mermaid
classDiagram
    class AnalysisSession {
        +str id
        +SessionMode mode
        +SessionStatus status
        +DataSchema schema
        +list~AnalysisPlan~ plans
        +AnalysisPlan selected_plan
        +GeneratedCode generated_code
        +AnalysisResult result
    }
    class DataSchema {
        +list~ColumnSpec~ columns
        +str origin
    }
    class ColumnSpec {
        +str name
        +str data_type
        +bool is_target
        +str pii_kind 🆕
    }
    class AnalysisPlan {
        +str title
        +str algorithm_family
        +str feature_strategy
        +str target_column
        +str task_type
        +str time_column 🆕
    }
    class GeneratedCode {
        +str source_code
        +list~str~ dependencies
    }
    class AnalysisResult {
        +dict metrics
        +dict feature_importance
        +str generated_code
    }

    AnalysisSession "1" --> "1" DataSchema
    DataSchema "1" --> "*" ColumnSpec
    AnalysisSession "1" --> "*" AnalysisPlan
    AnalysisSession "1" --> "0..1" GeneratedCode
    AnalysisSession "1" --> "0..1" AnalysisResult
    GeneratedCode ..> AnalysisPlan : plan_id
    AnalysisResult ..> AnalysisSession : session_id
```

> `task_type`은 이제 `"classification" | "regression" | "timeseries"` 세 가지다. `metrics`(딕셔너리)에는 실행마다 `__eval`(진단), `__cost`(비용) 키가 추가로 담긴다.

---

## 10. LLM 교체 및 캐싱 지점 (보안 환경 대응 + 재현성)

```mermaid
flowchart TB
    subgraph agents["Logic Layer 에이전트"]
        PA["PlanAgent"]
        CA["CodeAgent"]
        EA["EvalAgent"]
        CH["ChatAgent"]
        SA["SpecAgent 🆕"]
    end

    iface["LLMProvider (추상 인터페이스)<br/>chat() · get_model_name()<br/>usage_snapshot() · cost_usd()"]

    PA & CA & EA & CH & SA -->|의존| iface

    iface -.구현.-> caching["CachingLLMProvider 🆕<br/>(동일 요청 캐시 재사용)"]
    caching -.감쌈.-> anth["AnthropicProvider<br/>(Claude API · 비용 추적)"]
    iface -.구현 추가 가능.-> ollama["OllamaProvider<br/>(로컬 모델 · 미착수)"]

    anth --> cloud(["☁️ Anthropic Cloud"])
    ollama --> local(["🖥️ 온프레미스 GPU"])

    classDef new fill:#064e3b,stroke:#10b981,color:#e2e8f0
    classDef future fill:#292524,stroke:#78716c,color:#a8a29e,stroke-dasharray: 4 3
    class SA,caching new
    class ollama,local future
```

> 에이전트는 여전히 `LLMProvider` 인터페이스에만 의존한다. `CachingLLMProvider`는 그 인터페이스를 감싸는 데코레이터라 `AnthropicProvider`뿐 아니라 향후 `OllamaProvider`에도 그대로 씌울 수 있다. 상세는 [`deployment-and-local-model.md`](./deployment-and-local-model.md) 참고.
