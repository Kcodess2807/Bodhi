"use client"

import { type SessionEnd } from "@/lib/api"

interface InterviewSummaryProps {
  summary: SessionEnd
}

export function InterviewSummary({ summary }: InterviewSummaryProps) {
  return (
    <div className="glass rounded-2xl p-6 shadow-[0px_4px_16px_rgba(55,50,47,0.12)] border border-green-200 animate-fade-in-up">
      <div className="flex items-start gap-4">
        <div className="w-12 h-12 rounded-full bg-green-500 flex items-center justify-center shrink-0">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5">
            <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="text-lg font-semibold text-[#37322F] mb-2">
            Interview Complete!
          </h3>
          <p className="text-sm text-[rgba(55,50,47,0.7)] leading-relaxed mb-4">
            {summary.summary}
          </p>
          {summary.overall_score != null && (
            <div className="flex items-center gap-3">
              <span className="text-xs font-semibold text-[rgba(55,50,47,0.5)] uppercase tracking-wider">
                Overall Score
              </span>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-2 bg-[rgba(55,50,47,0.08)] rounded-full overflow-hidden w-32">
                  <div
                    className="h-full bg-green-500 transition-all duration-500"
                    style={{ width: `${(summary.overall_score / 10) * 100}%` }}
                  />
                </div>
                <span className="text-lg font-bold text-[#37322F]">
                  {summary.overall_score.toFixed(1)}/10
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
