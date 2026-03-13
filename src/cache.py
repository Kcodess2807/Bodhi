"""Redis cache layer (Tier 2) — sub-millisecond reads for session and entity data."""

import json
import os

import redis


def _default_redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://localhost:6379")


class BodhiCache:
    """Cache-aside wrapper around Redis.

    Key patterns:
        entity:{company}     — company context (TTL 24h)
        session:{session_id} — live session scores/phase (TTL 2h)
    """

    def __init__(self, redis_url: str | None = None):
        url = redis_url or _default_redis_url()
        self.r = redis.from_url(url, decode_responses=True)

    def ping(self) -> bool:
        try:
            return self.r.ping()
        except redis.ConnectionError:
            return False

    # ── Entity cache ──────────────────────────────────────────────

    def get_entity(self, company: str) -> str | None:
        """Return cached company context or None on miss."""
        return self.r.get(f"entity:{company.lower().strip()}")

    def set_entity(self, company: str, context: str, ttl: int = 86400) -> None:
        self.r.setex(f"entity:{company.lower().strip()}", ttl, context)

    # ── Session cache ─────────────────────────────────────────────

    def save_session_state(
        self, session_id: str, data: dict, ttl: int = 7200,
    ) -> None:
        """Persist session snapshot (scores, phase, difficulty) in Redis."""
        self.r.setex(f"session:{session_id}", ttl, json.dumps(data))

    def get_session_state(self, session_id: str) -> dict | None:
        raw = self.r.get(f"session:{session_id}")
        if raw is None:
            return None
        return json.loads(raw)

    def delete_session(self, session_id: str) -> None:
        self.r.delete(f"session:{session_id}")

    # ── RAG context cache ─────────────────────────────────────────

    def get_rag_context(self, company: str, role: str) -> str | None:
        """Return cached RAG context for a company+role, or None on miss."""
        key = f"rag:{company.lower().strip()}:{role.lower().strip()}"
        return self.r.get(key)

    def set_rag_context(
        self, company: str, role: str, context: str, ttl: int = 3600,
    ) -> None:
        """Cache assembled RAG context (1-hour TTL by default)."""
        key = f"rag:{company.lower().strip()}:{role.lower().strip()}"
        self.r.setex(key, ttl, context)

    # ── Suggested topics cache ─────────────────────────────────────

    def get_topics(self, company: str, role: str) -> list[str] | None:
        """Return cached suggested interview topics, or None on miss."""
        key = f"topics:{company.lower().strip()}:{role.lower().strip()}"
        raw = self.r.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    def set_topics(
        self, company: str, role: str, topics: list[str], ttl: int = 86400,
    ) -> None:
        """Cache suggested topics extracted from uploaded documents (24h TTL)."""
        key = f"topics:{company.lower().strip()}:{role.lower().strip()}"
        self.r.setex(key, ttl, json.dumps(topics))
