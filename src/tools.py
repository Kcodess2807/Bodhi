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
def score_answer(
    accuracy: int,
    depth: int,
    communication: int,
    confidence: int,
    feedback: str,
    needs_probing: bool = False,
    probe_reason: str = "",
) -> str:
    """Rate the candidate's last answer on multiple dimensions.

    Args:
        accuracy: 1-5 — is the answer factually correct?
        depth: 1-5 — does the candidate show deep understanding (trade-offs, edge cases)?
        communication: 1-5 — is the explanation clear and well-structured?
        confidence: 1-5 — does the candidate seem certain or is guessing/bluffing?
        feedback: Brief internal note on strengths/weaknesses (not shown to candidate).
        needs_probing: True if the bot should challenge or follow up on this answer.
        probe_reason: Why probing is needed (e.g. "Claimed Redis at scale but gave no specifics").
    """
    a = max(1, min(5, accuracy))
    d = max(1, min(5, depth))
    c = max(1, min(5, communication))
    conf = max(1, min(5, confidence))
    # Weighted composite: accuracy 30%, depth 25%, communication 20%, confidence 15%, reserve 10%
    composite = round(a * 0.30 + d * 0.25 + c * 0.20 + conf * 0.15 + 0.5, 1)  # 0.5 = 10% neutral baseline

    probe_flag = "PROBE" if needs_probing else "NOPROBE"
    return f"SCORE:{composite}:{a},{d},{c},{conf}:{probe_flag}:{probe_reason}:{feedback}"


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
