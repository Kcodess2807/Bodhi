"use client"

import { useState, RefObject } from "react"
import { 
  Mic, 
  MicOff, 
  PhoneOff,
  AlertTriangle,
  Activity,
  Eye
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"

interface Turn {
  speaker: "user" | "bodhi"
  text: string
  phase?: string
}

interface SentimentData {
  emotion: string
  emotionConfidence: number
  sentiment: string
  speechRateWpm: number
  confidenceScore: number
  flags: string[]
}

interface InterviewSessionViewProps {
  sessionId: string
  videoRef: RefObject<HTMLVideoElement | null>
  transcript: Turn[]
  phase: string
  onEndSession: () => void
  proctoringActive: boolean
  sessionFlagged: boolean
  cameraError: string
  sentimentData?: SentimentData | null
  violationCount?: number
  interviewerPersona?: "bodhi" | "riya"
}

export function InterviewSessionView({
  videoRef,
  transcript,
  phase,
  onEndSession,
  proctoringActive,
  sessionFlagged,
  cameraError,
  sentimentData,
  violationCount = 0,
  interviewerPersona = "bodhi"
}: InterviewSessionViewProps) {
  const [isMicOn, setIsMicOn] = useState(true)
  const [editorContent, setEditorContent] = useState("")

  const currentTranscript = transcript[transcript.length - 1]

  const getPhaseText = () => {
    switch (phase) {
      case "listening": return "Listening..."
      case "recording": return "Recording"
      case "processing": return "Processing"
      case "speaking": return "AI Speaking"
      default: return "Active"
    }
  }

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-[#F7F5F3]">
      {/* Minimal Top Header */}
      <div className="border-b border-[rgba(55,50,47,0.10)] bg-white px-6 py-3 flex items-center justify-between shadow-[0px_2px_8px_rgba(55,50,47,0.06)]">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-[#2F3037] tracking-tight" style={{ fontFamily: "var(--font-inter), ui-sans-serif, sans-serif" }}>
            {interviewerPersona === "riya" ? "Riya" : "Bodhi"}
          </h1>
          <Badge className="text-xs bg-[rgba(55,50,47,0.08)] text-[#37322F] border-[rgba(55,50,47,0.12)] font-medium">
            {getPhaseText()}
          </Badge>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-sm font-medium text-[#37322F]">
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
            <span className="font-sans">45:00</span>
          </div>
          <Button 
            variant="outline" 
            size="sm" 
            onClick={onEndSession}
            className="text-[#DC2626] border-[#DC2626]/30 hover:bg-[#DC2626]/10 font-sans font-medium"
          >
            End Session
          </Button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar - Session Metrics */}
        <div className="w-[280px] border-r border-[rgba(55,50,47,0.10)] bg-white flex flex-col p-6 gap-6">
          <div>
            <h3 className="text-sm font-semibold text-[#37322F] mb-4 font-sans">Session Metrics</h3>
            
            {/* Proctoring Status */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs text-[rgba(55,50,47,0.6)] font-sans">Proctoring</span>
                <div className="flex items-center gap-2">
                  <div className={cn(
                    "h-2 w-2 rounded-full",
                    sessionFlagged ? "bg-red-500" : proctoringActive ? "bg-green-500 animate-pulse" : "bg-gray-400"
                  )} />
                  <span className="text-xs font-medium text-[#37322F] font-sans">
                    {sessionFlagged ? "Flagged" : proctoringActive ? "Active" : "Inactive"}
                  </span>
                </div>
              </div>

              {cameraError && (
                <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2">
                  <p className="text-xs text-red-700 font-sans">{cameraError}</p>
                </div>
              )}

              {sessionFlagged && (
                <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
                  <p className="text-xs text-red-700 font-sans">Session flagged due to violations</p>
                </div>
              )}
            </div>
          </div>

          {/* Attention Score */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-[rgba(55,50,47,0.6)] font-sans">Attention Score</span>
              <span className="text-sm font-semibold text-[#37322F] font-sans">85%</span>
            </div>
            <div className="w-full h-2 bg-[rgba(55,50,47,0.08)] rounded-full overflow-hidden">
              <div className="h-full bg-[#37322F] rounded-full" style={{ width: "85%" }} />
            </div>
          </div>

          {/* Sentiment Indicators */}
          <div>
            <h4 className="text-xs font-semibold text-[#37322F] mb-3 font-sans">Sentiment</h4>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-[rgba(55,50,47,0.6)] font-sans">Confidence</span>
                <span className="text-xs font-medium text-[#37322F] font-sans capitalize">
                  {sentimentData ? `${sentimentData.confidenceScore}%` : "—"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-[rgba(55,50,47,0.6)] font-sans">Emotion</span>
                <span className="text-xs font-medium text-[#37322F] font-sans capitalize">
                  {sentimentData?.emotion || "—"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-[rgba(55,50,47,0.6)] font-sans">Speech Rate</span>
                <span className="text-xs font-medium text-[#37322F] font-sans">
                  {sentimentData ? `${sentimentData.speechRateWpm} wpm` : "—"}
                </span>
              </div>
              {sentimentData?.flags && sentimentData.flags.length > 0 && (
                <div className="pt-2 border-t border-[rgba(55,50,47,0.08)]">
                  <div className="flex flex-wrap gap-1">
                    {sentimentData.flags.map((flag, i) => (
                      <span
                        key={i}
                        className="text-[10px] px-2 py-0.5 rounded-full bg-[rgba(55,50,47,0.08)] text-[#37322F] font-sans capitalize"
                      >
                        {flag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Violations Count */}
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-[rgba(55,50,47,0.6)] font-sans">Violations</span>
              <span className={cn(
                "text-sm font-semibold font-sans",
                violationCount > 0 ? "text-red-600" : "text-[#37322F]"
              )}>
                {violationCount}
              </span>
            </div>
          </div>
        </div>

        {/* Center Canvas/Editor - IDE Style (Light Mode) */}
        <div className="flex-1 relative bg-[#FFFFFF] flex flex-col">
          {/* IDE Toolbar */}
          <div className="h-10 bg-[#F7F5F3] border-b border-[rgba(55,50,47,0.12)] flex items-center px-4 gap-2">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-[#FF5F56]"></div>
              <div className="w-3 h-3 rounded-full bg-[#FFBD2E]"></div>
              <div className="w-3 h-3 rounded-full bg-[#27C93F]"></div>
            </div>
            <div className="flex-1 flex items-center gap-2 ml-4">
              <div className="px-3 py-1 bg-white rounded text-xs text-[#37322F] font-mono border border-[rgba(55,50,47,0.12)] shadow-sm">
                interview-notes.md
              </div>
            </div>
            <div className="flex items-center gap-2 text-[#37322F]">
              <button className="hover:bg-[rgba(55,50,47,0.06)] p-1 rounded transition-colors">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
            </div>
          </div>

          {/* IDE Editor Area */}
          <div className="flex-1 flex overflow-hidden">
            {/* Line Numbers */}
            <div className="w-12 bg-[#FAFAFA] border-r border-[rgba(55,50,47,0.10)] py-3 text-right pr-3 font-mono text-xs text-[rgba(55,50,47,0.4)] select-none">
              {Array.from({ length: 30 }, (_, i) => (
                <div key={i} className="leading-6">{i + 1}</div>
              ))}
            </div>

            {/* Editor Content */}
            <div className="flex-1 relative bg-white">
              <Textarea
                value={editorContent}
                onChange={(e) => setEditorContent(e.target.value)}
                placeholder="# Interview Notes

## Key Points
- 

## Questions Asked
- 

## My Responses
- 

## Follow-up Items
- "
                className="w-full h-full bg-transparent border-0 text-[#2F3037] placeholder:text-[rgba(55,50,47,0.35)] resize-none font-mono text-sm p-3 leading-6 focus:outline-none focus:ring-0"
                style={{ 
                  caretColor: '#37322F',
                  lineHeight: '1.5rem'
                }}
              />
            </div>
          </div>

          {/* Floating Live Captions - Above buttons */}
          <div className="absolute bottom-28 left-1/2 -translate-x-1/2 w-full max-w-2xl px-6 z-30">
            <div className="bg-black/80 backdrop-blur-md rounded-xl px-4 py-3 shadow-[0px_8px_24px_rgba(0,0,0,0.4)] border border-white/10">
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 shrink-0">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-white"></span>
                  </span>
                  <span className="text-xs font-medium text-white/60 font-sans">Live</span>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-white font-sans">
                    {currentTranscript?.text || "Waiting for audio..."}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Bottom Action Buttons */}
          <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex items-center gap-4 z-20">
            <Button
              variant={isMicOn ? "outline" : "destructive"}
              size="icon"
              className={cn(
                "rounded-full w-16 h-16 shadow-[0px_8px_24px_rgba(0,0,0,0.3)] transition-all hover:scale-105",
                isMicOn 
                  ? "bg-white/95 backdrop-blur-sm border-white/20 text-[#1E1E1E] hover:bg-white" 
                  : "bg-red-600 hover:bg-red-700 border-0"
              )}
              onClick={() => setIsMicOn(!isMicOn)}
            >
              {isMicOn ? <Mic className="w-6 h-6" /> : <MicOff className="w-6 h-6 text-white" />}
            </Button>
            <Button
              variant="destructive"
              size="icon"
              className="rounded-full w-16 h-16 bg-red-600 hover:bg-red-700 shadow-[0px_8px_24px_rgba(220,38,38,0.4)] transition-all hover:scale-105 border-0"
              onClick={onEndSession}
            >
              <PhoneOff className="w-6 h-6 text-white" />
            </Button>
          </div>

          {/* IDE Status Bar */}
          <div className="h-6 bg-[#37322F] flex items-center px-4 text-xs text-white font-sans">
            <div className="flex items-center gap-4">
              <span>Markdown</span>
              <span>UTF-8</span>
              <span>Ln {editorContent.split('\n').length}, Col 1</span>
            </div>
          </div>
        </div>

        {/* Right Sidebar - Participants (38% width) */}
        <div className="w-[38%] border-l border-[rgba(55,50,47,0.10)] bg-white flex flex-col">
          {/* AI Interviewer */}
          <div className="flex-1 flex flex-col items-center justify-center p-6 border-b border-[rgba(55,50,47,0.10)] relative bg-gradient-to-br from-[#FAFAFA] to-[#F7F5F3]">
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="relative">
                {/* Siri-like Animated Rings - Only when speaking */}
                {phase === "speaking" && (
                  <>
                    {/* Outer ring - slow pulse */}
                    <div className="absolute inset-0 -m-8 rounded-full border-4 border-[#37322F]/20 animate-siri-ring-1" />
                    {/* Middle ring - medium pulse */}
                    <div className="absolute inset-0 -m-6 rounded-full border-4 border-[#37322F]/30 animate-siri-ring-2" />
                    {/* Inner ring - fast pulse */}
                    <div className="absolute inset-0 -m-4 rounded-full border-4 border-[#37322F]/40 animate-siri-ring-3" />
                  </>
                )}
                
                <Avatar className="w-32 h-32 shadow-[0px_8px_32px_rgba(55,50,47,0.15)] relative z-10">
                  <AvatarFallback className={cn(
                    "text-4xl font-bold text-white font-sans",
                    interviewerPersona === "riya" 
                      ? "bg-gradient-to-br from-[#5D5754] to-[#3E3A38]" 
                      : "bg-gradient-to-br from-[#37322F] to-[#2A2624]"
                  )}>
                    {interviewerPersona === "riya" ? "R" : "B"}
                  </AvatarFallback>
                </Avatar>
                
                {phase === "speaking" && (
                  <div className="absolute -bottom-2 -right-2 bg-gradient-to-br from-green-400 to-green-600 rounded-full p-2.5 shadow-lg z-20 animate-pulse">
                    <Activity className="w-5 h-5 text-white" />
                  </div>
                )}
              </div>
            </div>
            <div className="absolute bottom-6 left-0 right-0 flex flex-col items-center gap-2">
              <p className="text-base font-bold text-[#2F3037] font-sans">
                {interviewerPersona === "riya" ? "Riya" : "Bodhi"}
              </p>
              <Badge className="text-xs bg-[rgba(55,50,47,0.08)] text-[#37322F] border-[rgba(55,50,47,0.12)] font-sans font-medium px-3 py-1">
                Interviewer
              </Badge>
            </div>
          </div>

          {/* Candidate (You) with Full Video Feed */}
          <div className="flex-1 flex flex-col relative">
            {/* Full-size Video Feed */}
            <div className="absolute inset-0">
              <video
                ref={videoRef}
                autoPlay
                muted
                playsInline
                className="w-full h-full object-cover bg-[#F7F5F3]"
                style={{ transform: "scaleX(-1)" }}
              />
              
              {/* Proctoring Indicator Overlay */}
              {proctoringActive && (
                <div className="absolute top-4 right-4 bg-green-500/90 backdrop-blur-sm rounded-full px-3 py-1.5 flex items-center gap-1.5 shadow-lg">
                  <Eye className="w-3.5 h-3.5 text-white" />
                  <span className="text-xs font-medium text-white font-sans">Monitored</span>
                </div>
              )}

              {/* Recording Indicator */}
              {phase === "recording" && (
                <div className="absolute top-4 left-4 bg-red-500/90 backdrop-blur-sm rounded-full px-3 py-1.5 flex items-center gap-1.5 shadow-lg">
                  <div className="w-2 h-2 bg-white rounded-full animate-pulse" />
                  <span className="text-xs font-medium text-white font-sans">Recording</span>
                </div>
              )}

              {/* Bottom Label Overlay */}
              <div className="absolute bottom-0 left-0 right-0 bg-linear-to-t from-black/60 via-black/30 to-transparent pt-12 pb-4 px-4">
                <div className="flex flex-col items-center gap-1">
                  <p className="text-sm font-semibold text-white font-sans drop-shadow-lg">You</p>
                  <Badge className="text-xs bg-blue-500/90 text-white border-blue-400/50 font-sans backdrop-blur-sm">
                    Candidate
                  </Badge>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}