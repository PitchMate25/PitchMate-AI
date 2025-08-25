import json, threading
from typing import Dict
from settings import settings
from core.cache import MultiLayerCache
from core.llm import ask_llm

cache = MultiLayerCache()

def _state_key(state: Dict) -> str:
    k = {x:state[x] for x in ["topic","season","audience","phase"] if x in state}
    return json.dumps(k, ensure_ascii=False)

def prefetch_next_turn(state: Dict, last_user_msg: str):
    key = _state_key(state)

    def _job():
        # 다음 질문
        q = ask_llm(
            [{"role":"system","content":"넌 창업 코치야."},
             {"role":"user","content":f"사용자 답변: {last_user_msg}\n다음 턴에 물을 질문 5개만."}],
            scope="next_q", use_cache=True
        )
        cache.set("next_q", key, settings.KNOWLEDGE_VERSION, q)

        # 아이디어 카드
        ideas = ask_llm(
            [{"role":"system","content":"여행/레저 창업 아이디어 큐레이터."},
             {"role":"user","content":f"상태:{key}\n최근 답변:{last_user_msg}\n대표 아이디어 3개와 한줄 강점."}],
            scope="next_idea", use_cache=True
        )
        cache.set("next_idea", key, settings.KNOWLEDGE_VERSION, ideas)

        # 요약
        summ = ask_llm(
            [{"role":"system","content":"메모 요약가."},
             {"role":"user","content":f"최근 대화 핵심 bullet 5개:\n{last_user_msg}"}],
            scope="mini_summary", use_cache=True
        )
        cache.set("mini_summary", key, settings.KNOWLEDGE_VERSION, summ)

    threading.Thread(target=_job, daemon=True).start()
