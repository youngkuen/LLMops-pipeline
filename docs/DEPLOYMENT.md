# 배포 가이드 — Streamlit Community Cloud (무료)

포트폴리오용 라이브 데모를 무료로 띄우는 방법. 면접관이 코드를 읽지 않고도 직접 눌러볼 수 있게 됩니다.

> **전제**: 이 프로젝트가 GitHub 공개 레포에 push되어 있어야 합니다.

---

## 1. GitHub에 push

```bash
cd automl-pipeline
gh repo create automl-pipeline --public --source=. --push
# gh CLI가 없으면 GitHub에서 빈 레포를 만든 뒤:
#   git remote add origin https://github.com/<사용자명>/automl-pipeline.git
#   git push -u origin main
```

## 2. Streamlit Community Cloud 연결

1. [share.streamlit.io](https://share.streamlit.io) 접속 → GitHub 계정으로 로그인
2. **New app** → 방금 push한 레포 선택
3. 설정값:
   - **Branch**: `main`
   - **Main file path**: `app/main.py`
4. **Deploy** 클릭

## 3. API 키를 Secrets로 주입 (중요)

API 키는 **절대 코드/레포에 넣지 않고**, Streamlit Cloud의 Secrets 기능으로 주입합니다.

앱 대시보드 → **Settings → Secrets** 에 아래를 입력:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
LLM_MODEL = "claude-sonnet-4-6"
```

> 이 값은 서버 환경변수로 앱에 전달되며, `os.environ.get("ANTHROPIC_API_KEY")`로 코드가 읽습니다.
> 로컬의 `.env`와 동일한 역할을 클라우드에서 하는 것입니다.

## 4. 배포 후 확인

- 앱 URL(`https://<이름>.streamlit.app`)이 발급됩니다 → README 상단에 링크로 추가하면 좋습니다.
- **공개 데모에는 반드시 공개 데이터셋만 사용하세요** (예: California Housing). 회사/실데이터 업로드 금지.

---

## 비용 주의

- Streamlit Community Cloud 자체는 무료지만, 앱이 호출하는 **Claude API는 사용량만큼 과금**됩니다.
- 공개 데모는 아무나 누를 수 있으므로, 데모용으로 저렴한 모델(예: Haiku)을 쓰거나, API 사용량 한도를 콘솔에서 설정해 두는 것을 권장합니다.
