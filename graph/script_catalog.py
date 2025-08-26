# app/graph/script_catalog.py
from __future__ import annotations
from typing import Dict, List, Optional, Any
import re
import unicodedata

# --- 섹션별 슬롯 순서 ---
A_ORDER = ["A1_problem","A2_pain","A3_reason","A4_unmet"]
B_ORDER = ["B1_core_service","B2_value","B3_features","B4_diff","B5_edge"]
C_ORDER = [
    "C1_consumer","C2_alternatives","C3_paincases","C4_market_size",
    "C5_competitors","C6_customer_traits","C7_issues"
]
D_ORDER = [
    "D1_revenue_sources","D2_model","D3_segments","D4_resources",
    "D5_extensions","D6_diff","D7_go_to_market","D8_activation",
    "D9_kpi","D10_trust"
]

SECTION_ORDER: Dict[str, List[str]] = {
    "A": A_ORDER, "B": B_ORDER, "C": C_ORDER, "D": D_ORDER,
}

# --- 기본 질문 텍스트 ---
QUESTIONS: Dict[str, str] = {
    # A. 사업 주제 선정
    "A1_problem": "당신이 주목한 문제나 새로운 기회는 무엇인가요?",
    "A2_pain": "현재 가장 부족하거나 불편한 점은 무엇이라 보나요?",
    "A3_reason": "이 주제를 선택한 계기(시장 분위기, 개인경험, 트렌드 등)가 있나요?",
    "A4_unmet": "기존 시장에서 미충족된 고객 니즈는 무엇이라고 생각하시나요?",
    # B. 사업 정의
    "B1_core_service": "제공할 핵심 서비스/경험은 무엇인가요? (예: 초보자 맞춤 강습+장비 예약 통합, 안전/보험 자동 연동 등)",
    "B2_value": "우리 서비스가 제공하는 '경험/가치'는 무엇인가요?",
    "B3_features": "핵심 서비스/제품/기능은 무엇인가요?",
    "B4_diff": "경쟁사와의 차별화 포인트는?",
    "B5_edge": "경쟁사보다 더 우월한 점/한계점 1가지는?",
    # C. 시장 조사 및 분석
    "C1_consumer": "상품 소비자의 특징(연령, 동기, 지역성 등)을 알고 있나요?",
    "C2_alternatives": "기존 비슷한 온라인/오프라인 서비스는? 차별화 필요성은?",
    "C3_paincases": "고객이 기존 서비스에서 겪는 불편 사례는?",
    "C4_market_size": "",  # 동적 문구
    "C5_competitors": "대표적인 경쟁 서비스(플랫폼/운영 업체)는 무엇이고, 강점/약점은?",
    "C6_customer_traits": "고객(이용자)의 주요 특성(연령, 가족/직장인, 여행 스타일 등)을 어떻게 보나요?",
    "C7_issues": "해당 분야의 주요 이슈나 니즈도 파악되어 있나요?",
    # D. 비즈니스 모델 수립
    "D1_revenue_sources": "사업의 주요 수익원은 무엇인가요? (예: 예약수수료, 장비렌털, 멤버십, 광고 등)",
    "D2_model": "수익 모델은 무엇인가요? (복수예약 중개, 정액 구독, 후기/포인트 프로그램 등)",
    "D3_segments": "주요 고객층은 누구로 설정할 건가요?",
    "D4_resources": "필요 리소스가 있나요?",
    "D5_extensions": "장기적으로 확장 가능한 추가 기능/서비스 아이디어가 있나요?",
    "D6_diff": "유사 서비스와의 차별점은 무엇인가요?",
    "D7_go_to_market": "시장진입 방법(마케팅, 홍보 채널, 첫 파트너 선정기준 등)은?",
    "D8_activation": "고객 확보/활성화 전략(커뮤니티, SNS, MZ 감성 등)은?",
    "D9_kpi": "성공지표(KPI)를 어떻게 정할 것인지?",
    "D10_trust": "서비스 품질보증/신뢰확보 방안은?",
}

SEG_LABEL = {
    None: "여행·레저",
    "camping": "캠핑/글램핑",
    "experience": "현지체험/액티비티",
    "sports": "레저 스포츠(서핑/등산 등)",
}

# --- 키워드 맵(사용자 메시지에 따라 다음 질문 우선순위 결정) ---
KEYWORDS: Dict[str, List[str]] = {
    "D1_revenue_sources": ["수익원","수익","매출","수수료","구독","광고","멤버십","렌털","유료"],
    "B1_core_service": ["핵심 서비스","무엇을 제공","경험 제공","통합","강습","예약"],
    "C4_market_size": ["시장 규모","성장 추세","트렌드","규모"],
    "B4_diff": ["차별화","우월","다름","강점","약점"],
    # 필요한 슬롯 계속 보강 가능
}

# -------- Helpers --------
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower().strip()
    s = re.sub(r"[\"'`.,:;()\[\]{}<>~^\-_/\\]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s

def _dyn_question(slot_id: str, segment: Optional[str]) -> str:
    if slot_id == "C4_market_size":
        label = SEG_LABEL.get(segment, SEG_LABEL[None])
        return f"{label} 시장 규모와 최근 성장 추세에 대해 알고 있나요?"
    return QUESTIONS.get(slot_id, "")

def first_progress() -> Dict[str, Any]:
    return {"section": "A", "index": 0, "answered": []}

def next_progress(progress: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    section = progress.get("section", "A")
    index = int(progress.get("index", 0))
    order = SECTION_ORDER[section]
    index += 1
    if index < len(order):
        return {**progress, "index": index}
    flow = ["A", "B", "C", "D"]
    try:
        nxt_section = flow[flow.index(section) + 1]
    except Exception:
        return None
    return {"section": nxt_section, "index": 0, "answered": progress.get("answered", [])}

def current_question(progress: Dict[str, Any], segment: Optional[str]) -> Optional[Dict[str, str]]:
    section = progress.get("section", "A")
    index = int(progress.get("index", 0))
    order = SECTION_ORDER.get(section)
    if not order or index < 0 or index >= len(order):
        return None
    slot_id = order[index]
    text = _dyn_question(slot_id, segment) or QUESTIONS.get(slot_id, "")
    if not text:
        return None
    return {"id": slot_id, "text": text}

# --- 키워드 점수화 & 다음 질문 선택 ---
def _score_slot(user_text: str, slot_id: str) -> int:
    if not user_text:
        return 0
    t = _norm(user_text)
    kws = KEYWORDS.get(slot_id, [])
    # 단순 포함 개수로 점수화 (실무에선 형태소/시소러스/embeddings로 확장 가능)
    return sum(1 for kw in kws if _norm(kw) in t)

def choose_next_progress(progress: Dict[str, Any], user_text: str) -> Optional[Dict[str, Any]]:
    """
    현재 섹션 내 '미답변' 슬롯들 중 키워드 점수가 가장 높은 질문으로 점프.
    점수가 0이면 기존 선형(next_progress)로 진행.
    """
    section = progress.get("section", "A")
    index = int(progress.get("index", 0))
    answered = set(progress.get("answered", []))
    order = SECTION_ORDER.get(section, [])
    if not order:
        return next_progress(progress)

    remaining = [sid for sid in order if sid not in answered and order.index(sid) >= index + 1]
    if not remaining:
        # 현 질문 바로 다음이 없거나 다 답했으면 섹션 이동
        return next_progress(progress)

    scored = sorted(
        ((sid, _score_slot(user_text, sid)) for sid in remaining),
        key=lambda x: x[1],
        reverse=True
    )
    top_sid, top_score = scored[0]
    if top_score > 0:
        # 해당 슬롯의 인덱스로 점프
        return {**progress, "index": order.index(top_sid)}
    return next_progress(progress)
