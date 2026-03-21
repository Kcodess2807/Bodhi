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
  prepareInterview,
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
  const [interviewPhase, setInterviewPhase] = useState<string>("intro");
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
  const [editorContent, setEditorContent] = useState("")

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
  // (with video ref) mounts.
  // The camera stream was already obtained by initCamera() but the
  // <video> element was not yet in the DOM, so we need to re-apply it.
  useEffect(() => {
    if (phase !== "idle" && phase !== "ended" && proctoring.cameraAvailable) {
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
    const rawMode = params.get("mode")
    // Map legacy mode values to new system
    const mode = rawMode === "option_a" || rawMode === "resume" ? "option_a" : null
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
        experience_level: "Mid-Level",
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
          experience_level: "Mid-Level",
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
          experience_level: "Mid-Level",
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
      audio.startListening(() => setPhase("listening"), () => setPhase("recording"), () => finishRecording())
      return
    }

    try {
      audio.sendAudioWs(wavBlob)
      // Phase transitions are handled by WebSocket callbacks (onTranscript, onReplyComplete)
    } catch (err) {
      setError(String(err))
      audio.startListening(() => setPhase("listening"), () => setPhase("recording"), () => finishRecording())
    }
  }, [audio])

  const handleFormSubmit = async (data: InterviewFormData, isDemoMode = false, demoPhase = "") => {
    setFormData(data)
    setError("")
    setPhase("processing")
    try {
      // Init camera (may fail gracefully — interview continues without)
      const cameraOk = await proctoring.initCamera()
      await audio.initMic()
      
      const res = await prepareInterview({
        ...data,
        interviewer_persona: data.interviewer_persona ?? "bodhi",
        demo_mode: isDemoMode,
        demo_phase: demoPhase,
      } as any) // suppress TS type issue for demo props temporarily

      const sid = res.session_id
      setSessionId(sid)

      // Connect Proctoring WS only if camera is available
      if (cameraOk) {
        proctoring.connectWebSocket(sid, "")
      }

      // Connect Interview Audio & State WS
      audio.connectWebSocket(sid, {
        onGreetingStart: (text, sessionPhase) => {
           setTranscript([{ speaker: "bodhi", text, phase: isDemoMode ? demoPhase : sessionPhase }])
           setInterviewPhase(isDemoMode ? demoPhase : sessionPhase)
           refreshSession()
        },
        onGreetingComplete: (sessionPhase) => {
           // Phase transitions to speaking happen during onPlaybackStart now
        },
        onTranscript: (text) => {
           setTranscript((prev) => [...prev, { speaker: "user", text }])
        },
        onPartialReply: (chunk) => {
           setTranscript((prev) => {
             const newTranscript = [...prev]
             const last = newTranscript[newTranscript.length - 1]
             if (last && last.speaker === "bodhi") {
               // Clone the last turn before mutating to be strictly immutable
               newTranscript[newTranscript.length - 1] = {
                 ...last,
                 text: last.text + chunk
               }
               return newTranscript
             } else {
               return [...newTranscript, { speaker: "bodhi", text: chunk }]
             }
           })
        },
        onReplyComplete: (text, sessionPhase, shouldEnd) => {
           setTranscript((prev) => {
             const newTranscript = [...prev]
             const last = newTranscript[newTranscript.length - 1]
             if (last && last.speaker === "bodhi") {
               newTranscript[newTranscript.length - 1] = {
                 ...last,
                 text: text,
                 phase: sessionPhase
               }
               return newTranscript
             } else {
               return [...newTranscript, { speaker: "bodhi", text, phase: sessionPhase }]
             }
           })
           setInterviewPhase(sessionPhase)
           if (shouldEnd) {
               setPhase("ended")
               proctoring.endSession()
               audio.cleanup()
               proctoring.cleanupCamera()
               router.push(`/report/${sid}`)
               sentiment.reset()
           } else {
               refreshSession()
           }
        },
        onError: (err) => {
           setError(err)
           setPhase("idle")
        },
        onPlaybackStart: () => {
           setPhase("speaking")
        },
        onPlaybackComplete: () => {
           audio.startListening(
               () => setPhase("listening"),
               () => setPhase("recording"),
               finishRecording
           )
        }
      })

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
      <div className="min-h-screen bg-[#F7F5F3] relative overflow-hidden">
        {/* Animated Grid Background */}
        <div className="absolute inset-0 opacity-[0.03] pointer-events-none">
          <div
            className="absolute inset-0"
            style={{
              backgroundImage: `
                linear-gradient(to right, #37322F 1px, transparent 1px),
                linear-gradient(to bottom, #37322F 1px, transparent 1px)
              `,
              backgroundSize: "60px 60px",
            }}
          />
        </div>

        {/* Gradient Orbs */}
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-[#E8E3DF] rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-float" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-[#DED9D5] rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-float" style={{ animationDelay: "2s" }} />

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

  // ── Render: Initial Setup Loading ──────────────────────────────────
  if (phase === "processing" && transcript.length === 0) {
    return (
      <div className="min-h-screen bg-[#F7F5F3] flex items-center justify-center relative overflow-hidden">
        <div className="absolute inset-0 opacity-[0.03] pointer-events-none">
          <div
            className="absolute inset-0"
            style={{
              backgroundImage: `
                linear-gradient(to right, #37322F 1px, transparent 1px),
                linear-gradient(to bottom, #37322F 1px, transparent 1px)
              `,
              backgroundSize: "60px 60px",
            }}
          />
        </div>

        <div className="text-center space-y-6 px-4 z-10">
          <div className="flex justify-center">
            <div className="w-12 h-12 rounded-full border-4 border-[#37322F]/10 border-t-[#37322F] animate-spin" />
          </div>
          <div className="space-y-2">
            <h2 className="text-xl font-semibold text-[#37322F]">
              Loading expected environment...
            </h2>
            <p className="text-sm text-[rgba(55,50,47,0.6)]">
              {demoMode ? `Preparing ${demoPhase} demo` : "Initializing your session"}
            </p>
          </div>
        </div>
      </div>
    )
  }

  // ── Render: Active Interview - Show summary if ended, otherwise show session view
  if (phase === "ended" && summary) {
    return (
      <div className="min-h-screen bg-[#F7F5F3] relative overflow-hidden">
        {/* Animated Grid Background */}
        <div className="absolute inset-0 opacity-[0.03] pointer-events-none">
          <div
            className="absolute inset-0"
            style={{
              backgroundImage: `
                linear-gradient(to right, #37322F 1px, transparent 1px),
                linear-gradient(to bottom, #37322F 1px, transparent 1px)
              `,
              backgroundSize: "60px 60px",
            }}
          />
        </div>

        {/* Gradient Orbs */}
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-[#E8E3DF] rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-float" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-[#DED9D5] rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-float" style={{ animationDelay: "2s" }} />

        <Navbar />
        <div className="relative pt-24 pb-8 px-4 sm:px-6 max-w-7xl mx-auto">
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
        cameraAvailable={proctoring.cameraAvailable}
        sentimentData={sentiment.sentimentData}
        violationCount={proctoring.violations.length}
        interviewerPersona={formData?.interviewer_persona ?? "bodhi"}
        onEditorContentChange={setEditorContent}
        interviewPhase={interviewPhase}
      />
    </>
  )
}