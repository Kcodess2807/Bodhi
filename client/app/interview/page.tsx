"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import Navbar from "@/components/Navbar"
import { PageHeader } from "@/components/ui/page-header"
import { InterviewSetupForm, type InterviewFormData } from "@/components/interview/InterviewSetupForm"
import { InterviewSessionView } from "@/components/interview/InterviewSessionView"
import { InterviewSummary } from "@/components/interview/InterviewSummary"
import { useInterviewAudio } from "@/hooks/useInterviewAudio"
import { useProctoring } from "@/hooks/useProctoring"
import { useSentimentAnalysis } from "@/hooks/useSentimentAnalysis"
import {
  type SessionState,
  type SessionEnd,
  type StreamMeta,
  type InterviewReport,
  startInterviewStream,
  sendAudioStream,
  parseStreamHeaders,
  getSession,
  endInterview,
  downloadReportPDF,
} from "@/lib/api";
import ReportPreview from "@/components/ReportPreview";

type Phase = "idle" | "listening" | "recording" | "processing" | "speaking" | "ended"

interface Turn {
  speaker: "user" | "bodhi"
  text: string
  phase?: string
}

const SILENCE_THRESHOLD = 0.015

export default function InterviewPage() {
  const router = useRouter()
  const [sessionId, setSessionId] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [transcript, setTranscript] = useState<Turn[]>([]);
  const [sessionInfo, setSessionInfo] = useState<SessionState | null>(null);
  const [summary, setSummary] = useState<SessionEnd | null>(null);
  const [report, setReport] = useState<InterviewReport | null>(null);
  const [loadingReport, setLoadingReport] = useState(false);
  const [downloadingPDF, setDownloadingPDF] = useState(false);
  const [error, setError] = useState("");
  const [formData, setFormData] = useState<InterviewFormData | null>(null)
  const [demoMode, setDemoMode] = useState(false)
  const [demoPhase, setDemoPhase] = useState("")

  // Refs
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const phaseRef = useRef<Phase>("idle")
  const sessionIdRef = useRef("")

  // Custom hooks
  const audio = useInterviewAudio()
  const proctoring = useProctoring(videoRef, canvasRef)
  const sentiment = useSentimentAnalysis()

  useEffect(() => {
    phaseRef.current = phase
  }, [phase])

  useEffect(() => {
    sessionIdRef.current = sessionId
  }, [sessionId])

  // Re-attach camera stream to video element after phase transition
  // When phase changes from "idle" to an active state, the grid layout
  // (with ProctoringPanel containing <video ref={videoRef}>) mounts.
  // The camera stream was already obtained by initCamera() but the
  // <video> element was not yet in the DOM, so we need to re-apply it.
  useEffect(() => {
    if (phase !== "idle" && phase !== "ended") {
      // Small delay to ensure React has committed the DOM update
      const timer = setTimeout(() => {
        proctoring.reattachStream()
      }, 100)
      return () => clearTimeout(timer)
    }
  }, [phase, proctoring])

  // URL params - auto-start if present
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const mode = params.get("mode") as "option_a" | "option_b" | null
    const userId = params.get("user_id")
    const isDemoMode = params.get("demo") === "true"
    const phase = params.get("phase")
    
    if (isDemoMode && phase) {
      // Set demo mode state
      setDemoMode(true)
      setDemoPhase(phase)
      
      // Auto-start demo mode
      setFormData({
        candidate_name: "Demo User",
        company: "GrowthX",
        role: "Software Engineer",
        mode: "standard",
        user_id: "",
        jd_text: "",
        interviewer_persona: "bodhi",
      })
      // Trigger form submit with demo params
      setTimeout(() => {
        handleFormSubmit({
          candidate_name: "Demo User",
          company: "GrowthX",
          role: "Software Engineer",
          mode: "standard",
          user_id: "",
          jd_text: "",
          interviewer_persona: "bodhi",
        }, true, phase)
      }, 100)
    } else if (mode && userId) {
      setFormData((prev) => ({
        ...(prev || {
          candidate_name: "",
          company: "",
          role: "Software Engineer",
          mode: "standard",
          user_id: "",
          jd_text: "",
          interviewer_persona: "bodhi",
        }),
        mode,
        user_id: userId,
      }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const refreshSession = useCallback(async () => {
    try {
      const info = await getSession(sessionIdRef.current)
      setSessionInfo(info)
    } catch { }
  }, [])

  const finishRecording = useCallback(async () => {
    setPhase("processing")
    phaseRef.current = "processing"
    audio.setLevel(0)

    const wavBlob = audio.getRecordedAudio()
    if (!wavBlob) {
      audio.startListening(() => setPhase("listening"), () => setPhase("recording"), finishRecording)
      return
    }

    try {
      const res = await sendAudioStream(sessionIdRef.current, wavBlob, "recording.wav")
      if (!res.ok) throw new Error(`${res.status}: ${await res.text().catch(() => res.statusText)}`)

      const meta: StreamMeta = parseStreamHeaders(res)

      // Update sentiment data from streaming response headers
      if (meta.sentiment) {
        sentiment.updateFromMeta(meta)
      }

      if (meta.transcript) setTranscript((prev) => [...prev, { speaker: "user", text: meta.transcript! }])
      if (meta.text) setTranscript((prev) => [...prev, { speaker: "bodhi", text: meta.text!, phase: meta.phase }])

      setPhase("speaking")
      phaseRef.current = "speaking"
      await audio.playStreamingAudio(res)

      if (meta.shouldEnd) {
        setPhase("ended")
        proctoring.endSession()
        phaseRef.current = "ended"
        try {
          await endInterview(sessionIdRef.current)
        } catch { }
        audio.cleanup()
        proctoring.cleanupCamera()
        router.push(`/report/${sessionIdRef.current}`)
        sentiment.reset()
        return
      }

      refreshSession()
      audio.startListening(() => setPhase("listening"), () => setPhase("recording"), finishRecording)
    } catch (err) {
      setError(String(err))
      audio.startListening(() => setPhase("listening"), () => setPhase("recording"), finishRecording)
    }
  }, [audio, proctoring, refreshSession, sentiment, router])

  const handleFormSubmit = async (data: InterviewFormData, isDemoMode = false, demoPhase = "") => {
    setFormData(data)
    setError("")
    setPhase("processing")
    try {
      await proctoring.initCamera()
      await audio.initMic()
      // Pass interviewer_persona so backend uses the chosen voice/prompt
      const res = await startInterviewStream({
        ...data,
        interviewer_persona: data.interviewer_persona ?? "bodhi",
        demo_mode: isDemoMode,
        demo_phase: demoPhase,
      })
      if (!res.ok) throw new Error(`${res.status}: ${await res.text().catch(() => res.statusText)}`)

      const meta: StreamMeta = parseStreamHeaders(res)
      if (meta.session) setSessionId(meta.session)
      if (meta.text) setTranscript([{ speaker: "bodhi", text: meta.text, phase: isDemoMode ? demoPhase : "intro" }])

      if (meta.session) {
        proctoring.connectWebSocket(meta.session, "")
      }

      setPhase("speaking")
      await audio.playStreamingAudio(res)
      refreshSession()
      audio.startListening(() => setPhase("listening"), () => setPhase("recording"), finishRecording)
    } catch (err) {
      setError(String(err))
      setPhase("idle")
    }
  }

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

  const handleEnd = async () => {
    audio.stopListening()
    setPhase("processing")
    proctoring.endSession()
    sentiment.reset()
    try {
      await endInterview(sessionIdRef.current)
    } catch (err) {
      setError(String(err))
    }
    audio.cleanup()
    proctoring.cleanupCamera()
    router.push(`/report/${sessionIdRef.current}`)
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      audio.cleanup()
      proctoring.cleanupCamera()
      proctoring.endSession()
      sentiment.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Render: Setup Form ──────────────────────────────────
  if (phase === "idle") {
    return (
      <div className="min-h-screen bg-[#F7F5F3]">
        <Navbar />
        <div className="mx-auto max-w-lg space-y-6 pt-28 px-4 pb-12">
          <div className="flex items-center justify-between">
            <PageHeader
              title={demoMode ? `Demo: ${demoPhase.charAt(0).toUpperCase() + demoPhase.slice(1)} Phase` : "Mock Interview"}
              description={demoMode ? `Testing ${demoPhase} questions with GrowthX context` : "Hands-free voice conversation. Speak naturally — your interviewer listens, responds, and loops."}
            />
            {demoMode && (
              <span className="rounded-full bg-blue-100 px-3 py-1 text-xs font-medium text-blue-700">
                DEMO MODE
              </span>
            )}
          </div>
          {error && (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 animate-fade-in-up">
              {error}
            </div>
          )}
          <div className="rounded-2xl border border-[rgba(55,50,47,0.10)] bg-white p-6 shadow-[0px_2px_8px_rgba(55,50,47,0.06)] animate-fade-in-up">
            <InterviewSetupForm onSubmit={handleFormSubmit} loading={phase !== "idle"} />
          </div>
        </div>
      </div>
    )
  }

  // ── Render: Active Interview - Show summary if ended, otherwise show session view
  if (phase === "ended" && summary) {
    return (
      <div className="min-h-screen bg-background">
        <Navbar />
        <div className="pt-24 pb-8 px-4 sm:px-6 max-w-7xl mx-auto">
          <InterviewSummary summary={summary} />
        </div>
      </div>
    )
  }

  // Render: Active Interview Session (no navbar, full screen)
  return (
    <>
      <canvas ref={canvasRef} className="hidden" />
      <InterviewSessionView
        sessionId={sessionId}
        videoRef={videoRef}
        transcript={transcript}
        phase={phase}
        onEndSession={handleEnd}
        proctoringActive={proctoring.proctoringActive}
        sessionFlagged={proctoring.sessionFlagged}
        cameraError={proctoring.cameraError}
        sentimentData={sentiment.sentimentData}
        violationCount={proctoring.violations.length}
        interviewerPersona={formData?.interviewer_persona ?? "bodhi"}
      />
    </>
  )
}