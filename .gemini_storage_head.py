"""NeonDB PostgreSQL persistence layer (Tier 3) ΓÇö permanent interview records."""

import json
import os
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras


def _default_database_url() -> str:
    return os.getenv("DATABASE_URL", "")


_DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    candidate_name  TEXT NOT NULL,
    target_company  TEXT NOT NULL,
    target_role     TEXT NOT NULL,
    clerk_user_id   TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    overall_score   REAL,
    summary         TEXT
);

CREATE TABLE IF NOT EXISTS transcripts (
    id          SERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id),
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    phase       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS phase_results (
    id                 SERIAL PRIMARY KEY,
    session_id         TEXT NOT NULL REFERENCES sessions(id),
    phase              TEXT NOT NULL,
    score              REAL,
    question_count     INT,
    difficulty_reached INT,
    feedback_json      TEXT
);

CREATE TABLE IF NOT EXISTS entities (
    id               SERIAL PRIMARY KEY,
    company_name     TEXT NOT NULL UNIQUE,
    description      TEXT,
    hiring_patterns  TEXT,
    tech_stack       TEXT,
    contributed_by   TEXT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_profiles (
    id              SERIAL PRIMARY KEY,
    company_name    TEXT NOT NULL,
    role            TEXT NOT NULL,
    description     TEXT,
    hiring_patterns TEXT,
    tech_stack      TEXT,
    contributed_by  TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(company_name, role)
);

CREATE TABLE IF NOT EXISTS company_documents (
    id              SERIAL PRIMARY KEY,
    company_name    TEXT NOT NULL,
    role            TEXT NOT NULL,
    chunk_text      TEXT NOT NULL,
    chunk_index     INT NOT NULL,
    source_label    TEXT DEFAULT '',
    embedding       vector(3072) NOT NULL,
    contributed_by  TEXT DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS role_profiles (
    id              SERIAL PRIMARY KEY,
    role_name       TEXT NOT NULL UNIQUE,
    description     TEXT DEFAULT '',
    focus_areas     TEXT DEFAULT '',
    typical_topics  TEXT DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS phase_memories (
    id          SERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id),
    phase       TEXT NOT NULL,
    summary     JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(session_id, phase)
);

CREATE TABLE IF NOT EXISTS answer_scores (
    id            SERIAL PRIMARY KEY,
    session_id    TEXT NOT NULL REFERENCES sessions(id),
    phase         TEXT NOT NULL,
    question_num  INT NOT NULL,
    accuracy      INT,
    depth         INT,
    communication INT,
    confidence    INT,
    composite     REAL,
    feedback      TEXT,
    probed        BOOLEAN DEFAULT FALSE,
    probe_reason  TEXT DEFAULT '',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transcripts_session ON transcripts(session_id);
CREATE INDEX IF NOT EXISTS idx_phase_results_session ON phase_results(session_id);
CREATE INDEX IF NOT EXISTS idx_entities_company ON entities(company_name);
CREATE INDEX IF NOT EXISTS idx_company_docs_lookup ON company_documents(company_name, role);
CREATE INDEX IF NOT EXISTS idx_role_profiles_name ON role_profiles(role_name);
CREATE INDEX IF NOT EXISTS idx_phase_memories_session ON phase_memories(session_id);
CREATE INDEX IF NOT EXISTS idx_answer_scores_session ON answer_scores(session_id);
"""


class BodhiStorage:
    """Thin wrapper around psycopg2 for NeonDB operations."""

    def __init__(self, database_url: str | None = None):
        self._url = database_url or _default_database_url()
        if not self._url:
            raise ValueError(
                "DATABASE_URL not set. Add your NeonDB connection string to .env"
            )
        self.conn = self._connect()

    def _connect(self):
        conn = psycopg2.connect(
            self._url,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5,
        )
        conn.autocommit = True
        return conn

    def _ensure_conn(self):
        """Reconnect if the connection was dropped by the server."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1")
        except Exception:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = self._connect()

    def init_tables(self) -> None:
        """Create tables if they don't exist."""
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(_DDL)
            # Migration to add clerk_user_id to existing tables safely
            try:
                cur.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS clerk_user_id TEXT;")
            except Exception:
                pass

            # Execute the user_profiles table separately so any failure is visible.
            # (psycopg2 multi-statement execute only surfaces the last statement's error.)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    resume_raw_text TEXT NOT NULL,
                    professional_summary JSONB NOT NULL,
                    created_at      TIMESTAMPTZ DEFAULT NOW(),
                    updated_at      TIMESTAMPTZ DEFAULT NOW()
                )
            """)

    def migrate_embedding_dimension(self) -> None:
        """One-time migration: drop and recreate company_documents for new vector(3072) dim.
        WARNING: This drops all existing embedded document data. Run once after upgrading embeddings."""
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS company_documents;")
            cur.execute("""
                CREATE TABLE company_documents (
                    id              SERIAL PRIMARY KEY,
                    company_name    TEXT NOT NULL,
                    role            TEXT NOT NULL,
                    chunk_text      TEXT NOT NULL,
                    chunk_index     INT NOT NULL,
                    source_label    TEXT DEFAULT '',
                    embedding       vector(3072) NOT NULL,
                    contributed_by  TEXT DEFAULT '',
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_company_docs_lookup ON company_documents(company_name, role);
            """)

    def close(self) -> None:
        self.conn.close()

    # ΓöÇΓöÇ Sessions ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

    def create_session(
        self,
        session_id: str,
        candidate_name: str,
        target_company: str,
        target_role: str,
        clerk_user_id: str | None = None,
    ) -> None:
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (id, candidate_name, target_company, target_role, clerk_user_id) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (session_id, candidate_name, target_company, target_role, clerk_user_id),
            )

    def end_session(
        self,
        session_id: str,
        overall_score: float | None = None,
        summary: str = "",
    ) -> None:
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE sessions SET ended_at = %s, overall_score = %s, summary = %s "
                "WHERE id = %s",
                (datetime.now(timezone.utc), overall_score, summary, session_id),
            )

    # ΓöÇΓöÇ Transcripts ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

    def save_transcript_batch(
        self,
        session_id: str,
        messages: list[dict],
        phase: str,
    ) -> None:
        """Bulk-insert messages. Each dict has 'role' and 'content'."""
        if not messages:
            return
        self._ensure_conn()
        rows = [
            (session_id, m["role"], m["content"], phase) for m in messages
        ]
        with self.conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO transcripts (session_id, role, content, phase) "
                "VALUES %s",
                rows,
            )

    # ΓöÇΓöÇ Phase results ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

    def save_phase_result(
        self,
        session_id: str,
        phase: str,
        score: float | None = None,
        question_count: int = 0,
        difficulty_reached: int = 3,
        feedback: list[str] | None = None,
    ) -> None:
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO phase_results "
                "(session_id, phase, score, question_count, difficulty_reached, feedback_json) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    session_id,
                    phase,
                    score,
                    question_count,
                    difficulty_reached,
                    json.dumps(feedback or []),
                ),
            )

    # ΓöÇΓöÇ Phase memories (compacted context) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

    def save_phase_memory(
        self,
        session_id: str,
        phase: str,
        memory: dict,
    ) -> None:
        """Persist a compacted phase memory summary."""
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO phase_memories (session_id, phase, summary) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (session_id, phase) DO UPDATE SET summary = EXCLUDED.summary",
                (session_id, phase, json.dumps(memory)),
            )

    def get_phase_memories(self, session_id: str) -> dict:
        """Load all phase memories for a session from Neon."""
        self._ensure_conn()
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT phase, summary FROM phase_memories WHERE session_id = %s",
                (session_id,),
            )
            result = {}
            for row in cur.fetchall():
                summary = row["summary"]
                if isinstance(summary, str):
                    summary = json.loads(summary)
                result[row["phase"]] = summary
            return result

    # ΓöÇΓöÇ Answer scores (granular per-question scores) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

    def save_answer_score(
        self,
        session_id: str,
        phase: str,
        question_num: int,
        accuracy: int,
        depth: int,
        communication: int,
        confidence: int,
        composite: float,
        feedback: str = "",
        probed: bool = False,
        probe_reason: str = "",
    ) -> None:
        """Persist a single answer score."""
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO answer_scores "
                "(session_id, phase, question_num, accuracy, depth, communication, "
                "confidence, composite, feedback, probed, probe_reason) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (session_id, phase, question_num, accuracy, depth,
                 communication, confidence, composite, feedback, probed, probe_reason),
            )

    # ΓöÇΓöÇ Entities ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

    def get_entity(self, company_name: str) -> dict | None:
        self._ensure_conn()
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM entities WHERE LOWER(company_name) = LOWER(%s)",
                (company_name,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def upsert_entity(
        self,
        company_name: str,
        description: str = "",
        hiring_patterns: str = "",
        tech_stack: str = "",
        contributed_by: str = "",
    ) -> None:
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO entities (company_name, description, hiring_patterns, tech_stack, contributed_by, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (company_name) DO UPDATE SET "
                "description = EXCLUDED.description, "
                "hiring_patterns = EXCLUDED.hiring_patterns, "
                "tech_stack = EXCLUDED.tech_stack, "
                "contributed_by = EXCLUDED.contributed_by, "
                "updated_at = EXCLUDED.updated_at",
                (
                    company_name,
                    description,
                    hiring_patterns,
                    tech_stack,
                    contributed_by,
                    datetime.now(timezone.utc),
                ),
            )

    # ΓöÇΓöÇ Company profiles (company+role granularity) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

    def upsert_company_profile(
        self,
        company_name: str,
        role: str,
        description: str = "",
        hiring_patterns: str = "",
        tech_stack: str = "",
        contributed_by: str = "",
    ) -> None:
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO company_profiles "
                "(company_name, role, description, hiring_patterns, tech_stack, contributed_by, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (company_name, role) DO UPDATE SET "
                "description = EXCLUDED.description, "
                "hiring_patterns = EXCLUDED.hiring_patterns, "
                "tech_stack = EXCLUDED.tech_stack, "
                "contributed_by = EXCLUDED.contributed_by, "
                "updated_at = EXCLUDED.updated_at",
                (
                    company_name, role, description, hiring_patterns,
                    tech_stack, contributed_by, datetime.now(timezone.utc),
                ),
            )

    # ΓöÇΓöÇ Company documents (RAG vector store) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

    def insert_document_chunks(
        self,
        company_name: str,
        role: str,
        chunks_with_embeddings: list[tuple[str, int, list[float]]],
        source_label: str = "",
        contributed_by: str = "",
    ) -> int:
        """Insert chunked+embedded documents. Each tuple: (chunk_text, chunk_index, embedding).
        Returns number of rows inserted."""
        if not chunks_with_embeddings:
            return 0
        self._ensure_conn()
        rows = [
            (company_name, role, text, idx, source_label, str(emb), contributed_by)
            for text, idx, emb in chunks_with_embeddings
        ]
        with self.conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO company_documents "
                "(company_name, role, chunk_text, chunk_index, source_label, embedding, contributed_by) "
                "VALUES %s",
                rows,
            )
        return len(rows)

    def search_similar_chunks(
        self,
        company_name: str,
        role: str,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[dict]:
        """Cosine-similarity search merging role-only general docs + company-specific docs.

        Fetches chunks where:
          - company matches AND (role matches OR role='general')  -- company-specific
          - company='general' AND role matches                    -- role-only general
        """
        self._ensure_conn()
        emb_str = str(query_embedding)
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT chunk_text, 1 - (embedding <=> %s::vector) AS similarity "
                "FROM company_documents "
                "WHERE ("
                "  (LOWER(company_name) = LOWER(%s) AND (LOWER(role) = LOWER(%s) OR role = 'general'))"
                "  OR"
                "  (company_name = 'general' AND LOWER(role) = LOWER(%s))"
                ") "
                "ORDER BY embedding <=> %s::vector "
                "LIMIT %s",
                (emb_str, company_name, role, role, emb_str, top_k),
            )
            return [dict(row) for row in cur.fetchall()]

    # ΓöÇΓöÇ Role profiles ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

    def create_role(
        self,
        role_name: str,
        description: str = "",
        focus_areas: str = "",
        typical_topics: str = "",
    ) -> dict:
        self._ensure_conn()
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "INSERT INTO role_profiles (role_name, description, focus_areas, typical_topics) "
                "VALUES (%s, %s, %s, %s) RETURNING *",
                (role_name, description, focus_areas, typical_topics),
            )
            return dict(cur.fetchone())

    def list_roles(self) -> list[dict]:
        self._ensure_conn()
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM role_profiles ORDER BY role_name")
            return [dict(row) for row in cur.fetchall()]

    def get_role(self, role_name: str) -> dict | None:
        self._ensure_conn()
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM role_profiles WHERE LOWER(role_name) = LOWER(%s)",
                (role_name,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def update_role(self, role_name: str, **fields) -> dict | None:
        allowed = {"description", "focus_areas", "typical_topics"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get_role(role_name)
        self._ensure_conn()
        set_clause = ", ".join(f"{k} = %s" for k in updates)
        values = list(updates.values()) + [role_name]
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"UPDATE role_profiles SET {set_clause}, updated_at = NOW() "
                "WHERE LOWER(role_name) = LOWER(%s) RETURNING *",
                values,
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def delete_role(self, role_name: str) -> bool:
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM role_profiles WHERE LOWER(role_name) = LOWER(%s)",
                (role_name,),
            )
            return cur.rowcount > 0

    # ΓöÇΓöÇ Company profiles ΓÇö list / get / delete ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

    def list_company_profiles(self) -> list[dict]:
        self._ensure_conn()
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM company_profiles ORDER BY company_name, role")
            return [dict(row) for row in cur.fetchall()]

    def get_company_profiles(self, company_name: str) -> list[dict]:
        self._ensure_conn()
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM company_profiles WHERE LOWER(company_name) = LOWER(%s) ORDER BY role",
                (company_name,),
            )
            return [dict(row) for row in cur.fetchall()]

    def delete_company_profile(self, company_name: str, role: str) -> bool:
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM company_profiles "
                "WHERE LOWER(company_name) = LOWER(%s) AND LOWER(role) = LOWER(%s)",
                (company_name, role),
            )
            return cur.rowcount > 0

    # ΓöÇΓöÇ User profiles (resume-based) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

    def create_user_profile(self, resume_raw_text: str, professional_summary: dict) -> str:
        """Store a parsed resume profile. Returns the generated user_id (UUID string)."""
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_profiles (resume_raw_text, professional_summary) "
                "VALUES (%s, %s) RETURNING user_id::text",
                (resume_raw_text, psycopg2.extras.Json(professional_summary)),
            )
            return cur.fetchone()[0]

    def get_user_profile(self, user_id: str) -> dict | None:
        """Fetch a stored user profile by UUID. Returns None if not found or invalid UUID."""
        import uuid as _uuid
        try:
            _uuid.UUID(user_id)
        except (ValueError, AttributeError):
            return None
        self._ensure_conn()
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT user_id::text, resume_raw_text, professional_summary, "
                "created_at, updated_at FROM user_profiles WHERE user_id = %s::uuid",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            result = dict(row)
            # professional_summary is already a dict when fetched from JSONB
            if isinstance(result["professional_summary"], str):
                result["professional_summary"] = json.loads(result["professional_summary"])
            return result
