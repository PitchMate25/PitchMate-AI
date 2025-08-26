# app/graph/router.py
from __future__ import annotations
"""
Router (fixed domain = travel/leisure) with scripted flow.

설계 요약
- 1차 도메인: 여행·레저로 '고정'
- 세그먼트: 캠핑 / 체험(액티비티·가이드투어 등) / 스포츠
- 플로우: 스크립트형 → 항상 step="script_qna"로 라우팅
- 분류 방식:
  (A) 기본: '룰기반' 키워드 매칭으로 세그먼트 결정
  (B) 모호할 때만: params.allow_zero_shot=True 일 때 제로샷 폴백 1회 시도
- 부가:
  - 관련성(0a): 초단문/무의미 입력 차단 플래그
  - FAQ 히트(더미): services.faq_cache가 있으면 통합 가능
출력
  state.outputs["relevance"] = {"related": bool}
  state.outputs["faq"]       = {"hit": False} (placeholder)
  state.outputs["domain"]    = {
      "intent": "script_qna",
      "domain": "travel",
      "segment": "camping|experience|sports|None",
      "subdomain": <동일값 복제(호환)>,
      "confidence": float,
      "via": "rule|zero-shot|default|unrelated",
      "isOnTopic": bool,
      "onTopicScore": float
  }
  state.step = "script_qna"
"""

from typing import Literal, List, Dict, Optional
from pydantic import BaseModel
import re
import unicodedata

from .state import GraphState
from core.llm import ask_llm  # ✅ PitchMate-AI 레포 구조에 맞춘 임포트

# ===== Label space / thresholds =====
INTENTS: List[str] = [
    "script_qna", "ideate", "feedback_quick", "summary", "research", "revenue", "write"
]

DOMAINS: List[str] = ["travel", "finance", "environment", "general", "other"]

CONF_THRESHOLD: float = 0.55
CONF_STRONG_RULE: float = 0.90
MAX_HISTORY_TURNS: int = 3
UNRELATED_MIN_LEN: int = 2

# 온토픽 판정 임계값(필요 시 0.25~0.35 사이에서 조정 권장)
ON_TOPIC_THRESHOLD: float = 0.28

# ===== Segment keywords (KR/EN) =====
SEGMENTS: List[str] = ["camping", "experience", "sports"]

SEGMENT_KEYWORDS: Dict[str, List[str]] = {
    "camping": [
        "캠핑", "텐트", "오토캠핑", "글램핑", "카라반", "차박", "야영",
        "camp", "camping", "tent", "rv", "caravan", "glamping"
    ],
    "experience": [
        "체험", "액티비티", "가이드투어", "현지체험", "현지 투어", "워크샵", "쿠킹클래스", "공방",
        "experience", "activity", "guided tour", "local tour", "workshop", "cooking class", "craft"
    ],
    "sports": [
        "스포츠", "서핑", "스키", "스노보드", "등산", "하이킹", "트레킹", "사이클", "자전거",
        "클라이밍", "암벽", "축구", "야구", "골프", "테니스", "마라톤",
        "surf", "ski", "snowboard", "hike", "trek", "hiking", "cycling", "bike",
        "climbing", "soccer", "football", "baseball", "golf", "tennis", "marathon"
    ],
}

# 여행·레저 일반 힌트(세그먼트 키워드 외 공통 힌트)
ON_TOPIC_HINTS: List[str] = [
    "여행", "레저", "관광", "투어", "가이드", "체험", "액티비티", "숙소", "예약", "티켓", "패스"
]

# ===== Models =====
class RouterOutput(BaseModel):
    intent: Literal["script_qna","ideate","feedback_quick","summary","research","revenue","write"]
    domain: Literal["travel","finance","environment","general","other"]
    confidence: float
    subdomain: Optional[str] = None  # 세그먼트를 호환 위해 복제

# ===== Helpers =====
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower().strip()
    s = re.sub(r"[\"'`.,:;()\[\]{}<>~^\-_/\\]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s

def last_user_text(turns) -> str:
    return next((t.content for t in reversed(turns) if getattr(t, "role", "") == "user"), "")

def short_history(turns, k: int = MAX_HISTORY_TURNS) -> str:
    return "\n".join(f"{t.role}: {t.content}" for t in turns[-k:])

def is_unrelated(msg: str) -> bool:
    if len(msg.strip()) < UNRELATED_MIN_LEN:
        return True
    if not re.search(r"[A-Za-z0-9가-힣]", msg):
        return True
    return False

def _keyword_match_any(text: str, words: List[str]) -> bool:
    if not text:
        return False
    t = _norm(text)
    return any(_norm(w) in t for w in words)

def rule_segment(msg: str) -> Optional[str]:
    """세그먼트 룰기반: 다중 히트 중 최다 득표, 동률 시 camping>experience>sports"""
    t = msg or ""
    scores: Dict[str, int] = {}
    for seg in SEGMENTS:
        hits = sum(1 for w in SEGMENT_KEYWORDS[seg] if _keyword_match_any(t, [w]))
        if hits:
            scores[seg] = hits
    if not scores:
        return None
    tie_order = {"camping": 2, "experience": 1, "sports": 0}
    return max(scores.items(), key=lambda kv: (kv[1], tie_order[kv[0]]))[0]

def on_topic_score(msg: str) -> float:
    """여행·레저 관련성 점수(0~1). 일반 힌트 + 세그먼트 키워드 히트 합산."""
    t = _norm(msg or "")
    hits = 0
    for k in ON_TOPIC_HINTS:
        if _norm(k) in t:
            hits += 1
    # 세그먼트 키워드: 하나라도 맞으면 +1
    if any(_keyword_match_any(t, kws) for kws in SEGMENT_KEYWORDS.values()):
        hits += 1
    return min(hits / 5.0, 1.0)

# ===== Zero-shot (옵션 폴백) =====
async def classify_segment_zero_shot(msg: str, hist: str) -> Optional[str]:
    """
    LLM을 사용해 세그먼트를 camping/experience/sports/none 중 하나로 분류합니다.
    성공 시 세그 문자열 반환, 실패/모호하면 None.
    """
    system = (
        "You are a classifier for a travel/leisure chatbot. "
        "Decide which segment the USER is asking about. "
        "Valid labels: camping, experience, sports, none. "
        "Focus on the travel/leisure meanings, not generic sports news. "
        "Respond ONLY compact JSON like: {\"segment\":\"camping\"}"
    )
    user = (
        f"History (last {MAX_HISTORY_TURNS} turns):\n{hist}\n\n"
        f"USER: {msg}\n\n"
        "Return JSON with a single key 'segment' in "
        "[\"camping\",\"experience\",\"sports\",\"none\"]."
    )
    try:
        resp = await ask_llm(
            prompt=user,
            system=system,
            temperature=0.0,
            max_tokens=16,
        )
        import json, re
        m = re.search(r"\{.*\}", resp, re.S)
        data = json.loads(m.group(0)) if m else {}
        seg = (data.get("segment") or "").strip().lower()
        return seg if seg in ("camping", "experience", "sports") else None
    except Exception:
        return None

# ===== Router nodes =====
async def relevance_check_node(state: GraphState) -> GraphState:
    msg = last_user_text(state.turns)
    state.outputs["relevance"] = {"related": not is_unrelated(msg)}
    return state

async def faq_hit_node(state: GraphState) -> GraphState:
    state.outputs["faq"] = {"hit": False}
    return state

async def domain_detect_node(state: GraphState) -> GraphState:
    """
    - 도메인: travel 고정
    - 세그먼트: (1) params.segment → (2) 룰기반 키워드 → (3) allow_zero_shot 폴백 → (4) default(None)
    - step은 항상 "script_qna"
    """
    if state.step in INTENTS:
        state.outputs["domain"] = {
            "routed_step": state.step,
            "via": "explicit"
        }
        return state

    msg = last_user_text(state.turns)
    hist = short_history(state.turns, k=MAX_HISTORY_TURNS)
    params = getattr(state, "params", {}) or {}

    # 0a) 초단문/무문자 입력 필터
    related = state.outputs.get("relevance", {}).get("related", True)
    if not related:
        payload = RouterOutput(
            intent="script_qna", domain="travel", confidence=0.30, subdomain=None
        ).model_dump()
        payload.update({"segment": None, "via": "unrelated", "isOnTopic": False, "onTopicScore": 0.0})
        state.outputs["domain"] = payload
        state.step = "script_qna"
        return state

    # A) 프론트/파라미터 세그먼트 우선
    seg_param = params.get("segment")
    seg = seg_param if seg_param in SEGMENTS else None
    via = "param" if seg else None
    conf = 0.95 if seg else 0.0

    # B) 룰기반 키워드 매칭
    if not seg:
        seg = rule_segment(msg)
        if seg:
            via = "rule"
            conf = CONF_STRONG_RULE  # 0.90

    # C) 모호하면 제로샷 폴백(옵션)
    if not seg and params.get("allow_zero_shot"):
        try:
            z = await classify_segment_zero_shot(msg, hist)
        except Exception:
            z = None
        if z in SEGMENTS:
            seg = z
            via = "zero-shot"
            conf = max(conf, 0.65)

    # D) 여전히 모호하면 default(None)
    if not seg:
        via = via or "default"
        conf = max(conf, 0.50)

    # --- 온토픽 판정(강화 로직) ---
    topic_score = on_topic_score(msg)
    is_on_topic = (topic_score >= ON_TOPIC_THRESHOLD) or bool(seg)
    if not is_on_topic:
        via = "unrelated"
        conf = min(conf, 0.30)

    payload = RouterOutput(
        intent="script_qna",
        domain="travel",
        confidence=conf,
        subdomain=seg
    ).model_dump()
    payload.update({
        "segment": seg,
        "via": via,
        "isOnTopic": is_on_topic,
        "onTopicScore": round(topic_score, 2),
    })

    state.outputs["domain"] = payload
    state.step = "script_qna"
    return state
