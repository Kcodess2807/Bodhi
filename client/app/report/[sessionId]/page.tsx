"use client"

import { useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import Navbar from "@/components/Navbar"
import { type InterviewReport, getInterviewReport, downloadReportPDF } from "@/lib/api"

/* ── helpers ─────────────────────────────────────────────────── */

const GRADE_COLORS: Record<string, string> = {
  "A+": "#16a34a", A: "#22c55e", "A-": "#4ade80",
  "B+": "#2563eb", B: "#3b82f6", "B-": "#60a5fa",
  "C+": "#d97706", C: "#f59e0b", "C-": "#fbbf24",
  "D+": "#dc2626", D: "#ef4444", F: "#991b1b",
}

const SEVERITY_COLORS: Record<string, string> = {
  high: "#ef4444", medium: "#f59e0b", low: "#6b7280",
}

const PHASE_LABELS: Record<string, string> = {
  technical: "Technical", behavioral: "Behavioral",
  dsa: "DSA", project: "Project Discussion",
  intro: "Introduction", wrapup: "Wrap-Up",
}

function gradeColor(grade: string) {
  return GRADE_COLORS[grade] ?? "#6b7280"
}

function MetricBar({ label, value, max = 5 }: { label: string; value: number; max?: number }) {
  const pct = Math.min(100, (value / max) * 100)
  const hue = pct > 70 ? 142 : pct > 45 ? 38 : 0
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-[rgba(55,50,47,0.7)] font-medium">{label}</span>
        <span className="font-semibold text-[#37322F]">{value.toFixed(1)}/{max}</span>
      </div>
      <div className="h-2 rounded-full bg-[rgba(55,50,47,0.08)] overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700 ease-out"
          style={{ width: `${pct}%`, backgroundColor: `hsl(${hue}, 72%, 52%)` }}
        />
      </div>
    </div>
  )
}

function StatCard({ label, value, unit, accent }: { label: string; value: string | number; unit?: string; accent?: string }) {
  return (
    <div className="rounded-xl border border-[rgba(55,50,47,0.08)] bg-white p-4 shadow-[0px_1px_4px_rgba(55,50,47,0.04)]">
      <p className="text-xs text-[rgba(55,50,47,0.5)] mb-1">{label}</p>
      <p className="text-xl font-bold" style={{ color: accent ?? "#37322F" }}>
        {value}{unit && <span className="text-sm font-normal text-[rgba(55,50,47,0.5)] ml-0.5">{unit}</span>}
      </p>
    </div>
  )
}

function Badge({ text, color }: { text: string; color?: string }) {
  return (
    <span
      className="inline-block rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide"
      style={{
        backgroundColor: `${color ?? "#6b7280"}18`,
        color: color ?? "#6b7280",
      }}
    >
      {text}
    </span>
  )
}

/* ── Main Page ───────────────────────────────────────────────── */

export default function ReportPage() {
  const params = useParams()
  const router = useRouter()
  const sessionId = params.sessionId as string

  const [report, setReport] = useState<InterviewReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [downloadingPDF, setDownloadingPDF] = useState(false)

  useEffect(() => {
    if (!sessionId) return
    setLoading(true)
    getInterviewReport(sessionId)
      .then(setReport)
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false))
  }, [sessionId])

  const handleDownloadPDF = async () => {
    setDownloadingPDF(true)
    try { await downloadReportPDF(sessionId) }
    catch (err) { setError(String(err)) }
    finally { setDownloadingPDF(false) }
  }

  /* ── loading / error states ─────────────────────────────────── */
  if (loading) {
    return (
      <div className="min-h-screen bg-[#F7F5F3]">
        <Navbar />
        <div className="flex items-center justify-center pt-40">
          <div className="text-center space-y-4 animate-pulse">
            <div className="w-16 h-16 mx-auto rounded-full bg-[rgba(55,50,47,0.08)]" />
            <p className="text-[rgba(55,50,47,0.5)] text-sm">Loading your interview report…</p>
          </div>
        </div>
      </div>
    )
  }

  if (error || !report) {
    return (
      <div className="min-h-screen bg-[#F7F5F3]">
        <Navbar />
        <div className="flex items-center justify-center pt-40">
          <div className="text-center space-y-4 max-w-md">
            <p className="text-red-600 text-sm">{error || "Report not found."}</p>
            <button
              onClick={() => router.push("/interview")}
              className="rounded-full border border-[rgba(55,50,47,0.2)] bg-white px-6 py-2 text-sm font-semibold text-[#37322F] transition hover:shadow-md"
            >
              ← Back to Interviews
            </button>
          </div>
        </div>
      </div>
    )
  }

  const { session_info: info } = report
  const phases = Object.entries(report.phase_breakdown)
  const behavior = report.behavioral_summary
  const proctor = report.proctoring_summary

  return (
    <div className="min-h-screen bg-[#F7F5F3]">
      <Navbar />

      <div className="mx-auto max-w-5xl px-4 pt-24 pb-16 space-y-8 animate-fade-in-up">

        {/* ── Hero / Overall Grade ────────────────────────────────── */}
        <section className="relative overflow-hidden rounded-2xl border border-[rgba(55,50,47,0.08)] bg-gradient-to-br from-white via-white to-[#F7F5F3] p-8 shadow-[0px_4px_20px_rgba(55,50,47,0.06)]">
          {/* Brand accent bar */}
          <div className="absolute top-0 left-0 right-0 h-[3px] rounded-t-2xl bg-[#37322F] opacity-75" />
          <div className="absolute -top-20 -right-20 w-64 h-64 rounded-full opacity-[0.04]"
               style={{ background: gradeColor(report.overall_grade) }} />

          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6">
            {/* Left: Name + Role */}
            <div>
              <p className="text-xs text-[rgba(55,50,47,0.5)] uppercase tracking-wider mb-1">Bodhi · Interview Report</p>
              <h1 className="text-2xl font-bold text-[#37322F]">{info.candidate_name || "Candidate"}</h1>
              <p className="text-sm text-[rgba(55,50,47,0.6)] mt-1">
                {info.target_role}{info.target_company ? ` at ${info.target_company}` : ""}
              </p>
              <p className="text-xs text-[rgba(55,50,47,0.35)] mt-1 font-mono">
                Session: {info.session_id}
              </p>
            </div>

            {/* Right: Grade Badge */}
            <div className="flex items-center gap-6">
              <div className="text-center">
                <div
                  className="w-20 h-20 rounded-2xl flex items-center justify-center text-white text-3xl font-extrabold shadow-lg"
                  style={{ backgroundColor: gradeColor(report.overall_grade) }}
                >
                  {report.overall_grade}
                </div>
                <p className="text-xs text-[rgba(55,50,47,0.5)] mt-2">{report.overall_score_pct}%</p>
              </div>
              <div className="text-right space-y-1">
                <p className="text-sm text-[rgba(55,50,47,0.6)]">
                  <span className="font-semibold text-[#37322F]">{report.total_questions}</span> questions
                </p>
                <p className="text-sm text-[rgba(55,50,47,0.6)]">
                  <span className="font-semibold text-[#37322F]">{phases.length}</span> phases
                </p>
              </div>
            </div>
          </div>

          {/* Hiring Recommendation */}
          <div className="mt-6 rounded-xl bg-[rgba(55,50,47,0.03)] border border-[rgba(55,50,47,0.06)] p-4">
            <p className="text-xs text-[rgba(55,50,47,0.5)] uppercase tracking-wider mb-1">Hiring Recommendation</p>
            <p className="text-sm text-[#37322F] leading-relaxed">{report.hiring_recommendation}</p>
          </div>
        </section>

        {/* ── Action Buttons ─────────────────────────────────────── */}
        <div className="flex gap-3">
          <button
            onClick={() => router.push("/interview")}
            className="rounded-full border border-[rgba(55,50,47,0.2)] bg-white px-5 py-2 text-sm font-semibold text-[#37322F] transition hover:shadow-md"
          >
            ← New Interview
          </button>
          <button
            onClick={handleDownloadPDF}
            disabled={downloadingPDF}
            className="rounded-full bg-[#37322F] px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-[#4a443f] disabled:opacity-50 flex items-center gap-2 shadow-[0px_2px_8px_rgba(55,50,47,0.25)]"
          >
            {downloadingPDF ? (
              <>
                <span className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin shrink-0" />
                Generating…
              </>
            ) : (
              <>
                <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
                Download PDF
              </>
            )}
          </button>
        </div>

        {/* ── Phase Breakdown ────────────────────────────────────── */}
        <section className="space-y-4">
          <h2 className="text-lg font-bold text-[#37322F] flex items-center gap-2.5">
            <span className="w-1 h-5 rounded-full bg-[#37322F] opacity-60 shrink-0" />
            Phase Breakdown
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            {phases.map(([phase, data]) => (
              <div
                key={phase}
                className="rounded-2xl border border-[rgba(55,50,47,0.08)] bg-white p-5 shadow-[0px_2px_8px_rgba(55,50,47,0.04)] space-y-4"
              >
                {/* Header */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <h3 className="text-sm font-bold text-[#37322F]">
                      {PHASE_LABELS[phase] ?? phase}
                    </h3>
                    <Badge text={data.grade} color={gradeColor(data.grade)} />
                  </div>
                  <span className="text-xs text-[rgba(55,50,47,0.5)]">
                    {data.questions_asked} Qs · {data.score_pct}%
                  </span>
                </div>

                {/* Metrics */}
                <div className="space-y-2.5">
                  <MetricBar label="Accuracy" value={data.metrics.accuracy} />
                  <MetricBar label="Depth" value={data.metrics.depth} />
                  <MetricBar label="Communication" value={data.metrics.communication} />
                  <MetricBar label="Confidence" value={data.metrics.confidence} />
                </div>

                {/* Strengths & Improvements */}
                {(data.strengths.length > 0 || data.improvements.length > 0) && (
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    {data.strengths.length > 0 && (
                      <div>
                        <p className="text-[rgba(55,50,47,0.5)] font-medium mb-1">Strengths</p>
                        <ul className="space-y-1">
                          {data.strengths.map((s, i) => (
                            <li key={i} className="text-[#37322F] flex items-start gap-1">
                              <span className="text-green-500 mt-0.5">✓</span> {s}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {data.improvements.length > 0 && (
                      <div>
                        <p className="text-[rgba(55,50,47,0.5)] font-medium mb-1">To Improve</p>
                        <ul className="space-y-1">
                          {data.improvements.map((s, i) => (
                            <li key={i} className="text-[#37322F] flex items-start gap-1">
                              <span className="text-amber-500 mt-0.5">▲</span> {s}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                {/* Feedback */}
                {data.feedback.length > 0 && (
                  <details className="group">
                    <summary className="text-xs text-[rgba(55,50,47,0.45)] cursor-pointer hover:text-[#37322F] transition">
                      Show feedback ({data.feedback.length})
                    </summary>
                    <ul className="mt-2 space-y-1 text-xs text-[rgba(55,50,47,0.6)]">
                      {data.feedback.map((f, i) => (
                        <li key={i} className="pl-3 border-l-2 border-[rgba(55,50,47,0.08)]">{f}</li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            ))}
          </div>
        </section>

        {/* ── Behavioral Analytics ───────────────────────────────── */}
        <section className="space-y-4">
          <h2 className="text-lg font-bold text-[#37322F] flex items-center gap-2.5">
            <span className="w-1 h-5 rounded-full bg-[#37322F] opacity-60 shrink-0" />
            Behavioral Analytics
          </h2>
          <div className="grid gap-3 grid-cols-2 md:grid-cols-4">
            <StatCard
              label="Confidence Score"
              value={behavior.avg_confidence_score}
              unit="/100"
              accent={behavior.avg_confidence_score >= 60 ? "#16a34a" : "#ef4444"}
            />
            <StatCard
              label="Speaking Rate"
              value={behavior.avg_speaking_rate}
              unit="WPM"
              accent={behavior.avg_speaking_rate >= 100 && behavior.avg_speaking_rate <= 170 ? "#16a34a" : "#d97706"}
            />
            <StatCard
              label="Filler Rate"
              value={behavior.avg_filler_rate.toFixed(1)}
              unit="%"
              accent={behavior.avg_filler_rate <= 5 ? "#16a34a" : "#ef4444"}
            />
            <StatCard
              label="Data Points"
              value={behavior.total_data_points}
            />
          </div>

          <div className="rounded-2xl border border-[rgba(55,50,47,0.08)] bg-white p-5 shadow-[0px_2px_8px_rgba(55,50,47,0.04)]">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-xs text-[rgba(55,50,47,0.5)] mb-0.5">Dominant Emotion</p>
                <p className="font-semibold text-[#37322F] capitalize">{behavior.dominant_emotion}</p>
              </div>
              <div>
                <p className="text-xs text-[rgba(55,50,47,0.5)] mb-0.5">Sentiment</p>
                <p className="font-semibold text-[#37322F] capitalize">{behavior.dominant_sentiment}</p>
              </div>
              <div>
                <p className="text-xs text-[rgba(55,50,47,0.5)] mb-0.5">Posture Issues</p>
                <p className="font-semibold" style={{ color: behavior.posture_issues > 3 ? "#ef4444" : "#37322F" }}>
                  {behavior.posture_issues}
                </p>
              </div>
              <div>
                <p className="text-xs text-[rgba(55,50,47,0.5)] mb-0.5">Gaze Issues</p>
                <p className="font-semibold" style={{ color: behavior.gaze_issues > 5 ? "#ef4444" : "#37322F" }}>
                  {behavior.gaze_issues}
                </p>
              </div>
            </div>

            {behavior.behavioral_flags.length > 0 && (
              <div className="mt-4 pt-4 border-t border-[rgba(55,50,47,0.06)]">
                <p className="text-xs text-[rgba(55,50,47,0.5)] mb-2">Behavioral Flags</p>
                <div className="flex flex-wrap gap-1.5">
                  {behavior.behavioral_flags.map((flag, i) => (
                    <Badge key={i} text={flag} color="#d97706" />
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>

        {/* ── Proctoring Summary ─────────────────────────────────── */}
        <section className="space-y-4">
          <h2 className="text-lg font-bold text-[#37322F] flex items-center gap-2.5">
            <span className="w-1 h-5 rounded-full bg-[#37322F] opacity-60 shrink-0" />
            Proctoring Summary
          </h2>
          <div className="rounded-2xl border border-[rgba(55,50,47,0.08)] bg-white p-5 shadow-[0px_2px_8px_rgba(55,50,47,0.04)]">
            {proctor.session_flagged && (
              <div className="mb-4 rounded-xl bg-red-50 border border-red-200 p-3 flex items-center gap-2">
                <span className="text-red-600 text-lg">⚠</span>
                <p className="text-sm text-red-700 font-medium">Session flagged due to proctoring violations</p>
              </div>
            )}

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <StatCard label="Total Violations" value={proctor.total_violations} accent={proctor.total_violations > 0 ? "#ef4444" : "#16a34a"} />
              <StatCard label="High Severity" value={proctor.high_severity_count} accent={proctor.high_severity_count > 0 ? "#ef4444" : "#16a34a"} />
              <StatCard label="Medium Severity" value={proctor.medium_severity_count} accent={proctor.medium_severity_count > 0 ? "#d97706" : "#16a34a"} />
              <StatCard label="Low Severity" value={proctor.low_severity_count} />
            </div>

            {Object.keys(proctor.violation_types).length > 0 && (
              <div className="mt-4 pt-4 border-t border-[rgba(55,50,47,0.06)]">
                <p className="text-xs text-[rgba(55,50,47,0.5)] mb-2">Violation Types</p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(proctor.violation_types).map(([type, count]) => (
                    <span key={type} className="inline-flex items-center gap-1 rounded-full bg-[rgba(55,50,47,0.05)] px-3 py-1 text-xs text-[#37322F]">
                      {type.replace(/_/g, " ")} <span className="font-bold">×{count}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {proctor.timeline.length > 0 && (
              <details className="mt-4 pt-4 border-t border-[rgba(55,50,47,0.06)] group">
                <summary className="text-xs text-[rgba(55,50,47,0.45)] cursor-pointer hover:text-[#37322F] transition">
                  Show violation timeline ({proctor.timeline.length})
                </summary>
                <div className="mt-2 space-y-2">
                  {proctor.timeline.map((v, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs">
                      <span
                        className="mt-0.5 w-2 h-2 rounded-full shrink-0"
                        style={{ backgroundColor: SEVERITY_COLORS[v.severity] ?? "#6b7280" }}
                      />
                      <div>
                        <span className="font-medium text-[#37322F]">{v.type.replace(/_/g, " ")}</span>
                        {v.message && <span className="text-[rgba(55,50,47,0.5)]"> — {v.message}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        </section>

        {/* ── Cross-Section Insights ─────────────────────────────── */}
        {report.cross_section_insights.length > 0 && (
          <section className="space-y-4">
            <h2 className="text-lg font-bold text-[#37322F] flex items-center gap-2.5">
              <span className="w-1 h-5 rounded-full bg-[#37322F] opacity-60 shrink-0" />
              Cross-Section Insights
            </h2>
            <div className="rounded-2xl border border-[rgba(55,50,47,0.08)] bg-white p-5 shadow-[0px_2px_8px_rgba(55,50,47,0.04)] space-y-2">
              {report.cross_section_insights.map((insight, i) => (
                <div key={i} className="flex items-start gap-2 text-sm text-[#37322F]">
                  <span className="mt-0.5 shrink-0 text-[#37322F] opacity-40">▸</span>
                  <p>{insight}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* ── Top Strengths & Improvements ───────────────────────── */}
        <div className="grid gap-4 md:grid-cols-2">
          {report.top_strengths.length > 0 && (
            <section className="rounded-2xl border border-[rgba(55,50,47,0.08)] bg-white p-5 shadow-[0px_2px_8px_rgba(55,50,47,0.04)]">
              <h3 className="text-sm font-bold text-[#37322F] mb-3 flex items-center gap-2">
                <span className="w-1 h-4 rounded-full bg-[#37322F] opacity-50 shrink-0" />
                Top Strengths
              </h3>
              <ul className="space-y-2">
                {report.top_strengths.map((s, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-[#37322F]">
                    <span className="text-green-500 mt-0.5">✓</span> {s}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {report.top_improvements.length > 0 && (
            <section className="rounded-2xl border border-[rgba(55,50,47,0.08)] bg-white p-5 shadow-[0px_2px_8px_rgba(55,50,47,0.04)]">
              <h3 className="text-sm font-bold text-[#37322F] mb-3 flex items-center gap-2">
                <span className="w-1 h-4 rounded-full bg-[#37322F] opacity-50 shrink-0" />
                Areas for Improvement
              </h3>
              <ul className="space-y-2">
                {report.top_improvements.map((s, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-[#37322F]">
                    <span className="text-amber-500 mt-0.5">▲</span> {s}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        {/* ── Brand Footer ─────────────────────────────────────── */}
        <footer className="text-center pt-4 pb-2 border-t border-[rgba(55,50,47,0.06)]">
          <p className="text-xs text-[rgba(55,50,47,0.3)]">
            Generated by{" "}
            <span className="font-semibold text-[rgba(55,50,47,0.45)]">Bodhi</span>
            {" "}· AI Mock Interview Platform
          </p>
        </footer>

      </div>
    </div>
  )
}
