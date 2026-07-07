# ── 이사님모델 실행 환경을 통째로 담는 도커 이미지 레시피 ──
# 이 파일 하나면 "어느 컴퓨터든 동일하게" 앱을 실행할 수 있다.

# 1) 파이썬 3.11이 미리 깔린 가벼운 리눅스에서 시작
FROM python:3.11-slim

# 2) xgboost·lightgbm이 실행 시 필요로 하는 OpenMP 런타임(libgomp1) 설치
#    (slim 이미지엔 없어서, 없으면 모델 학습이 import 단계에서 실패한다)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 3) 앱 코드가 놓일 작업 폴더
WORKDIR /app

# 4) 의존성 목록을 먼저 복사해 설치한다.
#    코드보다 먼저 하면, 코드만 바뀔 때 이 무거운 설치 단계는 캐시를 재사용한다.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5) 애플리케이션 코드와 Streamlit 설정 복사 (테스트·문서·비밀키는 안 넣는다)
COPY app/ ./app/
COPY .streamlit/ ./.streamlit/

# 6) `from app...` import가 되도록 저장소 루트를 모듈 경로에 추가
ENV PYTHONPATH=/app

# 7) Streamlit 기본 포트를 외부에 알림
EXPOSE 8501

# 8) 컨테이너가 정상인지 확인 (Streamlit 내장 헬스 체크 주소)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

# 9) 실행 — 컨테이너 밖에서 접속 가능하도록 0.0.0.0에 바인딩
CMD ["streamlit", "run", "app/main.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
