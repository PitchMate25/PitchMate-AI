# app/graph/nodes_script.py
from __future__ import annotations
from typing import Optional, Dict, Any

from .state import GraphState
from .script_catalog import (
    first_progress, next_progress, current_question, choose_next_progress
)

def _last_user_text(turns) -> str:
    return next((t.content for t in reversed(turns) if getattr(t, "role", "") == "user"), "")

def _get_segment(state: GraphState) -> Optional[str]:
    seg = (state.outputs.get("domain") or {}).get("segment")
    if seg:
        return seg
    return (getattr(state, "params", {}) or {}).get("segment")

async def script_qna_node(state: GraphState) -> GraphState:
    params: Dict[str, Any] = getattr(state, "params", {}) or {}
    domain = state.outputs.get("domain") or {}
    on_topic = domain.get("isOnTopic", True)
    segment = _get_segment(state)

    # 0) 오프토픽: 안내
    if not on_topic:
        state.outputs["script"] = {
            "mode": "notice",
            "message": "이 챗봇은 여행·레저(캠핑/체험/스포츠) 전용입니다. 원하는 세그먼트를 알려주세요. 예) \"캠핑으로 할래요\"",
        }
        return state

    # 1) 진행도
    progress: Dict[str, Any] = params.get("script_progress") or first_progress()
    user_text = _last_user_text(state.turns).strip()

    # 2) 방금 질문에 답했다면 기록하고 다음 질문 선택
    asked_slot = params.get("last_slot")
    curr_q = current_question(progress, segment)
    if asked_slot and curr_q and asked_slot == curr_q["id"] and user_text:
        answered = set(progress.get("answered", []))
        answered.add(asked_slot)
        progress["answered"] = list(answered)
        # 키워드 기반 점프 → 없으면 선형
        nxt = choose_next_progress(progress, user_text) or next_progress(progress)
        if nxt is not None:
            progress = nxt

    # 3) 현재 질문
    q = current_question(progress, segment)
    if q is None:
        state.outputs["script"] = {
            "mode": "end",
            "message": "모든 핵심 질문을 수집했습니다. 원하시면 요약이나 사업계획서 초안을 생성해 드릴게요.",
            "progress": None,
        }
        return state

    # 4) 질문 1개 반환
    state.outputs["script"] = {
        "mode": "ask",
        "question": q["text"],
        "slot_key": q["id"],
        "section": progress["section"],
        "progress": progress,
    }
    return state
