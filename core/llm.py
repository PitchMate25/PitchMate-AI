import json
from typing import Dict, List, Iterator, Optional
from openai import OpenAI
from settings import settings
from core.cache import MultiLayerCache

# OpenAI 클라이언트 생성
client = OpenAI(api_key=settings.OPENAI_API_KEY)

# 멀티 레이어 캐시 (Redis + 인메모리)
cache = MultiLayerCache()

# 메시지 정규화
def _normalize_messages(messages: List[Dict[str, str]]) -> str:
    """
    LLM 요청 메시지들을 정규화하여 캐시 키 생성을 안정화
    - role의 앞뒤 공백 제거
    - content 내부 공백을 하나로 합침
    - JSON 문자열로 직렬화 (ensure_ascii=False: 한글 깨짐 방지)
    - separators=(",", ":") → 불필요한 공백 제거해 항상 같은 형태 유지
    """
    norm = []
    for m in messages:
        role = m["role"].strip()                                # 공백 제거
        content = " ".join(m["content"].split())                # 공백 합침
        norm.append({"role": role, "content": content})
    return json.dumps(norm, ensure_ascii=False, separators=(",", ":"))

# 비스트리밍 LLM 호출 함수
def ask_llm(messages: List[Dict[str, str]], scope="llm_resp", use_cache=True) -> str:
    """
    LLM에게 메시지를 전달해 최종 응답을 한 번에 받아온다.
    - 캐시를 먼저 확인하고, 있으면 그대로 반환
    - 없으면 OpenAI API 호출 후 캐시에 저장
    - 반환값: 최종 답변 문자열
    """

    # 캐시 키
    key = _normalize_messages(messages) + f"|model={settings.LLM_MODEL}"

    # 캐시 히트 확인
    if use_cache:
        hit = cache.get(scope, key, settings.KNOWLEDGE_VERSION)
    
        # 응답이 있으면 캐시에 저장된 값 바로 반환
        if hit: return hit

    # 캐시 없으면 LLM API 호출
    resp = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=messages,
        temperature=0.7,
    )

    out = resp.choices[0].message.content

    # 캐시에 저장
    if use_cache:
        cache.set(scope, key, settings.KNOWLEDGE_VERSION, out)
    return out

# 스트리밍 LLM 호출 함수
def stream_llm(messages: List[Dict[str, str]],
               scope="llm_resp",
               use_cache=True) -> Iterator[Dict]:
    """
    LLM 응답을 토큰 단위로 스트리밍 (SSE)
    Yields dict events:
      {"event":"meta","data":{...}}
      {"event":"token","data":{"delta":"..."}}
      {"event":"done","data":{"cached":bool}}
    """

    # 캐시 키 생성
    key = _normalize_messages(messages) + f"|model={settings.LLM_MODEL}"

    # 캐시 히트면 재생 (stream-from-cache)
    hit = cache.get(scope, key, settings.KNOWLEDGE_VERSION) if use_cache else None
    yield {"event":"meta","data":{"model":settings.LLM_MODEL, "cached": bool(hit)}}

    if hit is not None:
        # 캐시 텍스트를 토큰 이벤트로 스트리밍
        for ch in hit:
            yield {"event":"token","data":{"delta": ch}}
        # 완료
        yield {"event":"done","data":{"cached": True}}
        # 종료
        return

    # 캐시 미스면 OpenAI 스트림 호출
    # 응답 눈적
    acc = []
    try:
        resp = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=0.7,
            stream=True                     # 스트리밍 
        )

        for chunk in resp:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                text = delta.content
                acc.append(text)            # 누적

                # 토큰 단위 전달
                yield {"event":"token","data":{"delta": text}}

        # 합치지
        final_text = "".join(acc)

        # Redis + 인메모리 캐시에 저장
        cache.set(scope, key, settings.KNOWLEDGE_VERSION, final_text)

        # 완료
        yield {"event":"done","data":{"cached": False}}

    except Exception as e:
        # 예외
        yield {"event":"done","data":{"cached": False, "error": str(e)}}
