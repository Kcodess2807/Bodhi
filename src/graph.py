"""LangGraph interview orchestration graph."""

import logging
from datetime import datetime, timezone

from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.memory import build_cross_section_context, compact_phase
from src.prompts import build_jd_targeted_prompt, build_resume_based_prompt, build_system_prompt
from src.state import PHASE_CONFIG, InterviewState
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

    Handles the new multi-dimensional SCORE format:
      SCORE:{composite}:{a},{d},{c},{conf}:{PROBE|NOPROBE}:{probe_reason}:{feedback}

    On TRANSITION: pops the first question from the new phase queue.
    On SCORE: pops the next question from the current phase queue; tracks probing.
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
        updates["phase_question_count"] = 0
        updates["phase_start_time"] = datetime.now(timezone.utc).isoformat()
        updates["pending_probe"] = ""
        log.info(f"[GRAPH] Phase transition → {new_phase}, target_question: {next_q[:80] if next_q else '(ad-hoc)'}")

    elif content.startswith("SCORE:"):
        # Parse: SCORE:{composite}:{a},{d},{c},{conf}:{PROBE|NOPROBE}:{probe_reason}:{feedback}
        parts = content.split(":", 5)
        try:
            composite = float(parts[1])
            metrics_str = parts[2] if len(parts) > 2 else "3,3,3,3"
            metrics = [int(x) for x in metrics_str.split(",")]
            accuracy = metrics[0] if len(metrics) > 0 else 3
            depth_score = metrics[1] if len(metrics) > 1 else 3
            comm = metrics[2] if len(metrics) > 2 else 3
            conf = metrics[3] if len(metrics) > 3 else 3
        except (ValueError, IndexError):
            composite = 3.0
            accuracy = depth_score = comm = conf = 3

        probe_flag = parts[3] if len(parts) > 3 else "NOPROBE"
        probe_reason = parts[4] if len(parts) > 4 else ""
        feedback = parts[5] if len(parts) > 5 else ""

        phase = state["current_phase"]
        scores = dict(state.get("phase_scores", {}))
        prev = scores.get(phase, {"total_score": 0, "questions": 0, "feedback": []})
        prev = dict(prev)
        prev["total_score"] = prev.get("total_score", 0) + composite
        prev["questions"] = prev.get("questions", 0) + 1
        prev["feedback"] = list(prev.get("feedback", [])) + [feedback]
        scores[phase] = prev
        updates["phase_scores"] = scores

        # Track per-question score details
        answer_scores = list(state.get("answer_scores", []))
        q_count = state.get("phase_question_count", 0) + 1
        answer_scores.append({
            "phase": phase,
            "question_num": q_count,
            "accuracy": accuracy,
            "depth": depth_score,
            "communication": comm,
            "confidence": conf,
            "composite": composite,
            "feedback": feedback,
            "probed": probe_flag == "PROBE",
            "probe_reason": probe_reason,
        })
        updates["answer_scores"] = answer_scores
        updates["phase_question_count"] = q_count

        # Handle probing
        if probe_flag == "PROBE" and probe_reason:
            updates["pending_probe"] = probe_reason
            log.info(f"[GRAPH] Probe requested: {probe_reason}")
        else:
            updates["pending_probe"] = ""

        # Pop next question from current phase queue (only if not probing)
        if probe_flag != "PROBE":
            next_q = _pop_next_question(state, phase)
            updates["target_question"] = next_q
            updates["queued_questions"] = state.get("queued_questions", {})

        log.info(f"[GRAPH] Score: {composite} (A:{accuracy} D:{depth_score} C:{comm} Cf:{conf}) "
                 f"for {phase} Q{q_count}")

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


def _compact_memory_node(state: InterviewState) -> dict:
    """Graph node: fires on phase transitions to compact the old phase's memory.

    Uses the LLM to summarise the conversation from the phase that just ended,
    stores it in phase_memories for cross-section context in later phases.
    """
    # The phase has ALREADY been updated by _process_tool_results,
    # so we need to figure out which phase just ended.
    # We look at phase_memories to see what's already compacted.
    phase_memories = dict(state.get("phase_memories", {}))
    current_phase = state.get("current_phase", "intro")
    messages = state.get("messages", [])

    from src.state import PHASES
    current_idx = PHASES.index(current_phase) if current_phase in PHASES else 0
    if current_idx == 0:
        return {}

    old_phase = PHASES[current_idx - 1]

    # Skip if already compacted
    if old_phase in phase_memories:
        return {}

    # Use a lightweight LLM for compaction
    try:
        from src.services.llm import create_llm
        import os
        compact_llm = create_llm(api_key=os.getenv("GOOGLE_API_KEY", ""))
        memory = compact_phase(old_phase, messages, compact_llm)
        phase_memories[old_phase] = memory
        log.info(f"[GRAPH] Compacted memory for phase '{old_phase}' "
                 f"({len(memory.get('key_claims', []))} claims, "
                 f"{len(memory.get('follow_up_hooks', []))} hooks)")
        return {"phase_memories": phase_memories}
    except Exception as e:
        log.error(f"[GRAPH] Memory compaction failed for '{old_phase}': {e}")
        return {}


def build_interview_graph(llm):
    """Construct and compile the interview StateGraph.

    Args:
        llm: A ChatGoogleGenerativeAI instance (from create_llm).

    Returns:
        Compiled LangGraph graph with MemorySaver checkpointer.
    """
    model_with_tools = llm.bind_tools(ALL_TOOLS)

    def interviewer_node(state: InterviewState) -> dict:
        mode = state.get("interview_mode", "standard")
        phase = state["current_phase"]
        difficulty = state["difficulty_level"]

        # Build cross-section context from compacted phase memories
        cross_context = build_cross_section_context(state.get("phase_memories", {}))
        pending_probe = state.get("pending_probe", "")

        # Phase timing info for prompt
        config = PHASE_CONFIG.get(phase, {})
        q_count = state.get("phase_question_count", 0)
        target_q = config.get("target_questions", 5)
        max_q = config.get("max_questions", 7)

        if mode == "option_a":
            system = build_resume_based_prompt(
                candidate_profile=state.get("candidate_profile") or {},
                current_phase=phase,
                difficulty_level=difficulty,
                cross_section_context=cross_context,
                pending_probe=pending_probe,
                questions_asked=q_count,
                target_questions=target_q,
                max_questions=max_q,
            )
        elif mode == "option_b":
            system = build_jd_targeted_prompt(
                candidate_profile=state.get("candidate_profile") or {},
                jd_context=state.get("jd_context") or "",
                gap_map=state.get("gap_map") or {},
                current_phase=phase,
                difficulty_level=difficulty,
                cross_section_context=cross_context,
                pending_probe=pending_probe,
                questions_asked=q_count,
                target_questions=target_q,
                max_questions=max_q,
            )
        else:
            system = build_system_prompt(
                candidate_name=state["candidate_name"],
                target_company=state["target_company"],
                target_role=state["target_role"],
                current_phase=phase,
                difficulty_level=difficulty,
                entity_context=state.get("entity_context", ""),
                suggested_topics=state.get("suggested_topics", ""),
                target_question=state.get("target_question", ""),
                cross_section_context=cross_context,
                pending_probe=pending_probe,
                questions_asked=q_count,
                target_questions=target_q,
                max_questions=max_q,
            )
        all_messages = [SystemMessage(content=system)] + list(state["messages"])
        response = model_with_tools.invoke(all_messages)
        return {"messages": [response]}

    tool_node = ToolNode(ALL_TOOLS)

    def should_compact(state: InterviewState) -> str:
        """After process_tools, check if a phase transition just happened."""
        last_msg = state["messages"][-1] if state["messages"] else None
        if last_msg:
            content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
            if content.startswith("TRANSITION:"):
                return "compact"
        return "continue"

    builder = StateGraph(InterviewState)
    builder.add_node("interviewer", interviewer_node)
    builder.add_node("tools", tool_node)
    builder.add_node("process_tools", _process_tool_results)
    builder.add_node("compact_memory", _compact_memory_node)

    builder.set_entry_point("interviewer")
    builder.add_conditional_edges("interviewer", tools_condition)
    builder.add_edge("tools", "process_tools")
    builder.add_conditional_edges(
        "process_tools",
        should_compact,
        {"compact": "compact_memory", "continue": "interviewer"},
    )
    builder.add_edge("compact_memory", "interviewer")

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)
