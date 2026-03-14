"""LangGraph interview orchestration graph."""

import logging

from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.prompts import build_system_prompt
from src.state import InterviewState
from src.tools import ALL_TOOLS

log = logging.getLogger("bodhi.graph")


def _pop_next_question(state: dict, phase: str) -> str:
    """Pop the next question from the queued_questions for a given phase.
    Returns the question string, or '' if the queue is empty or missing."""
    queued = state.get("queued_questions", {})
    if not isinstance(queued, dict):
        return ""
    phase_q = queued.get(phase, [])
    if not phase_q:
        return ""
    # Pop the first question
    next_q = phase_q[0]
    # Update the queue (remove the popped question)
    new_queued = dict(queued)
    new_queued[phase] = phase_q[1:]
    state["queued_questions"] = new_queued
    log.info(f"[QUEUE] Popped question for {phase}: {next_q}")
    log.info(f"[QUEUE] Remaining {phase} questions: {len(phase_q) - 1}")
    return next_q


def _process_tool_results(state: InterviewState) -> dict:
    """Graph node: interpret tool outputs and update state accordingly.
    
    On TRANSITION: pops the first question from the new phase queue.
    On SCORE: pops the next question from the current phase queue.
    """
    updates: dict = {}
    last_msg = state["messages"][-1] if state["messages"] else None

    if last_msg is None:
        return updates

    content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    if content.startswith("TRANSITION:"):
        new_phase = content.split(":", 1)[1]
        updates["current_phase"] = new_phase
        # Pop first question for the new phase
        next_q = _pop_next_question(state, new_phase)
        updates["target_question"] = next_q
        updates["queued_questions"] = state.get("queued_questions", {})
        log.info(f"[GRAPH] Phase transition → {new_phase}, target_question: {next_q[:80] if next_q else '(ad-hoc)'}")

    elif content.startswith("SCORE:"):
        parts = content.split(":", 2)
        score = int(parts[1])
        feedback = parts[2] if len(parts) > 2 else ""
        phase = state["current_phase"]
        scores = dict(state.get("phase_scores", {}))
        prev = scores.get(phase, {"total_score": 0, "questions": 0, "feedback": []})
        prev = dict(prev)
        prev["total_score"] = prev.get("total_score", 0) + score
        prev["questions"] = prev.get("questions", 0) + 1
        prev["feedback"] = list(prev.get("feedback", [])) + [feedback]
        scores[phase] = prev
        updates["phase_scores"] = scores
        # Pop next question from current phase queue
        next_q = _pop_next_question(state, phase)
        updates["target_question"] = next_q
        updates["queued_questions"] = state.get("queued_questions", {})
        log.info(f"[GRAPH] Score recorded ({score}/5) for {phase}, next target: {next_q[:80] if next_q else '(ad-hoc / queue empty)'}")

    elif content.startswith("DIFFICULTY:"):
        direction = content.split(":", 1)[1]
        level = state.get("difficulty_level", 3)
        if direction == "up":
            updates["difficulty_level"] = min(5, level + 1)
        elif direction == "down":
            updates["difficulty_level"] = max(1, level - 1)

    elif content.startswith("END:"):
        updates["should_end"] = True

    return updates


def build_interview_graph(llm):
    """Construct and compile the interview StateGraph.

    Args:
        llm: A ChatGoogleGenerativeAI instance (from create_llm).

    Returns:
        Compiled LangGraph graph with MemorySaver checkpointer.
    """
    model_with_tools = llm.bind_tools(ALL_TOOLS)

    def interviewer_node(state: InterviewState) -> dict:
        system = build_system_prompt(
            candidate_name=state["candidate_name"],
            target_company=state["target_company"],
            target_role=state["target_role"],
            current_phase=state["current_phase"],
            difficulty_level=state["difficulty_level"],
            entity_context=state.get("entity_context", ""),
            suggested_topics=state.get("suggested_topics", ""),
            target_question=state.get("target_question", ""),
        )
        all_messages = [SystemMessage(content=system)] + list(state["messages"])
        response = model_with_tools.invoke(all_messages)
        return {"messages": [response]}

    tool_node = ToolNode(ALL_TOOLS)

    builder = StateGraph(InterviewState)
    builder.add_node("interviewer", interviewer_node)
    builder.add_node("tools", tool_node)
    builder.add_node("process_tools", _process_tool_results)

    builder.set_entry_point("interviewer")
    builder.add_conditional_edges("interviewer", tools_condition)
    builder.add_edge("tools", "process_tools")
    builder.add_edge("process_tools", "interviewer")

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)
