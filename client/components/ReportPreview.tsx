"use client";

import { type InterviewReport } from "@/lib/api";

interface ReportPreviewProps {
  report: InterviewReport;
  onDownloadPDF: () => void;
  downloading: boolean;
}

export default function ReportPreview({ report, onDownloadPDF, downloading }: ReportPreviewProps) {
  const gradeColor = (score: number) => {
    if (score >= 80) return "text-green-400";
    if (score >= 65) return "text-blue-400";
    if (score >= 50) return "text-yellow-400";
    return "text-red-400";
  };

  const severityColor = (severity: string) => {
    if (severity === "high") return "text-red-400";
    if (severity === "medium") return "text-yellow-400";
    return "text-green-400";
  };

  return (
    <div className="space-y-6 rounded-lg border border-[var(--border)] bg-[var(--card)] p-6">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--border)] pb-4">
        <div>
          <h2 className="text-2xl font-bold">Interview Report</h2>
          <p className="text-sm text-zinc-400 mt-1">
            {report.session_info.candidate_name} • {report.session_info.target_company} • {report.session_info.target_role}
          </p>
        </div>
        <button
          onClick={onDownloadPDF}
          disabled={downloading}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {downloading ? "Generating..." : "Download PDF"}
        </button>
      </div>

      {/* Overall Score */}
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-lg border border-[var(--border)] bg-[var(--background)] p-4 text-center">
          <div className="text-sm text-zinc-400">Overall Grade</div>
          <div className={`text-3xl font-bold mt-2 ${gradeColor(report.overall_score_pct)}`}>
            {report.overall_grade}
          </div>
        </div>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--background)] p-4 text-center">
          <div className="text-sm text-zinc-400">Score</div>
          <div className={`text-3xl font-bold mt-2 ${gradeColor(report.overall_score_pct)}`}>
            {report.overall_score_pct}%
          </div>
        </div>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--background)] p-4 text-center">
          <div className="text-sm text-zinc-400">Questions</div>
          <div className="text-3xl font-bold mt-2">{report.total_questions}</div>
        </div>
      </div>

      {/* Recommendation */}
      <div className="rounded-lg border border-[var(--border)] bg-[var(--background)] p-4">
        <h3 className="text-sm font-semibold text-zinc-300 mb-2">Hiring Recommendation</h3>
        <p className="text-sm text-zinc-200">{report.hiring_recommendation}</p>
      </div>

      {/* Phase Breakdown */}
      <div>
        <h3 className="text-lg font-semibold mb-3">Phase-wise Performance</h3>
        <div className="space-y-3">
          {Object.entries(report.phase_breakdown).map(([phase, data]) => (
            <div key={phase} className="rounded-lg border border-[var(--border)] bg-[var(--background)] p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold capitalize">{phase}</span>
                <div className="flex items-center gap-3">
                  <span className={`text-lg font-bold ${gradeColor(data.score_pct)}`}>{data.grade}</span>
                  <span className="text-sm text-zinc-400">{data.score_pct}%</span>
                  <span className="text-xs text-zinc-500">{data.questions_asked} questions</span>
                </div>
              </div>
              <div className="grid grid-cols-4 gap-2 text-xs">
                <div>
                  <span className="text-zinc-500">Accuracy:</span>
                  <span className="ml-1 text-zinc-300">{data.metrics.accuracy}/5</span>
                </div>
                <div>
                  <span className="text-zinc-500">Depth:</span>
                  <span className="ml-1 text-zinc-300">{data.metrics.depth}/5</span>
                </div>
                <div>
                  <span className="text-zinc-500">Communication:</span>
                  <span className="ml-1 text-zinc-300">{data.metrics.communication}/5</span>
                </div>
                <div>
                  <span className="text-zinc-500">Confidence:</span>
                  <span className="ml-1 text-zinc-300">{data.metrics.confidence}/5</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Strengths and Improvements */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <h3 className="text-sm font-semibold text-green-400 mb-2">Key Strengths</h3>
          <ul className="space-y-1">
            {report.top_strengths.map((strength, i) => (
              <li key={i} className="text-xs text-zinc-300">• {strength}</li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-yellow-400 mb-2">Areas for Improvement</h3>
          <ul className="space-y-1">
            {report.top_improvements.map((improvement, i) => (
              <li key={i} className="text-xs text-zinc-300">• {improvement}</li>
            ))}
          </ul>
        </div>
      </div>

      {/* Behavioral Analysis */}
      {report.behavioral_summary.total_data_points > 0 && (
        <div>
          <h3 className="text-lg font-semibold mb-3">Behavioral Analysis</h3>
          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-lg border border-[var(--border)] bg-[var(--background)] p-3">
              <div className="text-xs text-zinc-500">Avg Confidence Score</div>
              <div className="text-xl font-bold mt-1">{report.behavioral_summary.avg_confidence_score}/100</div>
            </div>
            <div className="rounded-lg border border-[var(--border)] bg-[var(--background)] p-3">
              <div className="text-xs text-zinc-500">Avg Speaking Rate</div>
              <div className="text-xl font-bold mt-1">{report.behavioral_summary.avg_speaking_rate} wpm</div>
            </div>
            <div className="rounded-lg border border-[var(--border)] bg-[var(--background)] p-3">
              <div className="text-xs text-zinc-500">Dominant Emotion</div>
              <div className="text-xl font-bold mt-1 capitalize">{report.behavioral_summary.dominant_emotion}</div>
            </div>
            <div className="rounded-lg border border-[var(--border)] bg-[var(--background)] p-3">
              <div className="text-xs text-zinc-500">Dominant Sentiment</div>
              <div className="text-xl font-bold mt-1 capitalize">{report.behavioral_summary.dominant_sentiment}</div>
            </div>
          </div>
          {report.behavioral_summary.behavioral_flags.length > 0 && (
            <div className="mt-3">
              <div className="text-xs text-zinc-500 mb-2">Behavioral Flags</div>
              <div className="flex flex-wrap gap-2">
                {report.behavioral_summary.behavioral_flags.map((flag, i) => (
                  <span key={i} className="rounded bg-zinc-800 px-2 py-1 text-xs capitalize">{flag}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Proctoring Summary */}
      {report.proctoring_summary.total_violations > 0 && (
        <div>
          <h3 className="text-lg font-semibold mb-3">Proctoring Summary</h3>
          <div className="grid grid-cols-4 gap-4 mb-3">
            <div className="rounded-lg border border-[var(--border)] bg-[var(--background)] p-3 text-center">
              <div className="text-xs text-zinc-500">Total</div>
              <div className="text-xl font-bold mt-1">{report.proctoring_summary.total_violations}</div>
            </div>
            <div className="rounded-lg border border-[var(--border)] bg-[var(--background)] p-3 text-center">
              <div className="text-xs text-red-400">High</div>
              <div className="text-xl font-bold mt-1 text-red-400">{report.proctoring_summary.high_severity_count}</div>
            </div>
            <div className="rounded-lg border border-[var(--border)] bg-[var(--background)] p-3 text-center">
              <div className="text-xs text-yellow-400">Medium</div>
              <div className="text-xl font-bold mt-1 text-yellow-400">{report.proctoring_summary.medium_severity_count}</div>
            </div>
            <div className="rounded-lg border border-[var(--border)] bg-[var(--background)] p-3 text-center">
              <div className="text-xs text-green-400">Low</div>
              <div className="text-xl font-bold mt-1 text-green-400">{report.proctoring_summary.low_severity_count}</div>
            </div>
          </div>
          {report.proctoring_summary.session_flagged && (
            <div className="rounded-lg border border-red-700 bg-red-900/30 p-3 text-sm text-red-300">
              ⚠️ Session was flagged due to multiple violations
            </div>
          )}
        </div>
      )}

      {/* Cross-section Insights */}
      {report.cross_section_insights.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold mb-3">Cross-section Insights</h3>
          <ul className="space-y-2">
            {report.cross_section_insights.map((insight, i) => (
              <li key={i} className="text-sm text-zinc-300 rounded-lg border border-[var(--border)] bg-[var(--background)] p-3">
                • {insight}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
