"use client"

import { useRef, useEffect } from "react"

interface Turn {
  speaker: "user" | "bodhi"
  text: string
  phase?: string
}

interface TranscriptViewProps {
  transcript: Turn[]
  isProcessing?: boolean
}

export function TranscriptView({ transcript, isProcessing }: TranscriptViewProps) {
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [transcript, isProcessing])

  return (
    <div className="flex-1 space-y-4 overflow-y-auto rounded-2xl border border-[rgba(55,50,47,0.10)] bg-white p-6 shadow-[0px_2px_8px_rgba(55,50,47,0.06)]">
      {transcript.length === 0 && !isProcessing && (
        <div className="flex items-center justify-center h-full text-center">
          <div className="space-y-2">
            <div className="w-16 h-16 mx-auto rounded-full bg-[rgba(55,50,47,0.05)] flex items-center justify-center">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-[rgba(55,50,47,0.3)]">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
            </div>
            <p className="text-sm text-[rgba(55,50,47,0.45)]">
              Waiting for interview to start...
            </p>
          </div>
        </div>
      )}

      {transcript.map((turn, i) => (
        <div
          key={i}
          className={`flex gap-3 animate-fade-in-up ${
            turn.speaker === "bodhi" ? "flex-row" : "flex-row-reverse"
          }`}
        >
          <div
            className={`mt-0.5 h-9 w-9 shrink-0 rounded-full flex items-center justify-center text-sm font-bold shadow-sm ${
              turn.speaker === "bodhi"
                ? "bg-[#37322F] text-white"
                : "bg-[rgba(55,50,47,0.08)] text-[#37322F]"
            }`}
          >
            {turn.speaker === "bodhi" ? "B" : "Y"}
          </div>
          <div className={`flex-1 ${turn.speaker === "user" ? "text-right" : ""}`}>
            {turn.phase && (
              <span className="mb-1 inline-block rounded-full bg-[rgba(55,50,47,0.06)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[rgba(55,50,47,0.5)] font-semibold">
                {turn.phase}
              </span>
            )}
            <div
              className={`inline-block rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                turn.speaker === "bodhi"
                  ? "bg-[rgba(55,50,47,0.04)] text-[#37322F]"
                  : "bg-[#37322F] text-white"
              }`}
            >
              {turn.text}
            </div>
          </div>
        </div>
      ))}

      {isProcessing && (
        <div className="flex gap-3 animate-fade-in-up">
          <div className="mt-0.5 h-9 w-9 shrink-0 rounded-full flex items-center justify-center text-sm font-bold bg-[#37322F] text-white shadow-sm">
            B
          </div>
          <div className="flex-1">
            <div className="inline-block rounded-2xl bg-[rgba(55,50,47,0.04)] px-4 py-2.5">
              <div className="flex items-center gap-2">
                <div className="flex gap-1">
                  <span className="w-2 h-2 bg-[rgba(55,50,47,0.3)] rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-2 h-2 bg-[rgba(55,50,47,0.3)] rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-2 h-2 bg-[rgba(55,50,47,0.3)] rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
                <span className="text-sm text-[rgba(55,50,47,0.5)]">Thinking...</span>
              </div>
            </div>
          </div>
        </div>
      )}

      <div ref={endRef} />
    </div>
  )
}
