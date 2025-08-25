# 1) Python slim 이미지 기반
FROM python:3.11-slim

# 2) 작업 디렉토리 설정
WORKDIR /app

# 3) 필요한 시스템 패키지 설치 (선택: uvicorn 속도 최적화용)
RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*

# 4) requirements.txt 복사 & 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5) 소스 복사
COPY . .

# 6) 환경변수 (실제 키는 .env 파일로 주입)
ENV PYTHONUNBUFFERED=1

# 7) FastAPI 실행 (reload 없이 production용)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
