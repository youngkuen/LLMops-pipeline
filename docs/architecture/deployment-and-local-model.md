# 배포 전략 및 로컬 모델 교체 가이드

> 패키지 판매 및 보안 제약 환경 대응을 위한 기술 가이드

---

## 1. 배포 · 판매 방식

### 옵션 비교

| 방식 | 타겟 고객 | 수익 모델 | 구현 난이도 |
|------|----------|-----------|------------|
| **Docker 패키지** | 데이터 보안이 중요한 기업 | 라이선스 일시불 / 연간 구독 | ★★ |
| **SaaS** | 개인 데이터 사이언티스트, 스타트업 | 월정액 구독 (Stripe) | ★★★ |
| **API 서비스** | 시스템 통합이 필요한 개발팀 | API 호출 수 과금 | ★★ |

---

### 옵션 A — Docker 패키지 (권장 첫 번째 단계)

**왜 먼저 시작하기 좋은가**
- 현재 Streamlit 코드를 그대로 사용 가능 — 재구성 불필요
- 고객이 자사 서버에 설치하므로 데이터가 외부로 나가지 않음
- Anthropic API 키를 고객이 직접 주입 → 운영 비용 0

**배포 구조**

```
고객 서버
├── docker-compose.yml
│   ├── app (Streamlit)
│   └── (선택) ollama  ← 로컬 모델 사용 시
└── .env
    ├── ANTHROPIC_API_KEY=sk-...   # 또는
    └── LLM_PROVIDER=ollama
```

**`docker-compose.yml` 예시**

```yaml
version: "3.9"
services:
  app:
    image: your-org/ai-model-pipeline:latest
    ports:
      - "8501:8501"
    env_file: .env
    restart: unless-stopped

  ollama:                          # 로컬 모델 사용 시만 포함
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]

volumes:
  ollama_data:
```

**라이선스 통제 방법 (간단한 방식)**

```python
# app/license.py — 시작 시 검증
import os, hashlib, datetime

def verify_license():
    key = os.environ.get("LICENSE_KEY", "")
    expiry_str = key.split(":")[0] if ":" in key else ""
    try:
        expiry = datetime.date.fromisoformat(expiry_str)
        if datetime.date.today() > expiry:
            raise SystemExit("라이선스가 만료되었습니다.")
    except ValueError:
        raise SystemExit("유효하지 않은 라이선스 키입니다.")
```

---

### 옵션 B — SaaS

**추가로 필요한 스택**

```
현재 (Streamlit)
    ↓ 교체
FastAPI (백엔드) + Next.js (프론트엔드)
    +
인증: Auth0 / Supabase Auth
결제: Stripe
배포: AWS ECS / Railway / Render
```

**API 엔드포인트 설계 예시**

```
POST /api/v1/analyze          ← CSV 업로드 + 목표 입력 (Mode A)
POST /api/v1/plans            ← 계획 3가지 제안 (Mode B Step 1)
POST /api/v1/plans/{id}/run   ← 선택한 계획 실행 (Mode B Step 2)
GET  /api/v1/results/{id}     ← 결과 조회
```

---

### 옵션 C — API 서비스

Streamlit UI 없이 FastAPI만 노출하는 방식. 고객사 내부 시스템에 통합할 때 적합.

과금 방식: API 키 발급 → 호출 수 카운트 → 월말 정산 (AWS API Gateway 또는 자체 미들웨어)

---

## 2. 로컬 LLM 교체 (보안 제약 환경)

Anthropic Claude API 사용이 불가한 환경(망 분리, 외부 API 차단 등)을 위한 가이드.

### 교체 범위

현재 코드는 `LLMProvider` 인터페이스로 이미 추상화되어 있어 **Provider 클래스 하나 추가**로 교체 가능.

```
app/providers/
├── base.py                ← LLMProvider 인터페이스 (변경 없음)
├── anthropic_provider.py  ← 기존 (변경 없음)
└── ollama_provider.py     ← 신규 추가
```

**영향받지 않는 컴포넌트 (그대로 사용)**

| 컴포넌트 | 이유 |
|----------|------|
| `ml_gates.py` | 정규식 기반 — LLM 불필요 |
| `validator.py` | AST 파싱 기반 — LLM 불필요 |
| `code_executor.py` | 로컬 Python 실행 — LLM 불필요 |
| `progress.py` / UI | Presentation Layer — LLM 불필요 |

---

### 구현 — `OllamaProvider`

Ollama는 OpenAI 호환 API를 내장하므로 `openai` 패키지로 연결.

```python
# app/providers/ollama_provider.py
from openai import OpenAI
from app.providers.base import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        model: str = "qwen2.5-coder:32b",
        base_url: str = "http://localhost:11434/v1",
    ) -> None:
        self._client = OpenAI(api_key="ollama", base_url=base_url)
        self._model = model

    def chat(self, messages: list[dict], temperature: float = 0.1) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
        )
        return resp.choices[0].message.content
```

**`main.py` 분기 처리**

```python
def _build_orchestrator() -> Orchestrator:
    provider_type = os.environ.get("LLM_PROVIDER", "anthropic")

    if provider_type == "ollama":
        from app.providers.ollama_provider import OllamaProvider
        provider = OllamaProvider(
            model=os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:32b"),
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        )
    else:
        from app.providers.anthropic_provider import AnthropicProvider
        provider = AnthropicProvider(
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
            model=os.environ.get("LLM_MODEL", "claude-sonnet-4-6"),
        )
    ...
```

**`.env` 설정 예시**

```env
# Anthropic 사용 시
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# 로컬 Ollama 사용 시
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5-coder:32b
OLLAMA_BASE_URL=http://localhost:11434/v1
```

---

### 추천 로컬 모델

| 모델 | 코드 생성 품질 | 최소 VRAM | 비고 |
|------|--------------|-----------|------|
| **Qwen2.5-Coder 32B** | ★★★★★ | 24GB | 코드 특화, 한국어 지원 우수 |
| **DeepSeek-Coder-V2** | ★★★★★ | 16GB | 코드 특화, 성능/용량 균형 좋음 |
| **Qwen2.5-Coder 7B** | ★★★☆☆ | 8GB | VRAM 제약 환경용 |
| **Llama 3.1 8B** | ★★★☆☆ | 8GB | 범용, ML 코드는 다소 약함 |

**Ollama 모델 설치**

```bash
ollama pull qwen2.5-coder:32b
# 또는
ollama pull deepseek-coder-v2
```

---

### 로컬 모델 사용 시 주의사항

**코드 생성 품질 보강**

로컬 모델은 Claude 대비 복잡한 ML 코드 품질이 떨어질 수 있다. 두 가지 방법으로 보완:

1. **재시도 횟수 증가** — `code_agent.py`의 `range(3)` → `range(5)`
2. **프롬프트 강화** — `_BASE_RULES`에 예시 코드 스니펫 추가 (few-shot)

**인프라 요구사항**

| 항목 | 권장 사양 |
|------|----------|
| GPU | NVIDIA RTX 3090 / A100 이상 |
| VRAM | 모델 크기에 따라 8~24GB |
| RAM | 32GB 이상 |
| OS | Ubuntu 22.04 (CUDA 12.x) |

---

## 3. 판매 시나리오별 추천 조합

| 고객 유형 | 배포 방식 | LLM |
|----------|----------|-----|
| 보안 중요 대기업 (망분리) | Docker 패키지 | Ollama + Qwen2.5-Coder 32B |
| 보안 중요 대기업 (인터넷 가능) | Docker 패키지 | Anthropic API (고객 키) |
| 중소기업 / 스타트업 | SaaS | Anthropic API (운영사 키, 종량제) |
| 개발팀 시스템 통합 | API 서비스 | Anthropic API 또는 Ollama |
