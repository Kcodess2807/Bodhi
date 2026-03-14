"""Interview session state schema for LangGraph."""

from typing import Annotated
from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

PHASES = ("intro", "technical", "behavioral", "dsa", "project", "wrapup")

# ── Phase timing and question budget configuration ─────────────────────────
PHASE_CONFIG: dict[str, dict] = {
    "intro":      {"target_questions": 3,  "max_questions": 4,  "target_minutes": 3},
    "technical":  {"target_questions": 5,  "max_questions": 7,  "target_minutes": 12},
    "behavioral": {"target_questions": 4,  "max_questions": 5,  "target_minutes": 8},
    "dsa":        {"target_questions": 3,  "max_questions": 4,  "target_minutes": 10},
    "project":    {"target_questions": 3,  "max_questions": 4,  "target_minutes": 8},
    "wrapup":     {"target_questions": 2,  "max_questions": 3,  "target_minutes": 4},
}
# Total target: ~45 minutes across all phases


class InterviewState(TypedDict, total=False):
    """LangGraph state for a single interview session.

    Tier-1 (edge) state — lives entirely in MemorySaver during the
    session. Flushed to Redis/NeonDB on phase transitions and session end.

    interview_mode values:
      "standard"  — classic company+role-based interview (default)
      "option_a"  — resume-based personal interview
      "option_b"  — company/role-targeted with JD gap analysis
    """

    messages: Annotated[list[AnyMessage], add_messages]
    session_id: str
    candidate_name: str
    target_company: str
    target_role: str
    current_phase: str            # one of PHASES
    difficulty_level: int         # 1-5
    phase_scores: dict            # {"technical": {"score": 4, "questions": 3}, ...}
    entity_context: str           # company info loaded from Redis/Neon at session start
    suggested_topics: str         # soft guidance from uploaded documents (cached in Redis)
    should_end: bool

    # ── Pre-generated curriculum queue ────────────────────────────
    queued_questions: dict        # {"technical": ["Q1", "Q2"], "dsa": ["Q1", "Q2"]}
    target_question: str          # The specific question Bodhi should ask next, or ""
    # ── Resume-based modes ─────────────────────────────────────────
    interview_mode: str           # "standard" | "option_a" | "option_b"
    candidate_profile: dict       # parsed resume profile (option_a / option_b)
    jd_context: str               # job description text (option_b)
    gap_map: dict                 # {strong_match, partial_match, gaps} (option_b, internal)

    # ── Phase memory & timing (NEW) ────────────────────────────────
    phase_memories: dict          # {phase: compacted_memory_dict} from completed phases
    phase_question_count: int     # questions asked in current phase so far
    phase_start_time: str         # ISO timestamp when current phase started
    pending_probe: str            # if set, bot MUST ask this follow-up before next question
    answer_scores: list           # [{phase, question_num, accuracy, depth, communication, confidence, feedback}, ...]
