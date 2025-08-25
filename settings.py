# settings.py
from pydantic import BaseModel
from dotenv import load_dotenv
import os
load_dotenv()

class Settings(BaseModel):
    APP_ENV: str = os.getenv("APP_ENV", "dev")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "86400"))
    SEMANTIC_CACHE_TOPK: int = int(os.getenv("SEMANTIC_CACHE_TOPK", "3"))
    SEMANTIC_CACHE_THRESHOLD: float = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.88"))
    KNOWLEDGE_VERSION: str = os.getenv("KNOWLEDGE_VERSION", "v1")
    REDIS_ENABLED: bool = os.getenv("REDIS_ENABLED", "true").lower() == "true"
    PREWARM_ENABLED: bool = os.getenv("PREWARM_ENABLED", "true").lower() == "true"

        # ★ 모의 스트림 옵션
    MOCK_LLM: bool = os.getenv("MOCK_LLM", "false").lower() == "true"
    MOCK_LATENCY_MS: int = int(os.getenv("MOCK_LATENCY_MS", "50"))

settings = Settings()
