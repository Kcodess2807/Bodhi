"""Bulbul V3 Text-to-Speech via Sarvam AI."""

import base64
import io
import re
from typing import AsyncIterator

import sounddevice as sd
import soundfile as sf
from sarvamai import SarvamAI


def text_to_speech_bytes(
    text: str,
    *,
    api_key: str,
    model: str = "bulbul:v3",
    target_language_code: str = "hi-IN",
    speaker: str = "shubh",
) -> bytes:
    """
    Convert text to speech audio bytes using Bulbul V3.
    Returns raw PCM/WAV bytes suitable for playback.
    """
    client = SarvamAI(api_subscription_key=api_key)

    response = client.text_to_speech.convert(
        text=text,
        target_language_code=target_language_code,
        model=model,
        speaker=speaker,
    )

    audio_b64 = _extract_audio(response)
    return base64.b64decode(audio_b64)


def play_audio(audio_bytes: bytes) -> None:
    """Play audio bytes using sounddevice. Assumes WAV format from Bulbul."""
    data, sample_rate = sf.read(io.BytesIO(audio_bytes))
    sd.play(data, sample_rate)
    sd.wait()


def speak(
    text: str,
    *,
    api_key: str,
    model: str = "bulbul:v3",
    target_language_code: str = "hi-IN",
    speaker: str = "shubh",
    play: bool = True,
) -> bytes:
    """
    Convert text to speech and optionally play it.
    Returns audio bytes.
    """
    audio_bytes = text_to_speech_bytes(
        text=text,
        api_key=api_key,
        model=model,
        target_language_code=target_language_code,
        speaker=speaker,
    )
    if play:
        play_audio(audio_bytes)
    return audio_bytes


def _extract_audio(response) -> str:
    """Extract base64 audio from Sarvam TTS response. Response has audios: [base64...]."""
    if hasattr(response, "audios") and response.audios:
        return response.audios[0]
    if hasattr(response, "audio"):
        return response.audio
    if isinstance(response, dict):
        audios = response.get("audios", [])
        if audios:
            return audios[0]
        return response.get("audio", "")
    return ""


# ── Streaming TTS ─────────────────────────────────────────────────

def split_sentences(text: str) -> list[str]:
    """Split text into sentences on .!? boundaries with a word-count fallback.

    Returns a list of non-empty sentence strings.
    """
    # Split on sentence-ending punctuation followed by whitespace or end-of-string
    raw = re.split(r'(?<=[.!?])\s+', text.strip())

    sentences: list[str] = []
    for chunk in raw:
        chunk = chunk.strip()
        if not chunk:
            continue
        # If a chunk is very long (no punctuation), split on ~15-word boundaries
        words = chunk.split()
        if len(words) > 20:
            buf: list[str] = []
            for w in words:
                buf.append(w)
                if len(buf) >= 15:
                    sentences.append(" ".join(buf))
                    buf = []
            if buf:
                sentences.append(" ".join(buf))
        else:
            sentences.append(chunk)

    return sentences


async def text_to_speech_stream(
    text: str,
    *,
    api_key: str,
    model: str = "bulbul:v3",
    target_language_code: str = "hi-IN",
    speaker: str = "shubh",
) -> AsyncIterator[bytes]:
    """Stream TTS audio chunks via Sarvam WebSocket API.

    Yields raw MP3 bytes as they arrive. Sends text sentence-by-sentence
    so audio generation starts before the full text is processed.
    """
    import logging
    log = logging.getLogger("bodhi.tts.stream")

    from sarvamai import AsyncSarvamAI
    from sarvamai.types.audio_output import AudioOutput
    from sarvamai.types.event_response import EventResponse
    from sarvamai.types.error_response import ErrorResponse

    client = AsyncSarvamAI(api_subscription_key=api_key)

    sentences = split_sentences(text)
    if not sentences:
        log.warning("No sentences after splitting text: %r", text[:100])
        return

    log.info("TTS stream: %d sentences from %d chars", len(sentences), len(text))
    for i, s in enumerate(sentences):
        log.debug("  sentence[%d]: %r", i, s[:80])

    import asyncio

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            async with client.text_to_speech_streaming.connect(
                model=model,
                api_subscription_key=api_key,
                send_completion_event=True,
            ) as ws:
                log.info("WebSocket connected on attempt %d, configuring...", attempt)

                await ws.configure(
                    target_language_code=target_language_code,
                    speaker=speaker,
                    output_audio_codec="mp3",
                    speech_sample_rate=24000,
                    enable_preprocessing=True,
                )
                log.info("WebSocket configured, sending sentences...")

                for i, sentence in enumerate(sentences):
                    await ws.convert(sentence)
                    log.debug("  sent sentence[%d] (%d chars)", i, len(sentence))

                await ws.flush()
                log.info("All sentences sent + flushed, waiting for audio...")

                chunk_count = 0
                total_bytes = 0
                async for message in ws:
                    msg_type = type(message).__name__
                    log.debug("  received message type: %s", msg_type)

                    if isinstance(message, AudioOutput):
                        audio_bytes = base64.b64decode(message.data.audio)
                        chunk_count += 1
                        total_bytes += len(audio_bytes)
                        log.debug("  audio chunk #%d: %d bytes", chunk_count, len(audio_bytes))
                        yield audio_bytes
                    elif isinstance(message, EventResponse):
                        log.info("  completion event received, done")
                        break
                    elif isinstance(message, ErrorResponse):
                        log.error("  TTS error: %s", message)
                        break
                    else:
                        log.warning("  unexpected message: %s", message)

                log.info("TTS stream complete: %d chunks, %d total bytes", chunk_count, total_bytes)
                break  # Success, exit retry loop

        except Exception as exc:
            log.warning("TTS stream connect attempt %d failed: %s: %s", attempt, type(exc).__name__, exc)
            if attempt == max_retries:
                log.error("All %d TTS stream attempts failed.", max_retries, exc_info=True)
                raise
            await asyncio.sleep(1.0)


async def tts_stream_sentences(
    sentences: "AsyncIterator[str]",
    *,
    api_key: str,
    model: str = "bulbul:v3",
    target_language_code: str = "hi-IN",
    speaker: str = "shubh",
) -> AsyncIterator[bytes]:
    """Stream TTS audio as sentences arrive from the LLM — pipelined.

    Unlike text_to_speech_stream (which needs the full text upfront), this
    function consumes an async iterator of sentence strings and converts them
    to audio concurrently:

    1. A producer task reads sentences and sends them via ws.convert()
    2. The main coroutine reads audio chunks from the WS and yields them

    This means TTS audio generation starts as soon as the FIRST sentence
    is ready, even while the LLM is still generating subsequent sentences.
    """
    import logging
    import asyncio
    log = logging.getLogger("bodhi.tts.pipeline")

    from sarvamai import AsyncSarvamAI
    from sarvamai.types.audio_output import AudioOutput
    from sarvamai.types.event_response import EventResponse
    from sarvamai.types.error_response import ErrorResponse

    client = AsyncSarvamAI(api_subscription_key=api_key)

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            async with client.text_to_speech_streaming.connect(
                model=model,
                api_subscription_key=api_key,
                send_completion_event=True,
            ) as ws:
                log.info("[TTS-PIPE] WebSocket connected (attempt %d), configuring...", attempt)

                await ws.configure(
                    target_language_code=target_language_code,
                    speaker=speaker,
                    output_audio_codec="mp3",
                    speech_sample_rate=24000,
                    enable_preprocessing=True,
                )

                # Producer: feed sentences to TTS as they arrive from LLM
                async def _send_sentences():
                    sent_count = 0
                    try:
                        async for sentence in sentences:
                            sentence = sentence.strip()
                            if not sentence:
                                continue
                            try:
                                await ws.convert(sentence)
                                sent_count += 1
                                log.info("[TTS-PIPE] Sent sentence #%d (%d chars): %s",
                                         sent_count, len(sentence), sentence[:60])
                            except websockets.exceptions.ConnectionClosed:
                                log.warning("[TTS-PIPE] Connection closed while sending sentence")
                                break
                        
                        try:
                            await ws.flush()
                            log.info("[TTS-PIPE] All %d sentences sent + flushed", sent_count)
                        except websockets.exceptions.ConnectionClosed:
                            log.warning("[TTS-PIPE] Connection closed while flushing")
                    except asyncio.CancelledError:
                        log.debug("[TTS-PIPE] Producer task cancelled")
                    except Exception as e:
                        log.error("[TTS-PIPE] Sentence producer error: %s", e)

                # Start producer as a background task
                producer = asyncio.create_task(_send_sentences())

                # Consumer: yield audio chunks as they arrive
                chunk_count = 0
                total_bytes = 0
                try:
                    async for message in ws:
                        if isinstance(message, AudioOutput):
                            audio_bytes = base64.b64decode(message.data.audio)
                            chunk_count += 1
                            total_bytes += len(audio_bytes)
                            log.debug("[TTS-PIPE] Audio chunk #%d: %d bytes", chunk_count, len(audio_bytes))
                            yield audio_bytes
                        elif isinstance(message, EventResponse):
                            log.info("[TTS-PIPE] Completion event received")
                            break
                        elif isinstance(message, ErrorResponse):
                            log.error("[TTS-PIPE] TTS error: %s", message)
                            break
                finally:
                    # Cancel producer if it's still running when we finish or error out
                    if not producer.done():
                        producer.cancel()
                        try:
                            await producer
                        except asyncio.CancelledError:
                            pass

                log.info("[TTS-PIPE] Done: %d chunks, %d bytes total", chunk_count, total_bytes)
                break  # Success

        except Exception as exc:
            log.warning("[TTS-PIPE] Attempt %d failed: %s: %s", attempt, type(exc).__name__, exc)
            if attempt == max_retries:
                log.error("[TTS-PIPE] All %d attempts failed", max_retries, exc_info=True)
                raise
            await asyncio.sleep(1.0)

