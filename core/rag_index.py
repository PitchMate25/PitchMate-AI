# core/rag_index.py
from typing import List, Tuple
import numpy as np, faiss
from sentence_transformers import SentenceTransformer

# 사전 학습된 경량 임베딩 모델 로드
_model = SentenceTransformer("all-MiniLM-L6-v2")
_index = None                   # FAISS 객체
_docs: List[str] = []

def build_index(docs: List[str]):
    """
    주어진 텍스트 문서 리스트(docs)를 받아서
    1) 임베딩 생성
    2) FAISS 벡터 인덱스를 구축
    3) 검색 대상 문서들을 전역 변수에 저장
    """
    global _index, _docs
    _docs = docs
    # 문장 임베딩 생성 (정규화 = cosine similarity와 동일 효과)
    embs = _model.encode(docs, normalize_embeddings=True)
    dim = embs.shape[1]
    # FAISS 내적 기반 인덱스(IndexFlatIP) 생성
    _index = faiss.IndexFlatIP(dim)
    # float32 형식으로 변환 후 인덱스에 추가
    _index.add(embs.astype(np.float32))


def search(q: str, topk=3) -> List[Tuple[str, float]]:
    """
    검색 함수
    - 쿼리(q)를 임베딩하고, 인덱스에서 top-k 유사 문서를 검색
    - 결과로 (문서내용, 유사도 스코어) 튜플 리스트 반환
    """
    # 쿼리 임베딩 생성
    qemb = _model.encode([q], normalize_embeddings=True).astype(np.float32)
    # FAISS로 top-k 검색
    D, I = _index.search(qemb, topk)   # D=유사도, I=문서 인덱스
    res = []
    for s, idx in zip(D[0], I[0]):
        if idx == -1: 
            continue
        # 해당 문서와 유사도 점수 저장
        res.append((_docs[idx], float(s)))
    return res