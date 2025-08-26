# graph/length_control.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import re

# -----------------------------
# 0) 프리셋
# -----------------------------
LENGTH_PRESETS: Dict[str, Dict[str, int]] = {
    "one_line": {"chars": 140,  "tokens": 50},
    "short":    {"chars": 400,  "tokens": 120},
    "medium":   {"chars": 1200, "tokens": 300},
    "long":     {"chars": 4000, "tokens": 1000},
}

def length_directive(style: str) -> Tuple[str, int]:
    """프롬프트에 붙일 지시문 + 스타일 토큰 상한"""
    preset = LENGTH_PRESETS.get(style, LENGTH_PRESETS["medium"])
    chars, toks = preset["chars"], preset["tokens"]
    text = (
        "Write with explicit length control:\n"
        f"- Target length: '{style}'.\n"
        f"- Hard limits: ≤{chars} characters or the allowed token budget.\n"
        "- Be concise. Avoid filler words.\n"
    )
    return text, toks

# -----------------------------
# 1) 사용자 지시/자동 분류 → 스타일 결정
# -----------------------------
USER_HINTS = {
    "one_line": ["한줄", "한 줄", "슬로건", "엘리베이터", "한문장", "한 문장"],
    "short":    ["짧게", "간단히", "요약", "핵심만"],
    "medium":   ["보통", "중간", "적당히"],
    "long":     ["길게", "자세히", "상세히", "보고서", "전체 초안", "풀버전"],
}

def detect_user_style(user_query: str) -> Optional[str]:
    q = user_query or ""
    for style, hints in USER_HINTS.items():
        if any(h in q for h in hints):
            return style
    return None

def auto_classify_style(user_query: str) -> str:
    q = user_query or ""
    if any(k in q for k in ["슬로건", "한줄", "한 문장"]):
        return "one_line"
    if any(k in q for k in ["요약", "핵심"]):
        return "short"
    if any(k in q for k in ["전체", "초안", "보고서"]):
        return "long"
    return "medium"

def decide_length_style(user_query: str, default: str = "medium") -> str:
    return detect_user_style(user_query) or auto_classify_style(user_query) or default

# -----------------------------
# 2) 토큰/글자 제한
# -----------------------------
class Tokenizer:
    """tiktoken 있으면 사용, 없으면 대략 공백 분할로 폴백."""
    def __init__(self, name: str = "cl100k_base"):
        self._enc = None
        try:
            import tiktoken  # type: ignore
            self._enc = tiktoken.get_encoding(name)
        except Exception:
            self._enc = None

    def encode(self, text: str) -> List[int] | List[str]:
        if self._enc:
            return self._enc.encode(text or "")
        return (text or "").split()  # 폴백(대략)

    def decode(self, ids: List[int] | List[str]) -> str:
        if self._enc:
            return self._enc.decode(ids)  # type: ignore
        return " ".join(ids) if ids and isinstance(ids[0], str) else ""

def enforce_token_cap(text: str, max_tokens: Optional[int], tokenizer: Optional[Tokenizer]) -> str:
    if not isinstance(text, str) or not max_tokens or max_tokens <= 0:
        return text
    tok = tokenizer or Tokenizer()
    ids = tok.encode(text)
    if len(ids) <= max_tokens:
        return text
    try:
        trimmed = tok.decode(ids[:max_tokens])
        return trimmed
    except Exception:
        # 폴백(대략)
        return " ".join(ids[:max_tokens]) if ids and isinstance(ids[0], str) else text[: max_tokens * 4]

# -----------------------------
# 3) 사후 보정(문장/단어 경계 + 마크다운/코드 보호)
# -----------------------------
_SENT_PUNCT = r"[\.!\?。！？…]+"               # 문장부호
_EXPLICIT_END = r"[\n]+|[”’\"'」』\)\]]"       # 줄바꿈/닫힘 기호
_WORD_BOUNDARY = r"[\s,;:/·\-–—]+"            # 단어 경계
_FENCE_TRIPLE = "```"
_FENCE_TILDES = "~~~"
_LINK_TOKENS = ("](", "http://", "https://", "://")

def _balance_fences(text: str) -> str:
    if not isinstance(text, str):
        return text
    if text.count(_FENCE_TRIPLE) % 2 == 1:
        text += "\n" + _FENCE_TRIPLE
    if text.count(_FENCE_TILDES) % 2 == 1:
        text += "\n" + _FENCE_TILDES
    return text

def _inside_code_block(text: str, idx: int) -> bool:
    before = text[:max(0, min(idx, len(text)))]
    return (before.count(_FENCE_TRIPLE) % 2 == 1) or (before.count(_FENCE_TILDES) % 2 == 1)

def _backoff_link_boundary(text: str, cut_idx: int) -> int:
    start = max(0, cut_idx - 6)
    if any(tok in text[start:cut_idx] for tok in _LINK_TOKENS):
        # 가장 가까운 단어 경계로 뒤로 물림
        for m in reversed(list(re.finditer(_WORD_BOUNDARY, text[:cut_idx]))):
            return m.start()
    return cut_idx

def soft_cut(text: str, max_chars: int, add_ellipsis: bool = True) -> str:
    if not isinstance(text, str) or len(text) <= max_chars:
        return _balance_fences(text)
    snippet = text[:max_chars]

    # 1) 문장/줄바꿈/따옴표 경계 우선
    m = list(re.finditer(f"(?:{_SENT_PUNCT}|{_EXPLICIT_END})", snippet))
    cut_idx = m[-1].end() if m else None

    # 2) 없으면 단어 경계
    if cut_idx is None:
        m2 = list(re.finditer(_WORD_BOUNDARY, snippet))
        cut_idx = m2[-1].start() if m2 else len(snippet)

    # 3) 코드블록 내부면 한 칸씩 뒤로
    while cut_idx > 0 and _inside_code_block(text, cut_idx):
        cut_idx -= 1

    # 4) 링크 무결성 보정
    cut_idx = _backoff_link_boundary(text, cut_idx)
    cut_idx = max(1, min(cut_idx, len(snippet)))

    out = text[:cut_idx].rstrip()
    out = _balance_fences(out)
    return (out + "…") if add_ellipsis else out

def enforce_char_cap(text: str, max_chars: int, is_code: bool = False) -> str:
    if not isinstance(text, str):
        return text
    if len(text) <= max_chars:
        return _balance_fences(text)
    if is_code:
        # 코드/JSON 등은 말줄임표를 넣지 않는 편이 안전
        cut = text[:max_chars]
        i = len(cut)
        while i > 0 and _inside_code_block(text, i):
            i -= 1
        return _balance_fences(text[:max(1, i)].rstrip())
    return soft_cut(text, max_chars, add_ellipsis=True)

# -----------------------------
# 4) 제네릭 페이로드 트리머
# -----------------------------
KEY_POLICY = {
    # 텍스트
    "one_liner":    {"type": "text", "max_chars": 140},
    "summary_text": {"type": "text"},
    "plan_md":      {"type": "text"},
    "body":         {"type": "text"},
    "text":         {"type": "text"},
    "content":      {"type": "text"},
    "answer":       {"type": "text"},
    # 코드/JSON
    "code":         {"type": "code"},
    "json":         {"type": "code"},
    # 리스트(문자열 리스트)
    "bullets":      {"type": "list", "max_each": 250, "max_count": 7, "tail": True},
    "outline":      {"type": "list", "max_each": 120, "max_count": 10, "tail": True},
    "items":        {"type": "list", "max_each": 200, "max_count": 10, "tail": True},
}

SKIP_KEYS = {"relevance", "faq", "domain"}

def enforce_bullets(lst: List[str], max_each: int, max_count: int, tail: bool) -> List[str]:
    out = []
    for s in lst[:max_count]:
        out.append(enforce_char_cap(s, max_each))
    remain = max(0, len(lst) - max_count)
    if tail and remain > 0:
        out.append(f"… (+{remain} more)")
    return out

def _trim_value(
    key: Optional[str], value: Any, *,
    style_chars: Optional[int], global_cap: int,
    token_cap: Optional[int], tokenizer: Optional[Tokenizer],
) -> Any:
    if isinstance(value, str):
        policy = KEY_POLICY.get(key or "", {"type": "text"})
        is_code = policy.get("type") == "code"
        # 1) 토큰 컷(텍스트만)
        txt = value
        if not is_code and token_cap:
            txt = enforce_token_cap(txt, token_cap, tokenizer)
        # 2) 문자 컷
        cap_chars = min(policy.get("max_chars", style_chars or global_cap), global_cap)
        return enforce_char_cap(txt, cap_chars, is_code=is_code)

    if isinstance(value, list):
        if all(isinstance(x, str) for x in value):
            policy = KEY_POLICY.get(key or "", {"type": "list"})
            each = min(policy.get("max_each", style_chars or 250), 250)
            cnt = policy.get("max_count", 7)
            tail = policy.get("tail", False)
            return enforce_bullets(value, each, cnt, tail)
        return [
            _trim_value(key, x, style_chars=style_chars, global_cap=global_cap,
                        token_cap=token_cap, tokenizer=tokenizer)
            for x in value
        ]

    if isinstance(value, dict):
        new = {}
        for k, v in value.items():
            if k in SKIP_KEYS:
                new[k] = v
            else:
                new[k] = _trim_value(k, v, style_chars=style_chars, global_cap=global_cap,
                                     token_cap=token_cap, tokenizer=tokenizer)
        return new
    return value

def trim_payload(
    payload: Any, *, length_style: Optional[str], max_chars: int = 4000,
    max_tokens: Optional[int] = None, tokenizer: Optional[Tokenizer] = None
):
    style_chars = LENGTH_PRESETS.get(length_style or "", {}).get("chars") if length_style else None
    # 스타일 토큰과 max_tokens를 보수적으로 min 병합
    style_tokens = LENGTH_PRESETS.get(length_style or "", {}).get("tokens")
    token_cap = None
    if max_tokens is not None or style_tokens is not None:
        candidates = [t for t in [max_tokens, style_tokens] if t is not None]
        token_cap = min(candidates) if candidates else None
    return _trim_value(None, payload, style_chars=style_chars, global_cap=max_chars,
                       token_cap=token_cap, tokenizer=tokenizer)

# -----------------------------
# 5) 파이프라인용 메인(노드 대용)
# -----------------------------

def _to_int(val, default: Optional[int]) -> Optional[int]:
    """안전 캐스팅: None/""/공백 → default, 숫자/숫자문자열 → int"""
    if val is None:
        return default
    if isinstance(val, bool):
        # True/False가 들어오는 이슈 방지
        return int(val)
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        v = val.strip()
        if v == "":
            return default
        try:
            return int(float(v))
        except Exception:
            return default
    return default

async def apply_length_control(state):
    """
    state.inputs['query'] : 유저 질문
    state.outputs         : 생성 결과(dict/str/list)
    state.params:
      - length_style: one_line|short|medium|long (없으면 자동 결정)
      - max_chars: 전역 상한(기본 4000)
      - max_tokens: 토큰 상한(옵션; 생성노드 max_tokens와 min 병합 권장)
    """
    query = getattr(state, "inputs", {}).get("query", "")
    params = getattr(state, "params", {}) or {}

    style = params.get("length_style") or decide_length_style(query, default="medium")

    # ✅ 안전 캐스팅 (None/"" 처리)
    global_cap = _to_int(params.get("max_chars"), 4000) or 4000
    token_cap  = _to_int(params.get("max_tokens"), None)

    # 음수/이상치 방어
    if global_cap <= 0:
        global_cap = 4000
    if token_cap is not None and token_cap <= 0:
        token_cap = None

    tokenizer = Tokenizer()
    trimmed = trim_payload(
        getattr(state, "outputs", {}),
        length_style=style,
        max_chars=global_cap,
        max_tokens=token_cap,
        tokenizer=tokenizer,
    )
    state.outputs = trimmed
    state.params["length_style"] = style
    return state
