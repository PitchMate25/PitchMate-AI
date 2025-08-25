## 🗂️ 프로젝트 구조
```
.
├── app.py # FastAPI 엔트리포인트 (엔드포인트 정의)
├── core/
│ ├── cache.py # 멀티 레이어 캐시 (메모리 + Redis)
│ ├── llm.py # OpenAI 호출 래퍼 (ask_llm, stream_llm)
│ ├── precache_jobs.py # 서버 부팅 시 실행되는 Prewarm 작업
│ ├── prefetcher.py # 한 턴 뒤에 다음 턴 질문/아이디어/요약 미리 캐싱
│ ├── knowledge_pack.py # 여행/레저 관련 도메인 지식 (RAG 시드 데이터)
│ ├── rag_index.py # SentenceTransformer + FAISS 기반 RAG 검색
├── settings.py # 환경변수/설정 관리
├── requirements.txt # Python 패키지 의존성
├── Dockerfile # API 컨테이너 빌드 설정
├── docker-compose.yml # API + Redis 실행 환경
└── README.md # 프로젝트 소개
```
---
## ⚙️ 설치 및 실행

### 1) 로컬 실행
```bash
# 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate

# 패키지 설치
pip install -r requirements.txt

# 서버 실행
uvicorn app:app --reload --port 8000

# 빌드 & 실행
docker compose up --build

# API 서버: http://localhost:8000
# Redis:     localhost:6379

```

---
## 📡 API 엔드포인트

`GET /health` → 서버 상태 확인

`POST /chat` → 비스트리밍 답변

`POST /chat/stream` → SSE 스트리밍 답변

`GET /prefetch?topic=...&season=...&audience=...&phase=...` → 프리페치 결과 조회

