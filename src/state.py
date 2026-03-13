"""Interview session state schema for LangGraph."""

from typing import Annotated
from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

PHASES = ("intro", "behavioral", "technical", "coding", "wrapup")


class InterviewState(TypedDict):
    """LangGraph state for a single interview session.

    Tier-1 (edge) state — lives entirely in MemorySaver during the
    session. Flushed to Redis/NeonDB on phase transitions and session end.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    session_id: str
    candidate_name: str
    target_company: str
    target_role: str
    current_phase: str            # one of PHASES
    difficulty_level: int         # 1-5
    phase_scores: dict            # {"behavioral": {"score": 4, "questions": 3}, ...}
    entity_context: str           # company info loaded from Redis/Neon at session start
    suggested_topics: str         # soft guidance from uploaded documents (cached in Redis)
    should_end: bool
