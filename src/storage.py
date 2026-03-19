"""NeonDB PostgreSQL persistence layer (Tier 3) — permanent interview records."""

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
    user_profile_id UUID,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    overall_score   REAL,
    summary         TEXT,
    report_data     JSONB
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
    custom_metrics  JSONB DEFAULT '[]',
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

CREATE TABLE IF NOT EXISTS proctoring_violations (
    id              SERIAL PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id),
    violation_type  TEXT NOT NULL,
    severity        TEXT NOT NULL,
    message         TEXT,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sentiment_data (
    id                  SERIAL PRIMARY KEY,
    session_id          TEXT NOT NULL REFERENCES sessions(id),
    emotion             TEXT,
    sentiment           TEXT,
    confidence_score    INT,
    speaking_rate_wpm   INT,
    filler_rate         REAL,
    posture             TEXT,
    gaze_direction      TEXT,
    spine_score         INT,
    flags               TEXT[],
    timestamp           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transcripts_session ON transcripts(session_id);
CREATE INDEX IF NOT EXISTS idx_phase_results_session ON phase_results(session_id);
CREATE INDEX IF NOT EXISTS idx_entities_company ON entities(company_name);
CREATE INDEX IF NOT EXISTS idx_company_docs_lookup ON company_documents(company_name, role);
CREATE INDEX IF NOT EXISTS idx_role_profiles_name ON role_profiles(role_name);
CREATE INDEX IF NOT EXISTS idx_phase_memories_session ON phase_memories(session_id);
CREATE INDEX IF NOT EXISTS idx_answer_scores_session ON answer_scores(session_id);
CREATE INDEX IF NOT EXISTS idx_proctoring_violations_session ON proctoring_violations(session_id);
CREATE INDEX IF NOT EXISTS idx_sentiment_data_session ON sentiment_data(session_id);
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
            # Safe migrations for existing databases
            for stmt in [
                "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS clerk_user_id TEXT;",
                "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS report_data JSONB;",
                "ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS custom_metrics JSONB DEFAULT '[]';",
            ]:
                try:
                    cur.execute(stmt)
                except Exception:
                    pass

            # user_profiles table (separate execute for clear error visibility)
            try:
                cur.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS user_profile_id UUID;")
            except Exception:
                pass

            try:
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_sessions_user_profile ON sessions(user_profile_id);"
                )
            except Exception:
                pass

            # Execute the user_profiles table separately so any failure is visible.
            # (psycopg2 multi-statement execute only surfaces the last statement's error.)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    clerk_user_id   TEXT,
                    resume_raw_text TEXT NOT NULL,
                    professional_summary JSONB NOT NULL,
                    created_at      TIMESTAMPTZ DEFAULT NOW(),
                    updated_at      TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            try:
                cur.execute("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS clerk_user_id TEXT;")
                cur.execute("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS resume_file_content BYTEA;")
                cur.execute("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS resume_file_name TEXT;")
            except Exception:
                pass

            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_profiles_clerk_user_id "
                "ON user_profiles(clerk_user_id) WHERE clerk_user_id IS NOT NULL;"
            )

            # Add FK for sessions.user_profile_id -> user_profiles.user_id
            try:
                cur.execute(
                    "ALTER TABLE sessions "
                    "ADD CONSTRAINT sessions_user_profile_id_fkey "
                    "FOREIGN KEY (user_profile_id) REFERENCES user_profiles(user_id);"
                )
            except Exception:
                pass

    def migrate_embedding_dimension(self) -> None:
        """One-time migration: drop and recreate company_documents for new vector(3072) dim.
        WARNING: This drops all existing embedded document data."""
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

    # ── Sessions ──────────────────────────────────────────────────────────────

    def create_session(
        self,
        session_id: str,
        candidate_name: str,
        target_company: str,
        target_role: str,
        clerk_user_id: str | None = None,
        user_profile_id: str | None = None,
    ) -> None:
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (id, candidate_name, target_company, target_role, clerk_user_id, user_profile_id) "
                "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (session_id, candidate_name, target_company, target_role, clerk_user_id, user_profile_id),
            )

    def end_session(
        self,
        session_id: str,
        overall_score: float | None = None,
        summary: str = "",
        report_data: dict | None = None,
    ) -> None:
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE sessions SET ended_at = %s, overall_score = %s, summary = %s, report_data = %s "
                "WHERE id = %s",
                (
                    datetime.now(timezone.utc),
                    overall_score,
                    summary,
                    json.dumps(report_data) if report_data else None,
                    session_id,
                ),
            )

    def get_session_info(self, session_id: str) -> dict | None:
        """Retrieve basic session information."""
        self._ensure_conn()
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
            row = cur.fetchone()
        return dict(row) if row else None

    def get_session_report_data(self, session_id: str) -> dict | None:
        """Retrieve the stored report data for a session."""
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute("SELECT report_data FROM sessions WHERE id = %s", (session_id,))
            row = cur.fetchone()
        return row[0] if row and row[0] else None

    # ── Transcripts ───────────────────────────────────────────────────────────

    def get_user_interview_history(self, clerk_user_id: str) -> list[dict]:
        """Fetch past interview sessions for a given Clerk user ID."""
        if not clerk_user_id:
            return []
        self._ensure_conn()
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id as session_id, target_company, target_role, overall_score, started_at, ended_at "
                "FROM sessions "
                "WHERE clerk_user_id = %s "
                "ORDER BY started_at DESC",
                (clerk_user_id,),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    # ── Phase results ─────────────────────────────────────────────────────────

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
                "INSERT INTO transcripts (session_id, role, content, phase) VALUES %s",
                rows,
            )

    # ── Phase results ─────────────────────────────────────────────────────────

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

    # ── Phase memories (compacted context) ───────────────────────────────────

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

    # ── Answer scores (granular per-question scores) ──────────────────────────

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

    def get_answer_scores(self, session_id: str) -> list[dict]:
        """Retrieve all answer scores for a session."""
        self._ensure_conn()
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM answer_scores WHERE session_id = %s ORDER BY phase, question_num",
                (session_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    # ── Proctoring violations ─────────────────────────────────────────────────

    def save_proctoring_violation(
        self,
        session_id: str,
        violation_type: str,
        severity: str,
        message: str,
    ) -> None:
        """Store a proctoring violation."""
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO proctoring_violations (session_id, violation_type, severity, message) "
                "VALUES (%s, %s, %s, %s)",
                (session_id, violation_type, severity, message),
            )

    def get_proctoring_violations(self, session_id: str) -> list[dict]:
        """Retrieve all proctoring violations for a session."""
        self._ensure_conn()
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM proctoring_violations WHERE session_id = %s ORDER BY timestamp",
                (session_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    # ── Sentiment data ────────────────────────────────────────────────────────

    def save_sentiment_data(
        self,
        session_id: str,
        emotion: str | None = None,
        sentiment: str | None = None,
        confidence_score: int | None = None,
        speaking_rate_wpm: int | None = None,
        filler_rate: float | None = None,
        posture: str | None = None,
        gaze_direction: str | None = None,
        spine_score: int | None = None,
        flags: list[str] | None = None,
    ) -> None:
        """Store sentiment and behavioral analysis data."""
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sentiment_data
                (session_id, emotion, sentiment, confidence_score, speaking_rate_wpm, filler_rate,
                 posture, gaze_direction, spine_score, flags)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (session_id, emotion, sentiment, confidence_score, speaking_rate_wpm, filler_rate,
                 posture, gaze_direction, spine_score, flags),
            )

    def get_sentiment_data(self, session_id: str) -> list[dict]:
        """Retrieve all sentiment data for a session."""
        self._ensure_conn()
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM sentiment_data WHERE session_id = %s ORDER BY timestamp",
                (session_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    # ── Entities ──────────────────────────────────────────────────────────────

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

    # ── Company profiles (company+role granularity) ───────────────────────────

    def upsert_company_profile(
        self,
        company_name: str,
        role: str,
        description: str = "",
        hiring_patterns: str = "",
        tech_stack: str = "",
        custom_metrics: list | None = None,
        contributed_by: str = "",
    ) -> None:
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO company_profiles "
                "(company_name, role, description, hiring_patterns, tech_stack, custom_metrics, contributed_by, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (company_name, role) DO UPDATE SET "
                "description = EXCLUDED.description, "
                "hiring_patterns = EXCLUDED.hiring_patterns, "
                "tech_stack = EXCLUDED.tech_stack, "
                "custom_metrics = EXCLUDED.custom_metrics, "
                "contributed_by = EXCLUDED.contributed_by, "
                "updated_at = EXCLUDED.updated_at",
                (
                    company_name, role, description, hiring_patterns,
                    tech_stack, json.dumps(custom_metrics or []), contributed_by, datetime.now(timezone.utc),
                ),
            )

    # ── Company documents (RAG vector store) ──────────────────────────────────

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
        """Cosine-similarity search, merging role-only general docs + company-specific docs."""
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

    # ── Role profiles ─────────────────────────────────────────────────────────

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

    # ── Company profiles — list / get / delete ────────────────────────────────

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

    # ── User profiles (resume-based) ──────────────────────────────────────────

    def create_user_profile(
        self,
        resume_raw_text: str,
        professional_summary: dict,
        clerk_user_id: str | None = None,
        file_bytes: bytes | None = None,
        filename: str | None = None,
    ) -> str:
        """Store a parsed resume profile. Returns the generated user_id (UUID string)."""
        self._ensure_conn()
        with self.conn.cursor() as cur:
            if clerk_user_id:
                cur.execute(
                    "SELECT user_id::text FROM user_profiles WHERE clerk_user_id = %s",
                    (clerk_user_id,),
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        "UPDATE user_profiles SET resume_raw_text = %s, "
                        "professional_summary = %s, updated_at = NOW(), "
                        "resume_file_content = COALESCE(%s, resume_file_content), "
                        "resume_file_name = COALESCE(%s, resume_file_name) "
                        "WHERE clerk_user_id = %s",
                        (
                            resume_raw_text,
                            psycopg2.extras.Json(professional_summary),
                            file_bytes,
                            filename,
                            clerk_user_id,
                        ),
                    )
                    return row[0]

                cur.execute(
                    "INSERT INTO user_profiles (clerk_user_id, resume_raw_text, professional_summary, resume_file_content, resume_file_name) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING user_id::text",
                    (
                        clerk_user_id,
                        resume_raw_text,
                        psycopg2.extras.Json(professional_summary),
                        file_bytes,
                        filename,
                    ),
                )
            else:
                cur.execute(
                    "INSERT INTO user_profiles (resume_raw_text, professional_summary, resume_file_content, resume_file_name) "
                    "VALUES (%s, %s, %s, %s) RETURNING user_id::text",
                    (
                        resume_raw_text, 
                        psycopg2.extras.Json(professional_summary),
                        file_bytes,
                        filename,
                    ),
                )
            return cur.fetchone()[0]

    def get_user_profile_id_by_clerk_user_id(self, clerk_user_id: str) -> str | None:
        """Fetch a user_id by Clerk user_id. Returns None if not found."""
        if not clerk_user_id:
            return None
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT user_id::text FROM user_profiles WHERE clerk_user_id = %s",
                (clerk_user_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def ensure_user_profile_for_clerk(self, clerk_user_id: str) -> str:
        """Ensure a user_profile row exists for the Clerk user. Returns user_id."""
        if not clerk_user_id:
            raise ValueError("clerk_user_id is required")
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT user_id::text FROM user_profiles WHERE clerk_user_id = %s",
                (clerk_user_id,),
            )
            row = cur.fetchone()
            if row:
                return row[0]

            cur.execute(
                "INSERT INTO user_profiles (clerk_user_id, resume_raw_text, professional_summary) "
                "VALUES (%s, %s, %s) RETURNING user_id::text",
                (clerk_user_id, "", psycopg2.extras.Json({})),
            )
            return cur.fetchone()[0]

    def get_user_profile_status_by_clerk_user_id(self, clerk_user_id: str) -> tuple[str, bool] | None:
        """Return (user_id, has_resume) for the Clerk user, or None if missing."""
        if not clerk_user_id:
            return None
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT user_id::text, "
                "(resume_raw_text IS NOT NULL AND resume_raw_text <> '') AS has_resume "
                "FROM user_profiles WHERE clerk_user_id = %s",
                (clerk_user_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return row[0], bool(row[1])

    def get_user_resume_file(self, clerk_user_id: str) -> tuple[bytes | None, str | None]:
        """Fetch the binary resume file content and filename for a user."""
        if not clerk_user_id:
            return None, None
        self._ensure_conn()
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT resume_file_content, resume_file_name FROM user_profiles WHERE clerk_user_id = %s",
                (clerk_user_id,),
            )
            row = cur.fetchone()
            if not row:
                return None, None
            # Convert memoryview from pg to bytes if present
            content = bytes(row[0]) if row[0] else None
            return content, row[1]


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
                "SELECT user_id::text, clerk_user_id, resume_raw_text, professional_summary, "
                "resume_file_name, created_at, updated_at FROM user_profiles WHERE user_id = %s::uuid",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            result = dict(row)
            if isinstance(result["professional_summary"], str):
                result["professional_summary"] = json.loads(result["professional_summary"])
            return result
