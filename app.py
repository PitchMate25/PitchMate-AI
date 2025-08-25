from fastapi import FastAPI, BackgroundTasks, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import Dict
import json, time
import asyncio

from settings import settings
from core.llm import ask_llm, stream_llm
from core.prefetcher import prefetch_next_turn
from core.cache import MultiLayerCache
from core.precache_jobs import run_all_precache

# OpenAI 쿼터/레이트 리밋 등 예외 안전 처리
try:
    from openai import RateLimitError, APIError, APIConnectionError, BadRequestError, AuthenticationError
except Exception:  # openai 없음 등
    class RateLimitError(Exception): ...
    class APIError(Exception): ...
    class APIConnectionError(Exception): ...
    class BadRequestError(Exception): ...
    class AuthenticationError(Exception): ...

app = FastAPI(title="Travel Biz Bot")

# CORS (TODO: 일단 *로 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

cache = MultiLayerCache()

class ChatIn(BaseModel):
    session_id: str
    topic: str = "캠핑"
    season: str = "가을"
    audience: str = "2030 커플"
    phase: str = "ideation"
    message: str

def sse_pack(event: str, data: Dict) -> str:
    # SSE 포맷
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

@app.on_event("startup")
def on_startup():
    """
    서버 부팅 시 프리캐싱은 토글 가능 + 실패해도 서버는 계속 뜨도록
    """
    if not settings.PREWARM_ENABLED:
        print("[startup] Prewarm disabled by env (PREWARM_ENABLED=false)")
        return
    try:
        run_all_precache()
        print("[startup] Prewarm completed")
    except RateLimitError as e:
        print("[startup] Prewarm skipped (RateLimit):", e)
    except AuthenticationError as e:
        print("[startup] Prewarm skipped (Auth error):", e)
    except (APIError, APIConnectionError, BadRequestError) as e:
        print("[startup] Prewarm skipped (API error):", e)
    except Exception as e:
        print("[startup] Prewarm skipped (Unexpected):", e)

@app.get("/health")
def health():
    return {"ok": True, "ts": time.time(), "prewarm": settings.PREWARM_ENABLED}

@app.post("/chat")  # 비스트리밍
def chat(in_: ChatIn, background_tasks: BackgroundTasks):
    system = "너는 여행/레저 도메인 창업 아이디어 코치야. 간결하게 구체적으로 답해."
    msgs = [
        {"role":"system","content": system},
        {"role":"user","content": in_.message}
    ]
    try:
        answer = ask_llm(msgs, scope="chat", use_cache=True)
    except RateLimitError:
        raise HTTPException(status_code=429, detail="LLM rate limit/quota exceeded")
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="LLM auth error (check API key)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {e}")

    # 다음 턴 프리페치
    state = {"topic": in_.topic, "season": in_.season, "audience": in_.audience, "phase": in_.phase}
    background_tasks.add_task(prefetch_next_turn, state, in_.message)
    return {"answer": answer}

@app.post("/chat/stream")
def chat_stream(in_: ChatIn, background_tasks: BackgroundTasks):
    """
    MOCK_LLM=true면 OpenAI 대신 모의 토큰을 SSE로 응답
    """
    system = "너는 여행/레저 도메인 창업 아이디어 코치야. 간결하게 구체적으로 답해."
    msgs = [{"role":"system","content": system},
            {"role":"user","content": in_.message}]

    async def mock_generator():
        # 메타 이벤트
        yield sse_pack("meta", {"model": "mock-llm", "cached": False})
        # 가짜 응답 -> 토큰
        fake = (
            "테스트 응답입니다. MZ세대 대상 캠핑 창업 아이디어 3가지를 예시로 흘려보낼게요. "
            "1) 글램핑 기반 주말 원데이 체험 패키지, "
            "2) 차박 초보자 스타터 키트 구독, "
            "3) 반려동물 동반 캠핑장 큐레이션 플랫폼. "
            "각 아이디어는 수익모델과 차별화 포인트로 확장 가능합니다."
        )
        for ch in fake:
            await asyncio.sleep(settings.MOCK_LATENCY_MS / 1000)
            yield sse_pack("token", {"delta": ch})
        yield sse_pack("done", {"cached": False})

    def real_generator():
        try:
            for ev in stream_llm(msgs, scope="chat", use_cache=True):
                yield sse_pack(ev["event"], ev["data"])
        except RateLimitError as e:
            yield sse_pack("done", {"error": "rate_limit", "detail": str(e)})
            return
        except AuthenticationError as e:
            yield sse_pack("done", {"error": "auth_error", "detail": str(e)})
            return
        except Exception as e:
            yield sse_pack("done", {"error": "server_error", "detail": str(e)})
            return

        state = {"topic": in_.topic, "season": in_.season, "audience": in_.audience, "phase": in_.phase}
        background_tasks.add_task(prefetch_next_turn, state, in_.message)

    # MOCK 경로와 REAL 경로 분리
    if settings.MOCK_LLM:
        return StreamingResponse(mock_generator(), media_type="text/event-stream")
    else:
        return StreamingResponse(real_generator(), media_type="text/event-stream")

@app.get("/prefetch")
def get_prefetch(
    topic: str = Query(...),
    season: str = Query(...),
    audience: str = Query(...),
    phase: str = Query(...)
):
    key = json.dumps({"topic":topic,"season":season,"audience":audience,"phase":phase}, ensure_ascii=False)
    return {
        "next_questions": cache.get("next_q", key, settings.KNOWLEDGE_VERSION),
        "next_ideas": cache.get("next_idea", key, settings.KNOWLEDGE_VERSION),
        "mini_summary": cache.get("mini_summary", key, settings.KNOWLEDGE_VERSION),
    }
