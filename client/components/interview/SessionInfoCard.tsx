"use client"

import { type SessionState } from "@/lib/api"

interface SessionInfoCardProps {
  sessionInfo: SessionState | null
  sessionId: string
}

export function SessionInfoCard({ sessionInfo, sessionId }: SessionInfoCardProps) {
  return (
    <div className="glass rounded-2xl p-5 shadow-[0px_2px_8px_rgba(55,50,47,0.06)]">
      <h3 className="mb-4 text-sm font-semibold text-[#37322F] flex items-center gap-2">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <polyline points="12 6 12 12 16 14" />
        </svg>
        Session Info
      </h3>

      {sessionInfo ? (
        <dl className="space-y-3 text-sm">
          <div className="flex justify-between items-center pb-2 border-b border-[rgba(55,50,47,0.08)]">
            <dt className="text-[rgba(55,50,47,0.5)]">Session ID</dt>
            <dd className="font-mono text-xs text-[#37322F] bg-[rgba(55,50,47,0.05)] px-2 py-1 rounded">
              {sessionId.slice(0, 8)}...
            </dd>
          </div>
          <div className="flex justify-between items-center">
            <dt className="text-[rgba(55,50,47,0.5)]">Phase</dt>
            <dd className="font-medium text-[#37322F] capitalize">{sessionInfo.phase}</dd>
          </div>
          <div className="flex justify-between items-center">
            <dt className="text-[rgba(55,50,47,0.5)]">Difficulty</dt>
            <dd className="font-medium text-[#37322F]">
              <div className="flex items-center gap-1">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div
                    key={i}
                    className={`w-2 h-2 rounded-full ${
                      i < sessionInfo.difficulty_level
                        ? "bg-[#37322F]"
                        : "bg-[rgba(55,50,47,0.15)]"
                    }`}
                  />
                ))}
              </div>
            </dd>
          </div>
          <div className="flex justify-between items-center">
            <dt className="text-[rgba(55,50,47,0.5)]">Company</dt>
            <dd className="font-medium text-[#37322F]">{sessionInfo.company}</dd>
          </div>
          <div className="flex justify-between items-center">
            <dt className="text-[rgba(55,50,47,0.5)]">Role</dt>
            <dd className="font-medium text-[#37322F]">{sessionInfo.role}</dd>
          </div>
        </dl>
      ) : (
        <div className="flex items-center justify-center py-8">
          <div className="w-5 h-5 border-2 border-[rgba(55,50,47,0.3)] border-t-[#37322F] rounded-full animate-spin" />
        </div>
      )}
    </div>
  )
}
