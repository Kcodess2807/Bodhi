"""Structured interview report generation for Bodhi.

Builds a comprehensive performance report from compacted phase memories
and granular answer scores at the end of a session.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("bodhi.report")

# Score → letter grade mapping
_GRADE_MAP = [
    (90, "A+"), (85, "A"), (80, "A-"),
    (75, "B+"), (70, "B"), (65, "B-"),
    (60, "C+"), (55, "C"), (50, "C-"),
    (45, "D+"), (40, "D"),
    (0,  "F"),
]


def _to_grade(pct: float) -> str:
    for threshold, grade in _GRADE_MAP:
        if pct >= threshold:
            return grade
    return "F"


def _to_pct(raw: float, max_val: float = 5.0) -> float:
    """Convert a 1-5 raw score to a 0-100 percentage."""
    return round(min(100.0, max(0.0, (raw / max_val) * 100)), 1)


def generate_report(
    phase_memories: dict,
    answer_scores: list[dict],
    phase_scores: dict,
    proctoring_violations: list[dict] | None = None,
    sentiment_data: list[dict] | None = None,
    session_info: dict | None = None,
) -> dict:
    """Build a structured performance report from session data.

    Args:
        phase_memories: {phase: compacted_memory_dict} from compact_phase().
        answer_scores: List of per-question score dicts from InterviewState.
        phase_scores: {phase: {total_score, questions, feedback}} from InterviewState.
        proctoring_violations: List of proctoring violation dicts from database.
        sentiment_data: List of sentiment analysis dicts from database.
        session_info: Basic session information (candidate name, company, role, etc.).

    Returns:
        A structured report dict with overall grade, phase breakdown,
        cross-section insights, proctoring summary, behavioral analysis, and improvement areas.
    """
    phase_breakdown: dict[str, dict] = {}
    all_strengths: list[str] = []
    all_weaknesses: list[str] = []
    all_hooks: list[str] = []
    total_composite = 0.0
    total_questions = 0

    # ── Per-phase breakdown ───────────────────────────────────────
    scored_phases = [p for p in ("technical", "behavioral", "dsa", "project") if p in phase_scores]

    for phase in scored_phases:
        ps = phase_scores.get(phase, {})
        q_count = ps.get("questions", 0)
        total_score = ps.get("total_score", 0)
        avg_composite = total_score / q_count if q_count else 0
        pct = _to_pct(avg_composite)

        # Collect per-question metrics for this phase
        phase_answers = [a for a in answer_scores if a.get("phase") == phase]
        metrics = _avg_metrics(phase_answers)

        # Collect memory insights
        mem = phase_memories.get(phase, {})
        strengths = mem.get("strengths", [])
        weaknesses = mem.get("weaknesses", [])
        hooks = mem.get("follow_up_hooks", [])

        all_strengths.extend(strengths)
        all_weaknesses.extend(weaknesses)
        all_hooks.extend(hooks)
        total_composite += total_score
        total_questions += q_count

        phase_breakdown[phase] = {
            "score_pct": pct,
            "grade": _to_grade(pct),
            "questions_asked": q_count,
            "avg_composite": round(avg_composite, 2),
            "metrics": metrics,
            "strengths": strengths[:3],
            "improvements": weaknesses[:3],
            "feedback": ps.get("feedback", [])[:5],
        }

    # ── Overall score ─────────────────────────────────────────────
    overall_avg = total_composite / total_questions if total_questions else 0
    overall_pct = _to_pct(overall_avg)
    overall_grade = _to_grade(overall_pct)

    # ── Cross-section insights ────────────────────────────────────
    cross_insights = _build_cross_insights(phase_memories, answer_scores)

    # ── Proctoring summary ────────────────────────────────────────
    proctoring_summary = _build_proctoring_summary(proctoring_violations or [])

    # ── Behavioral analysis ───────────────────────────────────────
    behavioral_summary = _build_behavioral_summary(sentiment_data or [])

    # ── Hiring recommendation ─────────────────────────────────────
    recommendation = _hiring_recommendation(overall_pct, phase_breakdown, proctoring_summary)

    report = {
        "overall_grade": overall_grade,
        "overall_score_pct": overall_pct,
        "total_questions": total_questions,
        "phase_breakdown": phase_breakdown,
        "top_strengths": list(dict.fromkeys(all_strengths))[:5],
        "top_improvements": list(dict.fromkeys(all_weaknesses))[:5],
        "cross_section_insights": cross_insights,
        "proctoring_summary": proctoring_summary,
        "behavioral_summary": behavioral_summary,
        "hiring_recommendation": recommendation,
        "session_info": session_info or {},
    }

    log.info("[REPORT] Generated report: %s (%s%%), %d questions across %d phases",
             overall_grade, overall_pct, total_questions, len(scored_phases))
    return report


def _avg_metrics(answers: list[dict]) -> dict:
    """Average the dimensional metrics across a list of answer scores."""
    if not answers:
        return {"accuracy": 0, "depth": 0, "communication": 0, "confidence": 0}

    n = len(answers)
    return {
        "accuracy": round(sum(a.get("accuracy", 3) for a in answers) / n, 1),
        "depth": round(sum(a.get("depth", 3) for a in answers) / n, 1),
        "communication": round(sum(a.get("communication", 3) for a in answers) / n, 1),
        "confidence": round(sum(a.get("confidence", 3) for a in answers) / n, 1),
    }


def _build_cross_insights(phase_memories: dict, answer_scores: list[dict]) -> list[str]:
    """Identify cross-section patterns and contradictions."""
    insights: list[str] = []

    # Find phases where probing was frequently needed
    for phase in ("technical", "behavioral", "dsa", "project"):
        phase_answers = [a for a in answer_scores if a.get("phase") == phase]
        probed = [a for a in phase_answers if a.get("probed")]
        if len(probed) >= 2:
            reasons = [a.get("probe_reason", "") for a in probed if a.get("probe_reason")]
            if reasons:
                insights.append(
                    f"In {phase}, multiple answers needed probing: {'; '.join(reasons[:2])}"
                )

    # Find metric inconsistencies (high accuracy but low depth = surface-level knowledge)
    for phase in ("technical", "dsa"):
        phase_answers = [a for a in answer_scores if a.get("phase") == phase]
        if len(phase_answers) >= 2:
            avg_acc = sum(a.get("accuracy", 3) for a in phase_answers) / len(phase_answers)
            avg_depth = sum(a.get("depth", 3) for a in phase_answers) / len(phase_answers)
            if avg_acc >= 4 and avg_depth <= 2.5:
                insights.append(
                    f"In {phase}: high accuracy ({avg_acc:.1f}) but low depth ({avg_depth:.1f}) "
                    f"suggests surface-level knowledge without deep understanding"
                )

    # Find confidence gaps
    low_conf_phases = []
    for phase in ("technical", "behavioral", "dsa", "project"):
        phase_answers = [a for a in answer_scores if a.get("phase") == phase]
        if phase_answers:
            avg_conf = sum(a.get("confidence", 3) for a in phase_answers) / len(phase_answers)
            if avg_conf <= 2.5:
                low_conf_phases.append(phase)
    if low_conf_phases:
        insights.append(f"Low confidence detected in: {', '.join(low_conf_phases)}")

    return insights[:5]


def _hiring_recommendation(overall_pct: float, phase_breakdown: dict, proctoring_summary: dict) -> str:
    """Generate a hiring recommendation based on overall performance and proctoring."""
    # Check for critical proctoring issues
    if proctoring_summary.get("session_flagged", False):
        return "Interview flagged due to proctoring violations. Manual review required before proceeding."
    
    high_violations = proctoring_summary.get("high_severity_count", 0)
    if high_violations >= 3:
        return "Multiple high-severity proctoring violations detected. Recommend re-interview under stricter monitoring."
    
    if overall_pct >= 80:
        return "Strong candidate. Recommend advancing to the next round."
    elif overall_pct >= 65:
        weak_areas = []
        for phase, data in phase_breakdown.items():
            if data.get("score_pct", 0) < 60:
                weak_areas.append(phase)
        if weak_areas:
            return f"Promising candidate with gaps in {', '.join(weak_areas)}. Consider a focused follow-up round."
        return "Solid candidate. Recommend advancing with minor focus areas."
    elif overall_pct >= 50:
        return "Average performance. Recommend additional preparation before re-interviewing."
    else:
        return "Below expectations. Significant improvement needed across multiple areas."



def _build_proctoring_summary(violations: list[dict]) -> dict:
    """Build a summary of proctoring violations."""
    if not violations:
        return {
            "total_violations": 0,
            "session_flagged": False,
            "high_severity_count": 0,
            "medium_severity_count": 0,
            "low_severity_count": 0,
            "violation_types": {},
            "timeline": [],
        }
    
    severity_counts = {"high": 0, "medium": 0, "low": 0}
    violation_types = {}
    
    for v in violations:
        severity = v.get("severity", "low")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        v_type = v.get("violation_type", "unknown")
        violation_types[v_type] = violation_types.get(v_type, 0) + 1
    
    # Session is flagged if there are 3+ high severity or 5+ medium severity violations
    session_flagged = severity_counts["high"] >= 3 or severity_counts["medium"] >= 5
    
    # Timeline of violations (last 10)
    timeline = [
        {
            "type": v.get("violation_type", "unknown"),
            "severity": v.get("severity", "low"),
            "message": v.get("message", ""),
            "timestamp": v.get("timestamp").isoformat() if v.get("timestamp") else "",
        }
        for v in violations[-10:]
    ]
    
    return {
        "total_violations": len(violations),
        "session_flagged": session_flagged,
        "high_severity_count": severity_counts["high"],
        "medium_severity_count": severity_counts["medium"],
        "low_severity_count": severity_counts["low"],
        "violation_types": violation_types,
        "timeline": timeline,
    }


def _build_behavioral_summary(sentiment_data: list[dict]) -> dict:
    """Build a summary of behavioral and sentiment analysis."""
    if not sentiment_data:
        return {
            "avg_confidence_score": 0,
            "avg_speaking_rate": 0,
            "avg_filler_rate": 0,
            "dominant_emotion": "neutral",
            "dominant_sentiment": "neutral",
            "posture_issues": 0,
            "gaze_issues": 0,
            "behavioral_flags": [],
        }
    
    # Calculate averages
    confidence_scores = [s.get("confidence_score", 50) for s in sentiment_data if s.get("confidence_score")]
    speaking_rates = [s.get("speaking_rate_wpm", 0) for s in sentiment_data if s.get("speaking_rate_wpm")]
    filler_rates = [s.get("filler_rate", 0) for s in sentiment_data if s.get("filler_rate")]
    
    avg_confidence = round(sum(confidence_scores) / len(confidence_scores)) if confidence_scores else 50
    avg_speaking_rate = round(sum(speaking_rates) / len(speaking_rates)) if speaking_rates else 0
    avg_filler_rate = round(sum(filler_rates) / len(filler_rates), 1) if filler_rates else 0
    
    # Dominant emotion and sentiment
    emotions = [s.get("emotion") for s in sentiment_data if s.get("emotion")]
    sentiments = [s.get("sentiment") for s in sentiment_data if s.get("sentiment")]
    
    dominant_emotion = max(set(emotions), key=emotions.count) if emotions else "neutral"
    dominant_sentiment = max(set(sentiments), key=sentiments.count) if sentiments else "neutral"
    
    # Count posture and gaze issues
    posture_issues = sum(
        1 for s in sentiment_data 
        if s.get("posture") in ["slouching", "leaning_away", "face_not_visible"]
    )
    gaze_issues = sum(
        1 for s in sentiment_data 
        if s.get("gaze_direction") and s.get("gaze_direction") != "center"
    )
    
    # Collect unique behavioral flags
    all_flags = []
    for s in sentiment_data:
        flags = s.get("flags", [])
        if flags:
            all_flags.extend(flags)
    
    behavioral_flags = list(dict.fromkeys(all_flags))[:10]  # Top 10 unique flags
    
    return {
        "avg_confidence_score": avg_confidence,
        "avg_speaking_rate": avg_speaking_rate,
        "avg_filler_rate": avg_filler_rate,
        "dominant_emotion": dominant_emotion,
        "dominant_sentiment": dominant_sentiment,
        "posture_issues": posture_issues,
        "gaze_issues": gaze_issues,
        "behavioral_flags": behavioral_flags,
        "total_data_points": len(sentiment_data),
    }
