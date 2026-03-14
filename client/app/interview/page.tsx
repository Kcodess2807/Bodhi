"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  type SessionState,
  type SessionEnd,
  type StreamMeta,
  startInterviewStream,
  sendAudioStream,
  parseStreamHeaders,
  getSession,
  endInterview,
} from "@/lib/api";
import { encodeWav } from "@/lib/wav";

type Phase =
  | "idle"
  | "listening"
  | "recording"
  | "processing"
  | "speaking"
  | "ended";

interface Turn {
  speaker: "user" | "bodhi";
  text: string;
  phase?: string;
}

interface Violation {
  violation_type: string;
  severity: string;
  message: string;
  timestamp: string;
}

const SILENCE_THRESHOLD = 0.015;
const SILENCE_DURATION_MS = 1500;
const SPEECH_CONFIRM_FRAMES = 5;
const MIN_RECORD_MS = 500;
const FRAME_INTERVAL_MS = 2500;

export default function InterviewPage() {
  const [sessionId, setSessionId] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [transcript, setTranscript] = useState<Turn[]>([]);
  const [sessionInfo, setSessionInfo] = useState<SessionState | null>(null);
  const [summary, setSummary] = useState<SessionEnd | null>(null);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState("");

  // Proctoring state
  const [proctoringActive, setProctoringActive] = useState(false);
  const [sessionFlagged, setSessionFlagged] = useState(false);
  const [violations, setViolations] = useState<Violation[]>([]);
  const [cameraError, setCameraError] = useState("");

  const [startForm, setStartForm] = useState({
    candidate_name: "",
    company: "",
    role: "Software Engineer",
  });

  // Audio refs
  const audioCtxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const workletRef = useRef<ScriptProcessorNode | null>(null);
  const samplesRef = useRef<Float32Array[]>([]);
  const silenceStartRef = useRef(0);
  const speechFramesRef = useRef(0);
  const isRecordingRef = useRef(false);
  const recordStartRef = useRef(0);
  const rafRef = useRef(0);
  const phaseRef = useRef<Phase>("idle");
  const sessionIdRef = useRef("");
  const transcriptEndRef = useRef<HTMLDivElement>(null);

  // Proctoring refs
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const proctoringWsRef = useRef<WebSocket | null>(null);
  const frameIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const frameCounterRef = useRef(0);

  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  const scrollDown = () =>
    setTimeout(
      () => transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" }),
      50
    );

  const playAudio = useCallback(
    (b64: string): Promise<void> =>
      new Promise((resolve) => {
        try {
          const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
          const blob = new Blob([bytes], { type: "audio/wav" });
          const url = URL.createObjectURL(blob);
          const audio = new Audio(url);
          audio.onended = () => {
            URL.revokeObjectURL(url);
            resolve();
          };
          audio.onerror = () => {
            URL.revokeObjectURL(url);
            resolve();
          };
          audio.play();
        } catch {
          resolve();
        }
      }),
    []
  );

  /** Play a streaming audio/mpeg response progressively using MediaSource. */
  const playStreamingAudio = useCallback(
    (response: Response): Promise<void> => {
      return new Promise((resolve) => {
        const reader = response.body?.getReader();
        if (!reader) {
          console.warn("[Bodhi] No response body reader available");
          resolve();
          return;
        }

        const mediaSource = new MediaSource();
        const url = URL.createObjectURL(mediaSource);
        const audio = new Audio(url);

        let cleanupDone = false;
        const cleanup = () => {
          if (cleanupDone) return;
          cleanupDone = true;
          console.log("[Bodhi] Audio playback ended/cleaned up");
          URL.revokeObjectURL(url);
          resolve();
        };

        audio.onended = cleanup;
        audio.onerror = (e) => {
          console.error("[Bodhi] Audio playback error:", e);
          cleanup();
        };

        mediaSource.addEventListener("sourceopen", async () => {
          console.log("[Bodhi] MediaSource opened, creating SourceBuffer (audio/mpeg)");
          // Sarvam bulbul model generates MP3 audio
          const mimeCodec = 'audio/mpeg';

          if (!MediaSource.isTypeSupported(mimeCodec)) {
            console.error("[Bodhi] Browser does NOT support", mimeCodec);
            // Fallback: wait for all chunks and play as Blob
            const allChunks: Uint8Array[] = [];
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              if (value) allChunks.push(value as Uint8Array);
            }
            const blob = new Blob(allChunks as BlobPart[], { type: "audio/mpeg" });
            const fallbackUrl = URL.createObjectURL(blob);
            audio.src = fallbackUrl;
            audio.play().catch((err) => {
              console.error("[Bodhi] Fallback audio play() rejected:", err);
              cleanup();
            });
            return;
          }

          const sourceBuffer = mediaSource.addSourceBuffer(mimeCodec);
          const queue: Uint8Array[] = [];
          let isAppending = false;
          let isStreamDone = false;

          const appendNext = () => {
            if (isAppending || sourceBuffer.updating) return;

            if (queue.length > 0) {
              isAppending = true;
              const chunk = queue.shift()!;
              try {
                sourceBuffer.appendBuffer(chunk as unknown as BufferSource);
              } catch (e) {
                console.error("[Bodhi] Buffer append error:", e);
                isAppending = false;
              }
            } else if (isStreamDone) {
              if (mediaSource.readyState === "open") {
                mediaSource.endOfStream();
              }
            }
          };

          sourceBuffer.addEventListener("updateend", () => {
            isAppending = false;
            appendNext();
          });

          audio.play().catch((err) => {
            console.error("[Bodhi] Audio play() rejected:", err);
            cleanup();
          });

          while (true) {
            try {
              const { done, value } = await reader.read();
              if (done) {
                isStreamDone = true;
                appendNext();
                break;
              }
              if (value) {
                queue.push(value as Uint8Array);
                appendNext();
              }
            } catch (err) {
              console.error("[Bodhi] Stream read error:", err);
              if (mediaSource.readyState === "open") {
                mediaSource.endOfStream("network");
              }
              break;
            }
          }
        });

        // Trigger the sourceopen event
        audio.src = url;
      });
    },
    []
  );

  // ── Mic setup ──────────────────────────────────────────

  const initMic = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, sampleRate: 16000 },
    });
    const ctx = new AudioContext({ sampleRate: 16000 });
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);

    const processor = ctx.createScriptProcessor(4096, 1, 1);
    source.connect(processor);
    processor.connect(ctx.destination);

    processor.onaudioprocess = (e) => {
      if (!isRecordingRef.current) return;
      const input = e.inputBuffer.getChannelData(0);
      samplesRef.current.push(new Float32Array(input));
    };

    audioCtxRef.current = ctx;
    streamRef.current = stream;
    analyserRef.current = analyser;
    workletRef.current = processor;
  }, []);

  const cleanupMic = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    workletRef.current?.disconnect();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    audioCtxRef.current?.close();
    audioCtxRef.current = null;
    streamRef.current = null;
    analyserRef.current = null;
    workletRef.current = null;
  }, []);

  // ── Camera setup ───────────────────────────────────────

  const initCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: "user" },
      });
      cameraStreamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
    } catch (err) {
      setCameraError("Camera not available — proctoring disabled.");
      console.warn("Camera init failed:", err);
    }
  }, []);

  const cleanupCamera = useCallback(() => {
    if (frameIntervalRef.current) {
      clearInterval(frameIntervalRef.current);
      frameIntervalRef.current = null;
    }
    cameraStreamRef.current?.getTracks().forEach((t) => t.stop());
    cameraStreamRef.current = null;
  }, []);

  // ── Capture frame from video as base64 JPEG ────────────

  const captureFrame = useCallback((): string | null => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) return null;

    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;

    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    // Remove the data:image/jpeg;base64, prefix
    return canvas.toDataURL("image/jpeg", 0.8).split(",")[1];
  }, []);

  // ── Proctoring WebSocket ────────────────────────────────

  const connectProctoringWs = useCallback(
    (sid: string, referenceImageB64: string) => {
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const wsBase = apiBase.replace(/^http/, "ws");
      const ws = new WebSocket(`${wsBase}/api/proctoring/ws/${sid}`);
      proctoringWsRef.current = ws;

      ws.onopen = () => {
        // Enroll with reference photo
        ws.send(
          JSON.stringify({
            type: "enroll",
            candidate_id: sid,
            image: referenceImageB64,
          })
        );
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);

          if (msg.type === "enrolled") {
            if (msg.success) {
              setProctoringActive(true);
              // Start sending frames
              frameIntervalRef.current = setInterval(() => {
                if (proctoringWsRef.current?.readyState !== WebSocket.OPEN) return;
                const frame = captureFrame();
                if (!frame) return;
                frameCounterRef.current += 1;
                proctoringWsRef.current.send(
                  JSON.stringify({
                    type: "frame",
                    frame_id: `frame-${frameCounterRef.current}`,
                    frame,
                  })
                );
              }, FRAME_INTERVAL_MS);
            }
          } else if (msg.type === "frame_result") {
            if (msg.has_violations && msg.violations?.length > 0) {
              setViolations((prev) => [...prev, ...msg.violations].slice(-20));
            }
            if (msg.session_flagged) {
              setSessionFlagged(true);
            }
          } else if (msg.type === "session_flagged") {
            setSessionFlagged(true);
          }
        } catch {
          // ignore parse errors
        }
      };

      ws.onerror = () => {
        setCameraError("Proctoring connection error.");
      };

      ws.onclose = () => {
        setProctoringActive(false);
      };
    },
    [captureFrame]
  );

  const endProctoringSession = useCallback(() => {
    if (frameIntervalRef.current) {
      clearInterval(frameIntervalRef.current);
      frameIntervalRef.current = null;
    }
    const ws = proctoringWsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "end_session" }));
      ws.close();
    }
    proctoringWsRef.current = null;
  }, []);

  // ── VAD loop ───────────────────────────────────────────

  const startListening = useCallback(() => {
    setPhase("listening");
    phaseRef.current = "listening";
    isRecordingRef.current = false;
    samplesRef.current = [];
    silenceStartRef.current = 0;
    speechFramesRef.current = 0;

    const analyser = analyserRef.current;
    if (!analyser) return;
    const buf = new Float32Array(analyser.fftSize);

    const tick = () => {
      if (phaseRef.current !== "listening" && phaseRef.current !== "recording")
        return;

      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
      const rms = Math.sqrt(sum / buf.length);
      setLevel(rms);

      const now = Date.now();
      const isSpeech = rms > SILENCE_THRESHOLD;

      if (phaseRef.current === "listening") {
        if (isSpeech) {
          speechFramesRef.current++;
          if (speechFramesRef.current >= SPEECH_CONFIRM_FRAMES) {
            isRecordingRef.current = true;
            recordStartRef.current = now;
            samplesRef.current = [];
            setPhase("recording");
          }
        } else {
          speechFramesRef.current = 0;
        }
      } else if (phaseRef.current === "recording") {
        if (!isSpeech) {
          if (silenceStartRef.current === 0) silenceStartRef.current = now;
          else if (
            now - silenceStartRef.current >= SILENCE_DURATION_MS &&
            now - recordStartRef.current >= MIN_RECORD_MS
          ) {
            isRecordingRef.current = false;
            finishRecording();
            return;
          }
        } else {
          silenceStartRef.current = 0;
        }
      }

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
  }, []);

  // ── Finish recording & send ────────────────────────────

  const finishRecording = useCallback(async () => {
    setPhase("processing");
    phaseRef.current = "processing";
    setLevel(0);

    const chunks = samplesRef.current;
    if (chunks.length === 0) {
      startListening();
      return;
    }

    const totalLen = chunks.reduce((a, c) => a + c.length, 0);
    const merged = new Float32Array(totalLen);
    let offset = 0;
    for (const c of chunks) {
      merged.set(c, offset);
      offset += c.length;
    }
    samplesRef.current = [];

    const ctx = audioCtxRef.current;
    const wavBlob = encodeWav(merged, ctx?.sampleRate ?? 16000);

    try {
      const res = await sendAudioStream(
        sessionIdRef.current,
        wavBlob,
        "recording.wav"
      );

      if (!res.ok) {
        const errText = await res.text().catch(() => res.statusText);
        throw new Error(`${res.status}: ${errText}`);
      }

      const meta: StreamMeta = parseStreamHeaders(res);

      if (meta.transcript) {
        setTranscript((prev) => [...prev, { speaker: "user", text: meta.transcript! }]);
      }
      if (meta.text) {
        setTranscript((prev) => [
          ...prev,
          { speaker: "bodhi", text: meta.text!, phase: meta.phase },
        ]);
      }
      scrollDown();

      setPhase("speaking");
      phaseRef.current = "speaking";
      await playStreamingAudio(res);

      if (meta.shouldEnd) {
        setPhase("ended");
        endProctoringSession();
        phaseRef.current = "ended";
        try {
          const end = await endInterview(sessionIdRef.current);
          setSummary(end);
        } catch {}
        cleanupMic();
        cleanupCamera();
        return;
      }

      refreshSession();
      startListening();
    } catch (err) {
      setError(String(err));
      startListening();
    }
  }, [playStreamingAudio, cleanupMic, cleanupCamera, startListening, endProctoringSession]);

  const refreshSession = async () => {
    try {
      const info = await getSession(sessionIdRef.current);
      setSessionInfo(info);
    } catch {}
  };

  // ── Start interview ────────────────────────────────────

  const handleStart = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setPhase("processing");
    phaseRef.current = "processing";
    try {
      // Init mic and camera in parallel
      await Promise.all([initMic(), initCamera()]);

      // Brief wait for video to be ready, then capture reference photo
      await new Promise((res) => setTimeout(res, 800));
      const referencePhoto = captureFrame();

      const res = await startInterviewStream(startForm);

      if (!res.ok) {
        const errText = await res.text().catch(() => res.statusText);
        throw new Error(`${res.status}: ${errText}`);
      }

      const meta: StreamMeta = parseStreamHeaders(res);

      if (meta.session) {
        setSessionId(meta.session);
      }
      if (meta.text) {
        setTranscript([
          { speaker: "bodhi", text: meta.text, phase: "intro" },
        ]);

      // Connect proctoring WebSocket (if camera is available)
      if (referencePhoto) {
        connectProctoringWs(r.session_id, referencePhoto);
      }
      }

      setPhase("speaking");
      await playStreamingAudio(res);

      refreshSession();
      startListening();
    } catch (err) {
      setError(String(err));
      setPhase("idle");
    }
  };

  const handleEnd = async () => {
    cancelAnimationFrame(rafRef.current);
    isRecordingRef.current = false;
    setPhase("processing");
    endProctoringSession();
    try {
      const r = await endInterview(sessionIdRef.current);
      setSummary(r);
      setPhase("ended");
    } catch (err) {
      setError(String(err));
    }
    cleanupMic();
    cleanupCamera();
  };

  // ── Cleanup on unmount ─────────────────────────────────

  useEffect(() => {
    return () => {
      cancelAnimationFrame(rafRef.current);
      cleanupMic();
      cleanupCamera();
      endProctoringSession();
    };
  }, [cleanupMic, cleanupCamera, endProctoringSession]);

  // ── Render ─────────────────────────────────────────────

  const inputCls =
    "rounded border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm w-full";

  if (phase === "idle") {
    return (
      <div className="mx-auto max-w-lg space-y-6 pt-12">
        <h1 className="text-center text-2xl font-bold">Mock Interview</h1>
        <p className="text-center text-sm text-zinc-400">
          Hands-free voice conversation. Speak naturally — Bodhi listens, responds, and loops.
        </p>
        {error && (
          <div className="rounded border border-red-800 bg-red-900/30 px-4 py-2 text-sm text-red-300">
            {error}
          </div>
        )}
        <form
          onSubmit={handleStart}
          className="space-y-3 rounded-lg border border-[var(--border)] bg-[var(--card)] p-5"
        >
          <input
            placeholder="Your name"
            value={startForm.candidate_name}
            onChange={(e) =>
              setStartForm({ ...startForm, candidate_name: e.target.value })
            }
            className={inputCls}
          />
          <input
            placeholder="Company"
            value={startForm.company}
            onChange={(e) =>
              setStartForm({ ...startForm, company: e.target.value })
            }
            className={inputCls}
          />
          <input
            placeholder="Role"
            value={startForm.role}
            onChange={(e) =>
              setStartForm({ ...startForm, role: e.target.value })
            }
            className={inputCls}
          />
          <button
            type="submit"
            className="w-full rounded border border-white py-2.5 text-sm font-medium text-white transition hover:bg-white hover:text-black"
          >
            Start Interview
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-80px)] gap-4">
      {/* Hidden canvas for frame capture */}
      <canvas ref={canvasRef} className="hidden" />

      {/* Main area */}
      <div className="flex flex-1 flex-col">
        {/* Header */}
        <div className="mb-3 flex items-center justify-between">
          <h1 className="text-xl font-bold">Interview</h1>
          <div className="flex items-center gap-3">
            <span className="text-xs text-zinc-500">{sessionId}</span>
            {phase !== "ended" && (
              <button
                onClick={handleEnd}
                className="rounded bg-red-600 px-3 py-1 text-xs font-medium text-white hover:bg-red-500"
              >
                End Interview
              </button>
            )}
          </div>
        </div>

        {error && (
          <div className="mb-2 rounded border border-red-800 bg-red-900/30 px-3 py-1.5 text-xs text-red-300">
            {error}
          </div>
        )}

        {/* Status indicator */}
        <div className="mb-3 flex items-center gap-3">
          <div
            className={`h-3 w-3 rounded-full transition-all ${
              phase === "listening"
                ? "animate-pulse bg-green-400"
                : phase === "recording"
                  ? "bg-red-500"
                  : phase === "processing"
                    ? "animate-pulse bg-yellow-400"
                    : phase === "speaking"
                      ? "animate-pulse bg-blue-400"
                      : "bg-zinc-600"
            }`}
          />
          <span className="text-sm text-zinc-400">
            {phase === "listening" && "Listening... speak when ready"}
            {phase === "recording" && "Recording your answer..."}
            {phase === "processing" && "Processing..."}
            {phase === "speaking" && "Bodhi is speaking..."}
            {phase === "ended" && "Interview ended"}
          </span>
          {(phase === "listening" || phase === "recording") && (
            <div className="flex h-4 items-end gap-0.5">
              {Array.from({ length: 20 }).map((_, i) => (
                <div
                  key={i}
                  className="w-1 rounded-sm bg-white transition-all"
                  style={{
                    height: `${Math.min(100, Math.max(8, level * 3000 * (1 + Math.random() * 0.3)))}%`,
                    opacity: level > SILENCE_THRESHOLD ? 1 : 0.3,
                  }}
                />
              ))}
            </div>
          )}
        </div>

        {/* Transcript */}
        <div
          className="flex-1 space-y-4 overflow-y-auto rounded-lg border border-[var(--border)] bg-[var(--card)] p-5"
        >
          {transcript.map((t, i) => (
            <div key={i} className="flex gap-3">
              <div
                className={`mt-0.5 h-7 w-7 shrink-0 rounded-full flex items-center justify-center text-xs font-bold ${
                  t.speaker === "bodhi"
                    ? "bg-white text-black"
                    : "bg-zinc-700 text-zinc-300"
                }`}
              >
                {t.speaker === "bodhi" ? "B" : "U"}
              </div>
              <div className="flex-1">
                {t.phase && (
                  <span className="mb-0.5 inline-block rounded bg-white/5 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-zinc-500">
                    {t.phase}
                  </span>
                )}
                <p className="text-sm leading-relaxed text-zinc-200 whitespace-pre-wrap">
                  {t.text}
                </p>
              </div>
            </div>
          ))}
          {phase === "processing" && (
            <div className="flex gap-3">
              <div className="mt-0.5 h-7 w-7 shrink-0 rounded-full flex items-center justify-center text-xs font-bold bg-white text-black">
                B
              </div>
              <p className="text-sm text-zinc-500 animate-pulse">Thinking...</p>
            </div>
          )}
          <div ref={transcriptEndRef} />
        </div>

        {/* Summary */}
        {summary && (
          <div className="mt-3 rounded-lg border border-green-700 bg-green-900/30 p-4 text-sm">
            <h3 className="mb-1 font-semibold text-green-300">Interview Complete</h3>
            <p className="text-zinc-300">{summary.summary}</p>
            {summary.overall_score != null && (
              <p className="mt-1 text-zinc-400">
                Score: {summary.overall_score.toFixed(2)}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Sidebar */}
      <div className="hidden w-52 shrink-0 space-y-3 lg:block">
        {/* Camera preview */}
        <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] overflow-hidden">
          <video
            ref={videoRef}
            muted
            playsInline
            className="w-full rounded-lg"
            style={{ transform: "scaleX(-1)" }}
          />
          {cameraError && (
            <p className="px-3 py-2 text-xs text-zinc-500">{cameraError}</p>
          )}
        </div>

        {/* Proctoring status */}
        <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-3 text-sm">
          <div className="mb-2 flex items-center gap-2">
            <div
              className={`h-2 w-2 rounded-full ${
                sessionFlagged
                  ? "bg-red-500"
                  : proctoringActive
                    ? "animate-pulse bg-green-400"
                    : "bg-zinc-600"
              }`}
            />
            <h3 className="font-semibold text-zinc-300">
              {sessionFlagged ? "Flagged" : proctoringActive ? "Proctoring" : "Inactive"}
            </h3>
          </div>
          {sessionFlagged && (
            <p className="mb-2 text-xs text-red-400">
              Session flagged due to violations.
            </p>
          )}
          {violations.length > 0 && (
            <div className="space-y-1 max-h-36 overflow-y-auto">
              {violations.slice(-5).map((v, i) => (
                <div key={i} className="rounded bg-red-900/20 px-2 py-1">
                  <p className="text-[10px] font-medium text-red-300 capitalize">
                    {v.violation_type.replace(/_/g, " ")}
                  </p>
                  <p className="text-[10px] text-zinc-500">{v.message}</p>
                </div>
              ))}
            </div>
          )}
          {violations.length === 0 && proctoringActive && (
            <p className="text-xs text-zinc-500">No violations detected.</p>
          )}
        </div>

        {/* Session info */}
        <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-3 text-sm">
          <h3 className="mb-2 font-semibold text-zinc-300">Session</h3>
          {sessionInfo ? (
            <dl className="space-y-1.5 text-xs">
              <div className="flex justify-between">
                <dt className="text-zinc-500">Phase</dt>
                <dd className="font-medium">{sessionInfo.phase}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-zinc-500">Difficulty</dt>
                <dd className="font-medium">{sessionInfo.difficulty_level}/5</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-zinc-500">Company</dt>
                <dd className="font-medium">{sessionInfo.company}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-zinc-500">Role</dt>
                <dd className="font-medium">{sessionInfo.role}</dd>
              </div>
            </dl>
          ) : (
            <p className="text-xs text-zinc-500">Loading...</p>
          )}
        </div>
      </div>
    </div>
  );
}
