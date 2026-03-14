"""Tone / sentiment analysis for interview responses.

Rule-based approach — zero extra latency (no LLM call).
Combines text signals (fillers, hedging, confidence markers)
with basic audio prosody (speaking rate, RMS energy) from the WAV bytes.
"""

from __future__ import annotations

import io
import re
import struct
import wave
from dataclasses import asdict, dataclass

# ── Word / phrase lists ───────────────────────────────────────────────────────

_FILLER_WORDS: frozenset[str] = frozenset({
    "um", "uh", "hmm", "err", "ah", "like", "basically", "literally",
    "actually", "honestly", "obviously", "right", "so", "okay", "well",
})

_HEDGE_PHRASES: tuple[str, ...] = (
    "i think", "i guess", "i'm not sure", "i am not sure",
    "maybe", "probably", "kind of", "sort of", "i believe",
    "not entirely sure", "i don't know", "i dont know", "i mean",
    "something like", "roughly", "approximately", "not really",
    "not quite", "more or less", "could be", "might be", "not certain",
)

_CONFIDENCE_MARKERS: tuple[str, ...] = (
    "specifically", "clearly", "definitely", "certainly", "for example",
    "for instance", "the reason", "because", "therefore", "thus",
    "in summary", "to summarize", "firstly", "secondly", "thirdly",
    "in conclusion", "the key", "the main", "the core",
    "the approach", "the solution", "the idea",
)

_ENTHUSIASM_MARKERS: tuple[str, ...] = (
    "really", "great question", "interesting", "love", "excited",
    "fascinating", "absolutely", "definitely", "exactly",
)

# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class SentimentResult:
    emotion: str              # confident | hesitant | nervous | enthusiastic | neutral
    filler_rate: float        # filler words per 100 words
    speaking_rate_wpm: float  # estimated words per minute (0 if no audio)
    energy_level: str         # low | medium | high
    hedge_count: int          # number of hedge phrases found
    score: float              # 0–1 classifier confidence

    def to_dict(self) -> dict:
        return asdict(self)


# ── Prosody extraction ────────────────────────────────────────────────────────


def _extract_prosody(
    audio_bytes: bytes, word_count: int
) -> tuple[float, str, float]:
    """Return (speaking_rate_wpm, energy_level, duration_s) from WAV bytes.

    Falls back to neutral values if the bytes cannot be parsed.
    """
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            n_frames = wf.getnframes()
            framerate = wf.getframerate()
            sampwidth = wf.getsampwidth()
            duration_s = n_frames / framerate if framerate else 0.0

            raw = wf.readframes(n_frames)
            if sampwidth == 2 and raw:
                samples = struct.unpack(f"<{len(raw) // 2}h", raw)
                max_val = 32768.0
            elif raw:
                samples = struct.unpack(f"{len(raw)}B", raw)
                max_val = 128.0
            else:
                return 0.0, "medium", 0.0

            rms = (sum(s * s for s in samples) / len(samples)) ** 0.5 / max_val
            energy_level = (
                "high" if rms > 0.18 else ("medium" if rms > 0.07 else "low")
            )
            speaking_rate_wpm = (
                (word_count / duration_s * 60) if duration_s > 0 else 0.0
            )
            return round(speaking_rate_wpm, 1), energy_level, round(duration_s, 2)
    except Exception:
        return 0.0, "medium", 0.0


# ── Main analysis function ────────────────────────────────────────────────────


def analyze_tone(
    transcript: str,
    audio_bytes: bytes | None = None,
) -> SentimentResult:
    """Analyze the emotional tone of a candidate's interview response.

    Args:
        transcript: Plain-text transcription of the candidate's speech.
        audio_bytes: Raw WAV bytes for prosody extraction (optional).

    Returns:
        SentimentResult with emotion label and supporting metrics.
    """
    text = transcript.lower().strip()
    # Tokenize simply — strip punctuation from each word
    words = [re.sub(r"[^\w]", "", w) for w in text.split()]
    words = [w for w in words if w]
    word_count = max(len(words), 1)

    # ── Text signals ─────────────────────────────────────────────────────────

    filler_count = sum(1 for w in words if w in _FILLER_WORDS)
    filler_rate = (filler_count / word_count) * 100  # per-100-words rate

    hedge_count = sum(1 for phrase in _HEDGE_PHRASES if phrase in text)
    confidence_count = sum(1 for m in _CONFIDENCE_MARKERS if m in text)
    enthusiasm_count = sum(1 for m in _ENTHUSIASM_MARKERS if m in text)

    # ── Prosody signals ───────────────────────────────────────────────────────

    if audio_bytes:
        speaking_rate_wpm, energy_level, _ = _extract_prosody(
            audio_bytes, word_count
        )
    else:
        speaking_rate_wpm, energy_level = 0.0, "medium"

    # ── Scoring heuristics ────────────────────────────────────────────────────

    # Nervousness: high fillers, many hedges, very fast / very slow speech,
    # low energy, very short response
    nervousness = (
        (filler_rate / 8)           # 0–~1.5 range
        + (hedge_count * 0.35)
        + (1.0 if speaking_rate_wpm > 185 else 0.0)   # rushing
        + (0.5 if speaking_rate_wpm > 0 and speaking_rate_wpm < 80 else 0.0)  # hesitating
        + (0.5 if energy_level == "low" else 0.0)
        + (0.6 if word_count < 12 else 0.0)           # very short answer
    )

    # Confidence: structured markers, decent pace, medium–high energy
    confidence = (
        (confidence_count * 0.5)
        + (1.0 if 110 <= speaking_rate_wpm <= 165 else 0.0)
        + (0.5 if energy_level in ("medium", "high") else 0.0)
        + (0.4 if word_count >= 30 else 0.0)
    )

    # Enthusiasm: positive + expressive language, longer responses
    enthusiasm = (
        (enthusiasm_count * 0.4)
        + (0.5 if word_count >= 60 else 0.0)
        + (0.5 if filler_rate < 3 and confidence_count >= 1 else 0.0)
    )

    # ── Classify ─────────────────────────────────────────────────────────────

    if nervousness >= 2.5:
        emotion = "nervous"
        score = min(0.92, nervousness / 4.0)
    elif nervousness >= 1.4 and nervousness > confidence:
        emotion = "hesitant"
        score = 0.68
    elif enthusiasm >= 1.5 and confidence >= 1.0:
        emotion = "enthusiastic"
        score = min(0.88, enthusiasm / 2.5)
    elif confidence >= 1.5:
        emotion = "confident"
        score = min(0.90, confidence / 3.0)
    else:
        emotion = "neutral"
        score = 0.50

    return SentimentResult(
        emotion=emotion,
        filler_rate=round(filler_rate, 1),
        speaking_rate_wpm=speaking_rate_wpm,
        energy_level=energy_level,
        hedge_count=hedge_count,
        score=round(score, 2),
    )
