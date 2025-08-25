import json
from settings import settings
from core.cache import MultiLayerCache
from core.llm import ask_llm

# 멀티 레이어 캐시
cache = MultiLayerCache()

TOPICS = [
    {"category":"캠핑","season":"가을","aud":"2030 커플"},
    {"category":"서핑","season":"여름","aud":"대학생"},
    {"category":"골프","season":"봄","aud":"직장인 단체"},
]

def _idea_msgs(c,s,a):
    return [
        {"role":"system","content":"너는 여행/레저 창업 아이디어 컨설턴트야."},
        {"role":"user","content":f"""주제:{c}, 시즌:{s}, 타깃:{a}
- 대표 아이디어 3개(각 2줄)
- 강점 1~2개(불릿), BM 한줄.
간결히."""}
    ]

def _stepq_msgs():
    return [
        {"role":"system","content":"넌 단계형 사업계획 질문 마스터야."},
        {"role":"user","content":"문제/시장/고객/BM/운영 영역별 다음 질문 5개를 짧고 구체적으로."}
    ]

def warm_ideas():
    for t in TOPICS:
        text = ask_llm(_idea_msgs(t["category"], t["season"], t["aud"]),
                       scope="ideas_precache", use_cache=True)
        key = json.dumps(t, ensure_ascii=False)
        cache.set("ideas_cards", key, settings.KNOWLEDGE_VERSION, text)

def warm_step_questions():
    text = ask_llm(_stepq_msgs(), scope="stepq_precache", use_cache=True)
    cache.set("stepq", "default", settings.KNOWLEDGE_VERSION, text)

def run_all_precache():
    warm_ideas()
    warm_step_questions()
