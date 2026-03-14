"""LangGraph tool definitions for interview flow control."""

from langchain_core.tools import tool

from src.state import PHASES


@tool
def transition_phase(next_phase: str) -> str:
    """Move the interview to a new phase.

    Args:
        next_phase: Target phase — one of 'technical', 'behavioral', 'dsa', 'project', 'wrapup'.
    """
    if next_phase not in PHASES:
        return f"Invalid phase '{next_phase}'. Choose from: {', '.join(PHASES)}"
    return f"TRANSITION:{next_phase}"


@tool
def score_answer(score: int, feedback: str) -> str:
    """Rate the candidate's last answer.

    Args:
        score: Rating from 1 (poor) to 5 (excellent).
        feedback: Brief internal note on strengths/weaknesses (not shown to candidate).
    """
    clamped = max(1, min(5, score))
    return f"SCORE:{clamped}:{feedback}"


@tool
def adjust_difficulty(direction: str) -> str:
    """Raise or lower the question difficulty.

    Args:
        direction: 'up' to increase difficulty, 'down' to decrease.
    """
    if direction not in ("up", "down"):
        return "Invalid direction. Use 'up' or 'down'."
    return f"DIFFICULTY:{direction}"


@tool
def end_interview(summary: str) -> str:
    """Conclude the interview session.

    Args:
        summary: Final performance summary for the candidate.
    """
    return f"END:{summary}"


ALL_TOOLS = [transition_phase, score_answer, adjust_difficulty, end_interview]
