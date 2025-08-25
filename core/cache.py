import hashlib, time
from dataclasses import dataclass
from typing import Optional
import redis
from settings import settings

@dataclass
class CacheEntry:
    value: str
    created_at: float
    version: str

def _h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

class MultiLayerCache:
    def __init__(self):
        self._mem = {}  # 인메모리에 저장
        self._r = redis.from_url(settings.REDIS_URL, decode_responses=True)

    def _key(self, scope: str, raw: str, ver: str) -> str:
        return f"pc:{scope}:{ver}:{_h(raw)}"

    # 캐시 조회 (메모리self._mem -> Redis -> 없음)
    def get(self, scope: str, raw: str, ver: str) -> Optional[str]:
        k = self._key(scope, raw, ver)
        v = self._mem.get(k)
        if v: return v.value
        rv = self._r.get(k)
        if rv:
            self._mem[k] = CacheEntry(rv, time.time(), ver)
            return rv
        return None

    # 캐시 저장
    def set(self, scope: str, raw: str, ver: str, value: str, ttl: Optional[int] = None):
        k = self._key(scope, raw, ver)
        self._mem[k] = CacheEntry(value, time.time(), ver)
        self._r.set(k, value, ex=ttl or settings.CACHE_TTL_SECONDS)
