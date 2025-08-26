from __future__ import annotations
from typing import Optional, Dict, Any
from fastapi import FastAPI
from pydantic import BaseModel

from graph.state import GraphState
from graph.router import relevance_check_node, domain_detect_node
from graph.length_control import apply_length_control
from graph.nodes_script import script_qna_node   # ✅ 추가: 질문 스크립트 노드

app = FastAPI(title="Router+LengthControl Local Smoke")

class ChatRequest(BaseModel):
    message: str
    segment: Optional[str] = None
    allow_zero_shot: bool = False
    script_progress: Optional[Dict[str, Any]] = None
    last_slot: Optional[str] = None
    length_style: Optional[str] = None
    max_chars: Optional[int] = None
    max_tokens: Optional[int] = None

class ChatResponse(BaseModel):
    domain: Dict[str, Any]
    script: Dict[str, Any]
    params: Dict[str, Any]

class _Msg:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    st = GraphState()
    st.turns = [_Msg("user", req.message)]
    st.params = {
        "segment": req.segment,
        "allow_zero_shot": req.allow_zero_shot,
        "script_progress": req.script_progress,
        "last_slot": req.last_slot,
        "length_style": req.length_style,
        "max_chars": req.max_chars,
        "max_tokens": req.max_tokens,
    }
    st.outputs = {}
    st.step = ""

    # 1) 온토픽/세그먼트 판정
    st = await relevance_check_node(st)
    st = await domain_detect_node(st)

    # 2) 질문 스텝(스크립트) 진행 ✅
    st = await script_qna_node(st)

    # 3) 길이 제한(응답 payload 후가공)
    st = await apply_length_control(st)

    return ChatResponse(
        domain=st.outputs.get("domain", {}),
        script=st.outputs.get("script", {}),
        params=st.params or {},
    )
