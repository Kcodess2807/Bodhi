"""Speech analysis service.

Pipeline:
  1. Convert incoming audio to 16 kHz mono WAV (librosa + soundfile)
  2. Sarvam AI saaras:v3 — speech-to-text + language detection
  3. j-hartmann/emotion-english-distilroberta-base — emotion label + confidence
  4. cardiffnlp/twitter-roberta-base-sentiment-latest — sentiment polarity
  5. librosa.yin — pitch variance from the audio signal
  6. Rule-based behavioral flags from all signals above
"""
from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path
from typing import Optional

import librosa
import numpy as np
import soundfile as sf
from dotenv import load_dotenv
from sarvamai import SarvamAI
from transformers import pipeline as hf_pipeline

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────

SARVAM_API_KEY: str = os.getenv("SARVAM_API_KEY", "")
SARVAM_MODEL: str = os.getenv("SARVAM_STT_MODEL", "saaras:v3")
EMOTION_MODEL: str = os.getenv(
    "EMOTION_MODEL", "j-hartmann/emotion-english-distilroberta-base"
)
SENTIMENT_MODEL: str = os.getenv(
    "SENTIMENT_MODEL", "cardiffnlp/twitter-roberta-base-sentiment-latest"
)

# ── Singleton model handles ───────────────────────────────────────────────────

_emotion_pipe = None
_sentiment_pipe = None


def load_models() -> None:
    """Pre-load both HuggingFace pipelines. Safe to call multiple times."""
    global _emotion_pipe, _sentiment_pipe
    if _emotion_pipe is None:
        _emotion_pipe = hf_pipeline(
            "text-classification",
            model=EMOTION_MODEL,
            top_k=1,
            truncation=True,
            max_length=512,
            model_kwargs={"use_safetensors": True},
        )
    if _sentiment_pipe is None:
        _sentiment_pipe = hf_pipeline(
            "text-classification",
            model=SENTIMENT_MODEL,
            top_k=1,
            truncation=True,
            max_length=512,
            model_kwargs={"use_safetensors": True},
        )


def models_ready() -> bool:
    return _emotion_pipe is not None and _sentiment_pipe is not None


# ── Audio pre-processing ──────────────────────────────────────────────────────


def _to_wav_16k(audio_bytes: bytes) -> bytes:
    """Resample any supported audio format to 16 kHz mono PCM-16 WAV.

    librosa handles WAV, MP3, OGG, FLAC, and WebM (if ffmpeg is available).
    The resulting bytes are safe to pass directly to the Sarvam STT API.
    """
    buf = io.BytesIO(audio_bytes)
    # sr=16000 resamples on load; mono=True downmixes multi-channel
    y, _ = librosa.load(buf, sr=16000, mono=True)

    out = io.BytesIO()
    sf.write(out, y, 16000, format="WAV", subtype="PCM_16")
    return out.getvalue()


# ── Sarvam STT ────────────────────────────────────────────────────────────────


def _transcribe(wav_bytes: bytes) -> tuple[str, str]:
    """Return (transcript, language_code) via Sarvam saaras:v3.

    Falls back to ("", "en-IN") if the API key is not configured.
    """
    if not SARVAM_API_KEY:
        return "", "en-IN"

    client = SarvamAI(api_subscription_key=SARVAM_API_KEY)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav_bytes)
        tmp_path = Path(tmp.name)

    try:
        with open(tmp_path, "rb") as f:
            resp = client.speech_to_text.transcribe(
                file=f,
                model=SARVAM_MODEL,
                mode="transcribe",
                language_code="en-IN",
            )
        transcript = ""
        language = "en-IN"
        if hasattr(resp, "transcript"):
            transcript = resp.transcript or ""
        if hasattr(resp, "language_code"):
            language = resp.language_code or "en-IN"
        return transcript, language
    finally:
        tmp_path.unlink(missing_ok=True)


# ── Librosa audio features ────────────────────────────────────────────────────


def _extract_audio_features(wav_bytes: bytes, transcript: str) -> tuple[int, float]:
    """Return (speech_rate_wpm, pitch_variance).

    speech_rate_wpm is derived from the transcript word count and audio duration.
    pitch_variance is the standard deviation of voiced F0 frames (librosa YIN).
    """
    try:
        buf = io.BytesIO(wav_bytes)
        y, sr = librosa.load(buf, sr=None, mono=True)
        duration_s = len(y) / sr if sr > 0 else 0.0

        # WPM: count non-empty words in the transcript divided by duration
        word_count = len(transcript.split()) if transcript.strip() else 0
        speech_rate_wpm = int(word_count / duration_s * 60) if duration_s > 0 else 0

        # Pitch variance via YIN fundamental frequency estimation
        f0 = librosa.yin(
            y,
            fmin=float(librosa.note_to_hz("C2")),
            fmax=float(librosa.note_to_hz("C7")),
            sr=sr,
        )
        # Discard unvoiced frames (YIN marks them at fmin or 0)
        voiced = f0[(f0 > librosa.note_to_hz("C2") * 1.1)]
        pitch_variance = float(np.std(voiced)) if len(voiced) > 10 else 0.0

        return speech_rate_wpm, round(pitch_variance, 2)
    except Exception:
        return 0, 0.0


# ── HuggingFace emotion + sentiment ──────────────────────────────────────────


def _detect_emotion(text: str) -> tuple[str, float]:
    """Return (emotion_label, confidence) using distilroberta emotion model."""
    if not text.strip() or _emotion_pipe is None:
        return "neutral", 0.5

    try:
        result = _emotion_pipe(text[:512])
        # Pipeline with top_k=1 returns [[{"label": ..., "score": ...}]]
        item = result[0] if isinstance(result[0], dict) else result[0][0]
        return item["label"].lower(), round(float(item["score"]), 3)
    except Exception:
        return "neutral", 0.5


def _detect_sentiment(text: str) -> str:
    """Return 'positive' | 'neutral' | 'negative' from roberta sentiment model."""
    if not text.strip() or _sentiment_pipe is None:
        return "neutral"

    try:
        result = _sentiment_pipe(text[:512])
        item = result[0] if isinstance(result[0], dict) else result[0][0]
        label = item["label"].lower()
        # cardiffnlp model outputs: "positive", "neutral", "negative"
        # (some checkpoints use "label_0/1/2" — map those too)
        mapping = {"label_0": "negative", "label_1": "neutral", "label_2": "positive"}
        return mapping.get(label, label)
    except Exception:
        return "neutral"


# ── Behavioral flags + confidence score ──────────────────────────────────────

# Filler words that indicate hesitation
_FILLERS = frozenset(
    {"um", "uh", "hmm", "err", "ah", "like", "basically", "literally", "right", "so"}
)


def _derive_flags(
    emotion: str,
    sentiment: str,
    speech_rate_wpm: int,
    pitch_variance: float,
    transcript: str,
) -> list[str]:
    """Derive behavioral flags from combined audio + text signals."""
    flags: list[str] = []
    words = [w.strip(".,!?;:") for w in transcript.lower().split()]
    filler_count = sum(1 for w in words if w in _FILLERS)
    filler_rate = (filler_count / max(len(words), 1)) * 100

    # Nervous: fear emotion, or extreme speaking rate, or high filler rate
    if emotion == "fear" or (speech_rate_wpm > 0 and speech_rate_wpm > 200) or filler_rate > 8:
        flags.append("nervous")

    # Rushed: very fast speech
    if speech_rate_wpm > 200:
        flags.append("rushed")

    # Hesitant: too slow, or many filler words, or hedging language
    hesitant_phrases = ("i think", "i guess", "maybe", "kind of", "sort of", "not sure")
    if (
        (speech_rate_wpm > 0 and speech_rate_wpm < 80)
        or filler_rate > 6
        or any(p in transcript.lower() for p in hesitant_phrases)
    ):
        flags.append("hesitant")

    # Distressed: anger or sadness emotion
    if emotion in ("anger", "sadness", "disgust"):
        flags.append("distressed")

    # Confident: joy + positive + moderate pace + low fillers
    if (
        emotion in ("joy", "neutral")
        and sentiment == "positive"
        and 90 <= speech_rate_wpm <= 180
        and filler_rate < 4
    ):
        flags.append("confident")

    return flags


def _compute_confidence_score(
    emotion: str,
    sentiment: str,
    flags: list[str],
    speech_rate_wpm: int,
) -> int:
    """Compute a 0–100 confidence score based on all signals."""
    score = 50

    # Emotion contributions
    emotion_delta = {
        "joy": +20,
        "neutral": +5,
        "surprise": +5,
        "fear": -20,
        "sadness": -15,
        "anger": -15,
        "disgust": -10,
    }
    score += emotion_delta.get(emotion, 0)

    # Sentiment contributions
    if sentiment == "positive":
        score += 10
    elif sentiment == "negative":
        score -= 10

    # Flag contributions
    if "confident" in flags:
        score += 10
    if "nervous" in flags:
        score -= 10
    if "rushed" in flags:
        score -= 5
    if "hesitant" in flags:
        score -= 5
    if "distressed" in flags:
        score -= 10

    # Moderate pace bonus
    if 90 <= speech_rate_wpm <= 180:
        score += 5

    return max(0, min(100, score))


# ── Public entry point ────────────────────────────────────────────────────────


def analyze_speech(audio_bytes: bytes, filename: str) -> dict:
    """Run the full speech analysis pipeline on raw audio bytes.

    Args:
        audio_bytes: Raw bytes from the uploaded audio file.
        filename: Original filename (used for format detection logging).

    Returns:
        Dict matching the SpeechResult schema.
    """
    load_models()

    # Step 1: Normalise to 16kHz mono WAV
    wav_bytes = _to_wav_16k(audio_bytes)

    # Step 2: Transcribe via Sarvam STT
    transcript, language = _transcribe(wav_bytes)

    # Step 3: Librosa audio features (need transcript for WPM)
    speech_rate_wpm, pitch_variance = _extract_audio_features(wav_bytes, transcript)

    # Step 4: HuggingFace emotion detection
    emotion, emotion_confidence = _detect_emotion(transcript)

    # Step 5: HuggingFace sentiment detection
    sentiment = _detect_sentiment(transcript)

    # Step 6: Behavioral flags
    flags = _derive_flags(emotion, sentiment, speech_rate_wpm, pitch_variance, transcript)

    # Step 7: Composite confidence score
    confidence_score = _compute_confidence_score(emotion, sentiment, flags, speech_rate_wpm)

    return {
        "transcript": transcript,
        "language": language,
        "emotion": emotion,
        "emotion_confidence": emotion_confidence,
        "sentiment": sentiment,
        "speech_rate_wpm": speech_rate_wpm,
        "pitch_variance": pitch_variance,
        "confidence_score": confidence_score,
        "flags": flags,
    }
