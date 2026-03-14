"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  type SessionState,
  type SessionEnd,
  type StreamMeta,
  type CandidateProfile,
  type SentimentData,
  type InterviewReport,
  startInterviewStream,
  sendAudioStream,
  parseStreamHeaders,
  getSession,
  endInterview,
  uploadResume,
  getInterviewReport,
  downloadReportPDF,
} from "@/lib/api";
import { encodeWav } from "@/lib/wav";
import ReportPreview from "@/components/ReportPreview";

type Phase =
  | "idle"       // form
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
interface SentimentEntry extends SentimentData {
  timestamp: number; // Date.now()
}

const SILENCE_THRESHOLD = 0.01;
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
  const [report, setReport] = useState<InterviewReport | null>(null);
  const [loadingReport, setLoadingReport] = useState(false);
  const [downloadingPDF, setDownloadingPDF] = useState(false);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState("");
  const [audioDevices, setAudioDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedAudioDevice, setSelectedAudioDevice] = useState<string>("");

  // Proctoring state
  const [proctoringActive, setProctoringActive] = useState(false);
  const [sessionFlagged, setSessionFlagged] = useState(false);
  const [violations, setViolations] = useState<Violation[]>([]);
  const [cameraError, setCameraError] = useState("");

  // Sentiment state
  const [sentimentHistory, setSentimentHistory] = useState<SentimentEntry[]>([]);

  // Mic device selection
  const [micDeviceId, setMicDeviceId] = useState<string>("");
  const [micDevices, setMicDevices] = useState<MediaDeviceInfo[]>([]);

  const [startForm, setStartForm] = useState<{
    candidate_name: string;
    company: string;
    role: string;
    job_title: string;
    mode: "standard" | "option_a" | "option_b";
    user_id: string;
    jd_text: string;
  }>({
    candidate_name: "",
    company: "",
    role: "Software Engineer",
    job_title: "",
    mode: "standard",
    user_id: "",
    jd_text: "",
  });

  // Resume upload state
  const [uploading, setUploading] = useState(false);
  const [uploadedProfile, setUploadedProfile] = useState<CandidateProfile | null>(null);

  // Audio refs
  const audioCtxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
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

  useEffect(() => { phaseRef.current = phase; }, [phase]);
  useEffect(() => { sessionIdRef.current = sessionId; }, [sessionId]);

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
          audio.onended = () => { URL.revokeObjectURL(url); resolve(); };
          audio.onerror = () => { URL.revokeObjectURL(url); resolve(); };
          audio.play();
        } catch { resolve(); }
      }),
    []
  );

  /**
   * Play a streaming audio/mpeg response progressively using chunk batching.
   * Accumulates ~15 chunks into a batch, creates a Blob URL, and plays it.
   * Subsequent batches are queued and played sequentially via onended chaining.
   */
  const playStreamingAudio = useCallback(
    (response: Response): Promise<void> => {
      return new Promise(async (resolve) => {
        const reader = response.body?.getReader();
        if (!reader) { resolve(); return; }

        console.time("[Bodhi] time-to-first-audio");
        let firstBatchPlayed = false;


        const BATCH_SIZE = 25; // chunks per batch (~20KB)
        const audioQueue: HTMLAudioElement[] = [];
        let currentAudio: HTMLAudioElement | null = null;
        let streamDone = false;
        let resolved = false;

        const playNext = () => {
          if (resolved) return;
          if (audioQueue.length === 0) {
            if (streamDone) {
              console.log("[Bodhi] All audio batches played");
              resolved = true;
              resolve();
            }
            return;
          }

          currentAudio = audioQueue.shift()!;
          currentAudio.onended = () => {
            URL.revokeObjectURL(currentAudio!.src);
            playNext();
          };
          currentAudio.onerror = (e) => {
            console.error("[Bodhi] Batch audio error:", e);
            URL.revokeObjectURL(currentAudio!.src);
            playNext();
          };
          currentAudio.play().catch((err) => {
            console.error("[Bodhi] Batch play() rejected:", err);
            URL.revokeObjectURL(currentAudio!.src);
            playNext();
          });
        };

        let batch: Uint8Array[] = [];

        const flushBatch = () => {
          if (batch.length === 0) return;
          const blob = new Blob(batch as BlobPart[], { type: "audio/mpeg" });
          batch = [];

          // Preload the audio so it decodes in the background immediately
          const url = URL.createObjectURL(blob);
          const audio = new Audio(url);
          audio.preload = "auto";
          audio.load();

          if (!firstBatchPlayed) {
            firstBatchPlayed = true;
            console.timeEnd("[Bodhi] time-to-first-audio");
            console.log("[Bodhi] Playing first audio batch (%d KB)", Math.round(blob.size / 1024));
            
            currentAudio = audio;
            currentAudio.onended = () => {
              URL.revokeObjectURL(currentAudio!.src);
              playNext();
            };
            currentAudio.onerror = (e) => {
              console.error("[Bodhi] First batch error:", e);
              URL.revokeObjectURL(currentAudio!.src);
              playNext();
            };
            currentAudio.play().catch((err) => {
              console.error("[Bodhi] First batch play() rejected:", err);
              URL.revokeObjectURL(currentAudio!.src);
              playNext();
            });
          } else {
            // Queue the already-loading audio element
            audioQueue.push(audio);
            // If nothing is currently playing, start
            if (!currentAudio || currentAudio.ended) {
              playNext();

            }
          }
        };

        // Read stream and batch chunks
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            if (value) {
              batch.push(value as Uint8Array);
              if (batch.length >= BATCH_SIZE) {
                flushBatch();
              }
            }
          }
        } catch (err) {
          console.error("[Bodhi] Stream read error:", err);
        }

        // Flush remaining chunks
        streamDone = true;
        flushBatch();

        // If nothing played yet (very short response), resolve
        if (!firstBatchPlayed) {
          console.warn("[Bodhi] No audio batches to play");
          resolved = true;
          resolve();
        } else if (audioQueue.length === 0 && currentAudio && currentAudio.ended) {
          // Queue is empty and current audio already ended
          if (!resolved) {
            resolved = true;
            resolve();
          }
        }
      });
    },
    []
  );

  // ── Mic device enumeration ─────────────────────────────────────────────────

  const refreshMicDevices = useCallback(async () => {
    try {
      const all = await navigator.mediaDevices.enumerateDevices();
      const inputs = all.filter((d) => d.kind === "audioinput");
      setMicDevices(inputs);
      setMicDeviceId((prev) => prev || inputs[0]?.deviceId || "");
    } catch {}
  }, []);

  useEffect(() => {
    refreshMicDevices();
    navigator.mediaDevices.addEventListener("devicechange", refreshMicDevices);
    return () => navigator.mediaDevices.removeEventListener("devicechange", refreshMicDevices);
  }, [refreshMicDevices]);

  // ── Mic setup ──────────────────────────────────────────────────────────────

  const initMic = useCallback(async () => {
    let constraints: MediaStreamConstraints = {
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        sampleRate: 16000,
      },
    };
    
    // Support my explicit device selector OR the upstream micDeviceId
    const targetDeviceId = selectedAudioDevice || micDeviceId;
    if (targetDeviceId) {
      constraints.audio = {
        ...constraints.audio as MediaTrackConstraints,
        deviceId: { exact: targetDeviceId },
      };
    }

    const stream = await navigator.mediaDevices.getUserMedia(constraints);
    
    // Permission just granted — re-enumerate so device labels populate
    navigator.mediaDevices.enumerateDevices().then((all) => {
      const inputs = all.filter((d) => d.kind === "audioinput");
      setMicDevices(inputs);
      setAudioDevices(inputs); // keep both states in sync for now
    }).catch(() => {});
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
      samplesRef.current.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    };

    audioCtxRef.current = ctx;
    streamRef.current = stream;
    sourceRef.current = source;
    analyserRef.current = analyser;
    workletRef.current = processor;
  }, [micDeviceId]);

  const cleanupMic = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    workletRef.current?.disconnect();
    sourceRef.current?.disconnect();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    audioCtxRef.current?.close();
    audioCtxRef.current = null;
    streamRef.current = null;
    sourceRef.current = null;
    analyserRef.current = null;
    workletRef.current = null;
  }, []);

  // ── Camera setup ───────────────────────────────────────────────────────────

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
    if (frameIntervalRef.current) { clearInterval(frameIntervalRef.current); frameIntervalRef.current = null; }
    cameraStreamRef.current?.getTracks().forEach((t) => t.stop());
    cameraStreamRef.current = null;
  }, []);

  // ── Capture frame ──────────────────────────────────────────────────────────

  const captureFrame = useCallback((): string | null => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) return null;
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.8).split(",")[1];
  }, []);

  // ── Proctoring WebSocket ───────────────────────────────────────────────────

  const connectProctoringWs = useCallback(
    (sid: string) => {
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const wsBase = apiBase.replace(/^http/, "ws");
      const ws = new WebSocket(`${wsBase}/api/proctoring/ws/${sid}`);
      proctoringWsRef.current = ws;

      ws.onopen = () => {
        setProctoringActive(true);
        frameIntervalRef.current = setInterval(() => {
          if (proctoringWsRef.current?.readyState !== WebSocket.OPEN) return;
          const frame = captureFrame();
          if (!frame) return;
          frameCounterRef.current += 1;
          proctoringWsRef.current.send(
            JSON.stringify({ type: "frame", frame_id: `frame-${frameCounterRef.current}`, frame })
          );
        }, FRAME_INTERVAL_MS);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "frame_result") {
            if (msg.has_violations && msg.violations?.length > 0)
              setViolations((prev) => [...prev, ...msg.violations].slice(-20));
            if (msg.session_flagged) setSessionFlagged(true);
          } else if (msg.type === "session_flagged") {
            setSessionFlagged(true);
          }
        } catch { /* ignore */ }
      };

      ws.onerror = () => setCameraError("Proctoring connection error.");
      ws.onclose = () => setProctoringActive(false);
    },
    [captureFrame]
  );

  const endProctoringSession = useCallback(() => {
    if (frameIntervalRef.current) { clearInterval(frameIntervalRef.current); frameIntervalRef.current = null; }
    const ws = proctoringWsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "end_session" }));
      ws.close();
    }
    proctoringWsRef.current = null;
  }, []);

  // ── VAD loop ───────────────────────────────────────────────────────────────

  const startListening = useCallback(() => {
    if (audioCtxRef.current?.state === "suspended") {
      audioCtxRef.current.resume().catch(console.warn);
    }

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
      if (phaseRef.current !== "listening" && phaseRef.current !== "recording") return;
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
        } else { speechFramesRef.current = 0; }
      } else if (phaseRef.current === "recording") {
        if (!isSpeech) {
          if (silenceStartRef.current === 0) silenceStartRef.current = now;
          else if (now - silenceStartRef.current >= SILENCE_DURATION_MS && now - recordStartRef.current >= MIN_RECORD_MS) {
            isRecordingRef.current = false;
            finishRecording();
            return;
          }
        } else { silenceStartRef.current = 0; }
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  // ── Finish recording & send ────────────────────────────────────────────────

  const finishRecording = useCallback(async () => {
    setPhase("processing");
    phaseRef.current = "processing";
    setLevel(0);

    const chunks = samplesRef.current;
    if (chunks.length === 0) { startListening(); return; }

    const totalLen = chunks.reduce((a, c) => a + c.length, 0);
    const merged = new Float32Array(totalLen);
    let offset = 0;
    for (const c of chunks) { merged.set(c, offset); offset += c.length; }
    samplesRef.current = [];

    const ctx = audioCtxRef.current;
    const wavBlob = encodeWav(merged, ctx?.sampleRate ?? 16000);

    try {
      // Capture a webcam frame for posture analysis (best-effort — null if camera unavailable)
      const frameBlob = await new Promise<Blob | undefined>((resolve) => {
        const video = videoRef.current;
        const canvas = canvasRef.current;
        if (!canvas || !video || video.readyState < 2) { resolve(undefined); return; }
        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 480;
        canvas.getContext("2d")?.drawImage(video, 0, 0, canvas.width, canvas.height);
        canvas.toBlob((b) => resolve(b ?? undefined), "image/jpeg", 0.8);
      });

      const res = await sendAudioStream(sessionIdRef.current, wavBlob, "recording.wav", frameBlob);
      if (!res.ok) throw new Error(`${res.status}: ${await res.text().catch(() => res.statusText)}`);

      const meta: StreamMeta = parseStreamHeaders(res);
      if (meta.transcript) setTranscript((prev) => [...prev, { speaker: "user", text: meta.transcript! }]);
      if (meta.text) setTranscript((prev) => [...prev, { speaker: "bodhi", text: meta.text!, phase: meta.phase }]);
      if (meta.sentiment) setSentimentHistory((prev) => [...prev, { ...meta.sentiment!, timestamp: Date.now() }].slice(-20));
      scrollDown();

      setPhase("speaking");
      phaseRef.current = "speaking";
      await playStreamingAudio(res);

      if (meta.shouldEnd) {
        setPhase("ended");
        endProctoringSession();
        phaseRef.current = "ended";
        try { const end = await endInterview(sessionIdRef.current); setSummary(end); } catch {}
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
    try { const info = await getSession(sessionIdRef.current); setSessionInfo(info); } catch {}
  };

  // ── Form submit → start interview directly ─────────────────────────────────

  const handleFormSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setPhase("processing");
    phaseRef.current = "processing";

    try {
      await Promise.all([initCamera(), initMic()]);

      const res = await startInterviewStream(startForm);
      if (!res.ok) throw new Error(`${res.status}: ${await res.text().catch(() => res.statusText)}`);

      const meta: StreamMeta = parseStreamHeaders(res);
      if (meta.session) { setSessionId(meta.session); sessionIdRef.current = meta.session; }
      if (meta.text) setTranscript([{ speaker: "bodhi", text: meta.text, phase: "intro" }]);

      if (meta.session) connectProctoringWs(meta.session);

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
      
      // Load the report
      setLoadingReport(true);
      try {
        const reportData = await getInterviewReport(sessionIdRef.current);
        setReport(reportData);
      } catch (err) {
        console.error("Failed to load report:", err);
      } finally {
        setLoadingReport(false);
      }
    } catch (err) {
      setError(String(err));
    }
    cleanupMic();
    cleanupCamera();
  };

  const handleDownloadPDF = async () => {
    if (!sessionIdRef.current) return;
    setDownloadingPDF(true);
    try {
      await downloadReportPDF(sessionIdRef.current);
    } catch (err) {
      setError(String(err));
    } finally {
      setDownloadingPDF(false);
    }
  };

  // ── Resume upload ──────────────────────────────────────────────────────────

  const handleResumeUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      const result = await uploadResume(file);
      setUploadedProfile(result.profile);
      setStartForm((prev) => ({ ...prev, user_id: result.user_id, candidate_name: result.profile.name || prev.candidate_name }));
    } catch (err) { setError(String(err)); }
    finally { setUploading(false); }
  };

  // ── URL params ─────────────────────────────────────────────────────────────

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const mode = params.get("mode") as "option_a" | "option_b" | null;
    const userId = params.get("user_id");
    if (mode && userId) setStartForm((prev) => ({ ...prev, mode, user_id: userId }));
  }, []);

  // ── Cleanup ────────────────────────────────────────────────────────────────

  useEffect(() => {
    return () => {
      cancelAnimationFrame(rafRef.current);
      cleanupMic();
      cleanupCamera();
      endProctoringSession();
    };
  }, [cleanupMic, cleanupCamera, endProctoringSession]);

  // ── Render ─────────────────────────────────────────────────────────────────

  const inputCls =
    "rounded border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm w-full";

  // ── Idle: setup form ───────────────────────────────────────────────────────
  if (phase === "idle") {
    return (
      <div className="mx-auto max-w-lg space-y-6 pt-12">
        <h1 className="text-center text-2xl font-bold">Mock Interview</h1>
        <p className="text-center text-sm text-zinc-400">
          Hands-free voice conversation. Speak naturally — Bodhi listens, responds, and loops.
        </p>
        {error && (
          <div className="rounded border border-red-800 bg-red-900/30 px-4 py-2 text-sm text-red-300">{error}</div>
        )}
        <form onSubmit={handleFormSubmit} className="space-y-3 rounded-lg border border-[var(--border)] bg-[var(--card)] p-5">
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Interview Mode</label>
            <select
              value={startForm.mode}
              onChange={(e) => { setStartForm({ ...startForm, mode: e.target.value as "standard" | "option_a" | "option_b" }); setUploadedProfile(null); setError(""); }}
              className={inputCls}
            >
              <option value="standard">Standard (Company-based)</option>
              <option value="option_a">Resume-Based</option>
              <option value="option_b">JD-Targeted</option>
            </select>
          </div>

          {startForm.mode !== "standard" && !startForm.user_id && (
            <div className="space-y-2">
              <label className="block text-xs text-zinc-400">Upload Your Resume (PDF or DOCX)</label>
              <input type="file" accept=".pdf,.docx" onChange={handleResumeUpload} disabled={uploading}
                className="w-full rounded border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm file:mr-4 file:rounded file:border-0 file:bg-white file:px-3 file:py-1 file:text-xs file:font-medium file:text-black hover:file:bg-zinc-200 disabled:opacity-50"
              />
              {uploading && <p className="text-xs text-zinc-400">Uploading and parsing resume...</p>}
            </div>
          )}

          {startForm.mode !== "standard" && uploadedProfile && (
            <div className="rounded border border-green-700 bg-green-900/20 p-3 space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium text-green-300">✓ Resume Uploaded</p>
                <button type="button" onClick={() => { setUploadedProfile(null); setStartForm((p) => ({ ...p, user_id: "" })); }}
                  className="text-xs text-zinc-400 hover:text-white">Change</button>
              </div>
              <div className="text-xs text-zinc-300">
                <p className="font-medium">{uploadedProfile.name}</p>
                {uploadedProfile.email && <p className="text-zinc-400">{uploadedProfile.email}</p>}
                {uploadedProfile.skills.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {uploadedProfile.skills.slice(0, 5).map((s, i) => (
                      <span key={i} className="rounded bg-white/10 px-1.5 py-0.5 text-[10px]">{s}</span>
                    ))}
                    {uploadedProfile.skills.length > 5 && <span className="text-[10px] text-zinc-500">+{uploadedProfile.skills.length - 5} more</span>}
                  </div>
                )}
              </div>
            </div>
          )}

          <input placeholder="Your name" value={startForm.candidate_name}
            onChange={(e) => setStartForm({ ...startForm, candidate_name: e.target.value })} className={inputCls} />

          {startForm.mode === "standard" && (
            <>
              <input placeholder="Company" value={startForm.company}
                onChange={(e) => setStartForm({ ...startForm, company: e.target.value })} className={inputCls} />
              <input placeholder="Job Title" value={startForm.job_title}
                onChange={(e) => setStartForm({ ...startForm, job_title: e.target.value })} className={inputCls} />
            </>
          )}

          <button type="submit"
            className="w-full rounded border border-white py-2.5 text-sm font-medium text-white transition hover:bg-white hover:text-black">
            Start Interview →
          </button>
        </form>
      </div>
    );
  }

  // ── Active interview ───────────────────────────────────────────────────────
  return (
    <div className="flex h-[calc(100vh-80px)] gap-4">
      <canvas ref={canvasRef} className="hidden" />

      {/* Main area */}
      <div className="flex flex-1 flex-col">
        <div className="mb-3 flex items-center justify-between">
          <h1 className="text-xl font-bold">Interview</h1>
          <div className="flex items-center gap-3">
            <span className="text-xs text-zinc-500">{sessionId}</span>
            {phase !== "ended" && (
              <button onClick={handleEnd}
                className="rounded bg-red-600 px-3 py-1 text-xs font-medium text-white hover:bg-red-500">
                End Interview
              </button>
            )}
          </div>
        </div>

        {error && (
          <div className="mb-2 rounded border border-red-800 bg-red-900/30 px-3 py-1.5 text-xs text-red-300">{error}</div>
        )}

        <div className="mb-3 flex items-center gap-3">
          <div className={`h-3 w-3 rounded-full transition-all ${
            phase === "listening" ? "animate-pulse bg-green-400"
            : phase === "recording" ? "bg-red-500"
            : phase === "processing" ? "animate-pulse bg-yellow-400"
            : phase === "speaking" ? "animate-pulse bg-blue-400"
            : "bg-zinc-600"}`}
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
                <div key={i} className="w-1 rounded-sm bg-white transition-all"
                  style={{ height: `${Math.min(100, Math.max(8, level * 3000 * (1 + Math.random() * 0.3)))}%`, opacity: level > SILENCE_THRESHOLD ? 1 : 0.3 }} />
              ))}
            </div>
          )}
          {phase === "recording" && (
            <button
              onClick={() => {
                cancelAnimationFrame(rafRef.current);
                isRecordingRef.current = false;
                finishRecording();
              }}
              className="ml-auto rounded border border-zinc-600 px-3 py-1 text-xs text-zinc-300 hover:border-white hover:text-white transition">
              Submit ↵
            </button>
          )}
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto rounded-lg border border-[var(--border)] bg-[var(--card)] p-5">
          {transcript.map((t, i) => (
            <div key={i} className="flex gap-3">
              <div className={`mt-0.5 h-7 w-7 shrink-0 rounded-full flex items-center justify-center text-xs font-bold ${
                t.speaker === "bodhi" ? "bg-white text-black" : "bg-zinc-700 text-zinc-300"}`}>
                {t.speaker === "bodhi" ? "B" : "U"}
              </div>
              <div className="flex-1">
                {t.phase && <span className="mb-0.5 inline-block rounded bg-white/5 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-zinc-500">{t.phase}</span>}
                <p className="text-sm leading-relaxed text-zinc-200 whitespace-pre-wrap">{t.text}</p>
              </div>
            </div>
          ))}
          {phase === "processing" && (
            <div className="flex gap-3">
              <div className="mt-0.5 h-7 w-7 shrink-0 rounded-full flex items-center justify-center text-xs font-bold bg-white text-black">B</div>
              <p className="text-sm text-zinc-500 animate-pulse">Thinking...</p>
            </div>
          )}
          <div ref={transcriptEndRef} />
        </div>

        {summary && !report && !loadingReport && (
          <div className="mt-3 rounded-lg border border-green-700 bg-green-900/30 p-4 text-sm">
            <h3 className="mb-1 font-semibold text-green-300">Interview Complete</h3>
            <p className="text-zinc-300">{summary.summary}</p>
            {summary.overall_score != null && <p className="mt-1 text-zinc-400">Score: {summary.overall_score.toFixed(2)}</p>}
          </div>
        )}

        {loadingReport && (
          <div className="mt-3 rounded-lg border border-blue-700 bg-blue-900/30 p-4 text-sm text-center">
            <p className="text-blue-300">Generating comprehensive report...</p>
          </div>
        )}

        {report && (
          <div className="mt-3">
            <ReportPreview report={report} onDownloadPDF={handleDownloadPDF} downloading={downloadingPDF} />
          </div>
        )}
      </div>

      {/* Sidebar */}
      <div className="hidden w-52 shrink-0 space-y-3 lg:block">
        {/* Camera preview */}
        <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] overflow-hidden">
          <video ref={videoRef} muted playsInline className="w-full rounded-lg" style={{ transform: "scaleX(-1)" }} />
          {cameraError && <p className="px-3 py-2 text-xs text-zinc-500">{cameraError}</p>}
        </div>

        {/* Sentiment / Tone */}
        {sentimentHistory.length > 0 && (() => {
          const latest = sentimentHistory[sentimentHistory.length - 1];

          const emotionColor: Record<string, string> = {
            confident: "text-green-400", enthusiastic: "text-blue-400",
            neutral: "text-zinc-400", hesitant: "text-amber-400", nervous: "text-orange-400",
            joy: "text-green-400", fear: "text-orange-400", anger: "text-red-400",
            sadness: "text-blue-300", disgust: "text-purple-400", surprise: "text-cyan-400",
          };
          const dotColor: Record<string, string> = {
            confident: "bg-green-400", enthusiastic: "bg-blue-400",
            neutral: "bg-zinc-500", hesitant: "bg-amber-400", nervous: "bg-orange-400",
          };
          const sentimentBadge: Record<string, string> = {
            positive: "text-green-400", neutral: "text-zinc-400", negative: "text-red-400",
          };
          const postureColor: Record<string, string> = {
            upright: "text-green-400", slouching: "text-amber-400",
            leaning_away: "text-orange-400", looking_away: "text-red-400",
            face_not_visible: "text-zinc-500",
          };

          // Use HF emotion if available, fall back to rule-based
          const displayEmotion = latest.hf_emotion ?? latest.emotion;

          return (
            <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-3 text-xs">
              <h3 className="mb-2 text-xs font-semibold text-zinc-300">Tone Analysis</h3>

              {/* Primary emotion */}
              <div className="flex items-center justify-between mb-1">
                <span className="text-zinc-500">Emotion</span>
                <span className={`font-semibold capitalize ${emotionColor[displayEmotion] ?? "text-zinc-400"}`}>
                  {displayEmotion}
                  {latest.hf_confidence != null && (
                    <span className="ml-1 text-[9px] text-zinc-500">
                      {Math.round(latest.hf_confidence * 100)}%
                    </span>
                  )}
                </span>
              </div>

              {/* Sentiment polarity */}
              {latest.sentiment && (
                <div className="flex items-center justify-between mb-1">
                  <span className="text-zinc-500">Sentiment</span>
                  <span className={`font-medium capitalize ${sentimentBadge[latest.sentiment] ?? "text-zinc-400"}`}>
                    {latest.sentiment}
                  </span>
                </div>
              )}

              {/* Confidence score */}
              {latest.confidence_score != null && (
                <div className="flex items-center justify-between mb-2">
                  <span className="text-zinc-500">Confidence</span>
                  <span className={`font-medium ${
                    latest.confidence_score >= 60 ? "text-green-400"
                    : latest.confidence_score >= 40 ? "text-amber-400"
                    : "text-red-400"}`}>
                    {latest.confidence_score}/100
                  </span>
                </div>
              )}

              {/* Trend dots (last 8 turns) */}
              {sentimentHistory.length > 1 && (
                <div className="flex items-center gap-1 mb-2">
                  {sentimentHistory.slice(-8).map((s, i) => (
                    <div key={i} title={s.hf_emotion ?? s.emotion}
                      className={`h-2 w-2 rounded-full ${dotColor[s.emotion] ?? "bg-zinc-500"}`} />
                  ))}
                </div>
              )}

              {/* Behavioral flags */}
              {latest.flags && latest.flags.length > 0 && (
                <div className="flex flex-wrap gap-1 mb-2">
                  {latest.flags.map((f) => (
                    <span key={f}
                      className={`rounded px-1 py-0.5 text-[9px] font-medium capitalize ${
                        f === "confident" ? "bg-green-900/40 text-green-400"
                        : f === "nervous" || f === "distressed" ? "bg-red-900/40 text-red-400"
                        : "bg-zinc-800 text-zinc-400"}`}>
                      {f}
                    </span>
                  ))}
                </div>
              )}

              {/* Audio metrics */}
              <dl className="space-y-1 text-[10px] text-zinc-500">
                {latest.speaking_rate_wpm > 0 && (
                  <div className="flex justify-between">
                    <dt>Speaking rate</dt>
                    <dd className="text-zinc-300">{latest.speaking_rate_wpm} wpm</dd>
                  </div>
                )}
                <div className="flex justify-between">
                  <dt>Filler words</dt>
                  <dd className={latest.filler_rate > 8 ? "text-amber-400" : "text-zinc-300"}>
                    {latest.filler_rate.toFixed(1)}%
                  </dd>
                </div>
                {latest.hedge_count > 0 && (
                  <div className="flex justify-between">
                    <dt>Hedging</dt>
                    <dd className="text-zinc-300">{latest.hedge_count}</dd>
                  </div>
                )}
                <div className="flex justify-between">
                  <dt>Voice energy</dt>
                  <dd className="text-zinc-300 capitalize">{latest.energy_level}</dd>
                </div>
              </dl>

              {/* Posture (only when frame was sent and analyzed) */}
              {latest.posture && (
                <div className="mt-2 pt-2 border-t border-[var(--border)] space-y-1 text-[10px]">
                  <div className="flex items-center justify-between">
                    <span className="text-zinc-500">Posture</span>
                    <span className={`font-medium capitalize ${postureColor[latest.posture] ?? "text-zinc-400"}`}>
                      {latest.posture.replace(/_/g, " ")}
                    </span>
                  </div>
                  {latest.gaze_direction && (
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Gaze</span>
                      <span className={`text-zinc-300 capitalize ${latest.gaze_direction !== "center" ? "text-amber-400" : ""}`}>
                        {latest.gaze_direction}
                      </span>
                    </div>
                  )}
                  {latest.spine_score != null && (
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Spine</span>
                      <span className={latest.spine_score >= 70 ? "text-green-400" : "text-amber-400"}>
                        {latest.spine_score}/100
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })()}

        {/* Proctoring status */}
        <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-3 text-sm">
          <div className="mb-2 flex items-center gap-2">
            <div className={`h-2 w-2 rounded-full ${
              sessionFlagged ? "bg-red-500" : proctoringActive ? "animate-pulse bg-green-400" : "bg-zinc-600"}`} />
            <h3 className="font-semibold text-zinc-300">
              {sessionFlagged ? "Flagged" : proctoringActive ? "Proctoring" : "Inactive"}
            </h3>
          </div>
          {sessionFlagged && <p className="mb-2 text-xs text-red-400">Session flagged due to violations.</p>}
          {violations.length > 0 && (
            <div className="space-y-1 max-h-36 overflow-y-auto">
              {violations.slice(-5).map((v, i) => (
                <div key={i} className="rounded bg-red-900/20 px-2 py-1">
                  <p className="text-[10px] font-medium text-red-300 capitalize">{v.violation_type.replace(/_/g, " ")}</p>
                  <p className="text-[10px] text-zinc-500">{v.message}</p>
                </div>
              ))}
            </div>
          )}
          {violations.length === 0 && proctoringActive && <p className="text-xs text-zinc-500">No violations detected.</p>}
        </div>

        {/* Session info */}
        <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-3 text-sm">
          <h3 className="mb-2 font-semibold text-zinc-300">Session</h3>
          {sessionInfo ? (
            <dl className="space-y-1.5 text-xs">
              <div className="flex justify-between"><dt className="text-zinc-500">Phase</dt><dd className="font-medium">{sessionInfo.phase}</dd></div>
              <div className="flex justify-between"><dt className="text-zinc-500">Difficulty</dt><dd className="font-medium">{sessionInfo.difficulty_level}/5</dd></div>
              <div className="flex justify-between"><dt className="text-zinc-500">Company</dt><dd className="font-medium">{sessionInfo.company}</dd></div>
              <div className="flex justify-between"><dt className="text-zinc-500">Role</dt><dd className="font-medium">{sessionInfo.role}</dd></div>
            </dl>
          ) : (
            <p className="text-xs text-zinc-500">Loading...</p>
          )}
        </div>
      </div>
    </div>
  );
}
