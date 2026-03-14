"""Phase-level context memory manager for Bodhi interviews.

Maintains per-phase conversational memory in Redis during the interview,
compacts it via LLM summarisation on phase transitions, and flushes
everything to NeonDB at session end.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AnyMessage, HumanMessage

log = logging.getLogger("bodhi.memory")

# ── Compaction prompt ────────────────────────────────────────────────────────

_COMPACT_PROMPT = """\
You are a senior technical interviewer. Analyse the following interview transcript
from the **{phase}** phase and produce a JSON summary.

TRANSCRIPT:
{transcript}

Return ONLY valid JSON with these keys:
{{
  "phase": "{phase}",
  "key_claims": ["list of specific factual claims the candidate made"],
  "strengths": ["specific things the candidate did well"],
  "weaknesses": ["specific gaps, vagueness, or mistakes"],
  "follow_up_hooks": [
    "specific questions to ask in later phases to cross-reference or challenge"
  ],
  "topics_covered": ["list of technical/behavioral topics discussed"],
  "notable_quotes": ["1-2 short verbatim quotes that reveal depth or gaps"]
}}

Be concise but specific. Each list should have 2-5 items.
"""


def _messages_to_transcript(messages: list[AnyMessage]) -> str:
    """Convert LangGraph messages into a readable transcript string."""
    lines: list[str] = []
    for msg in messages:
        role = "Candidate" if isinstance(msg, HumanMessage) else "Interviewer"
        content = msg.content if hasattr(msg, "content") else str(msg)
        if isinstance(content, list):
            content = " ".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        content = content.strip()
        if content and not content.startswith(("TRANSITION:", "SCORE:", "DIFFICULTY:", "END:")):
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def compact_phase(
    phase: str,
    messages: list[AnyMessage],
    llm: Any,
) -> dict:
    """Use the LLM to summarise a phase's conversation into a compact memory blob.

    Args:
        phase: The phase that just ended (e.g. "technical").
        messages: The full messages list from InterviewState.
        llm: A ChatGoogleGenerativeAI instance.

    Returns:
        A dict with keys: phase, key_claims, strengths, weaknesses,
        follow_up_hooks, topics_covered, notable_quotes.
    """
    transcript = _messages_to_transcript(messages)
    if not transcript.strip():
        log.warning("[MEMORY] No transcript content for phase '%s'", phase)
        return _empty_memory(phase)

    prompt = _COMPACT_PROMPT.format(phase=phase, transcript=transcript[-6000:])

    try:
        from src.services.llm import _extract_text

        response = llm.invoke([HumanMessage(content=prompt)])
        raw = _extract_text(response.content).strip()

        # Strip markdown fences
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]

        data = json.loads(raw.strip())
        data["phase"] = phase
        log.info("[MEMORY] Compacted phase '%s': %d claims, %d hooks",
                 phase, len(data.get("key_claims", [])), len(data.get("follow_up_hooks", [])))
        return data

    except Exception as e:
        log.error("[MEMORY] Compaction failed for phase '%s': %s", phase, e)
        return _empty_memory(phase)


def build_cross_section_context(phase_memories: dict) -> str:
    """Build a human-readable cross-section context string from all compacted phase memories.

    Args:
        phase_memories: Dict of {phase: compacted_memory_dict}.

    Returns:
        A formatted string to inject into the system prompt.
    """
    if not phase_memories:
        return ""

    sections: list[str] = []
    all_hooks: list[str] = []

    for phase, mem in phase_memories.items():
        if not isinstance(mem, dict):
            continue
        claims = mem.get("key_claims", [])
        strengths = mem.get("strengths", [])
        weaknesses = mem.get("weaknesses", [])
        hooks = mem.get("follow_up_hooks", [])

        parts = [f"[{phase.upper()}]"]
        if claims:
            parts.append(f"  Claims: {'; '.join(claims[:4])}")
        if strengths:
            parts.append(f"  Strengths: {'; '.join(strengths[:3])}")
        if weaknesses:
            parts.append(f"  Weaknesses: {'; '.join(weaknesses[:3])}")

        sections.append("\n".join(parts))
        all_hooks.extend(hooks)

    context = "\n".join(sections)
    if all_hooks:
        context += "\n\nSUGGESTED FOLLOW-UPS FROM EARLIER PHASES:\n"
        context += "\n".join(f"  - {h}" for h in all_hooks[:6])

    return context


def flush_memories_to_neon(
    session_id: str,
    phase_memories: dict,
    storage: Any,
) -> None:
    """Persist all compacted phase memories to NeonDB."""
    for phase, mem in phase_memories.items():
        if not isinstance(mem, dict):
            continue
        try:
            storage.save_phase_memory(session_id, phase, mem)
            log.info("[MEMORY] Flushed phase '%s' memory to Neon for session %s",
                     phase, session_id)
        except Exception as e:
            log.error("[MEMORY] Failed to flush phase '%s' to Neon: %s", phase, e)


def _empty_memory(phase: str) -> dict:
    return {
        "phase": phase,
        "key_claims": [],
        "strengths": [],
        "weaknesses": [],
        "follow_up_hooks": [],
        "topics_covered": [],
        "notable_quotes": [],
    }
