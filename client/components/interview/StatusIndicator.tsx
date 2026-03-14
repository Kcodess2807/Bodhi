"use client"

type Phase = "idle" | "setup" | "listening" | "recording" | "processing" | "speaking" | "ended"

interface StatusIndicatorProps {
  phase: Phase
  level?: number
  silenceThreshold?: number
}

export function StatusIndicator({ phase, level = 0, silenceThreshold = 0.015 }: StatusIndicatorProps) {
  const getStatusConfig = () => {
    switch (phase) {
      case "listening":
        return {
          color: "bg-green-500",
          text: "Listening... speak when ready",
          animate: "animate-pulse",
        }
      case "recording":
        return {
          color: "bg-red-500",
          text: "Recording your answer...",
          animate: "",
        }
      case "processing":
        return {
          color: "bg-yellow-500",
          text: "Processing your response...",
          animate: "animate-pulse",
        }
      case "speaking":
        return {
          color: "bg-blue-500",
          text: "Bodhi is speaking...",
          animate: "animate-pulse",
        }
      case "ended":
        return {
          color: "bg-gray-500",
          text: "Interview ended",
          animate: "",
        }
      default:
        return {
          color: "bg-gray-400",
          text: "Initializing...",
          animate: "",
        }
    }
  }

  const config = getStatusConfig()

  return (
    <div className="glass rounded-2xl p-4 shadow-[0px_2px_8px_rgba(55,50,47,0.06)]">
      <div className="flex items-center gap-3">
        <div className={`h-3 w-3 rounded-full ${config.color} ${config.animate} transition-all`} />
        <span className="text-sm font-medium text-[#37322F]">{config.text}</span>
      </div>

      {(phase === "listening" || phase === "recording") && (
        <div className="mt-3 flex h-12 items-end gap-1 rounded-lg bg-[rgba(55,50,47,0.04)] p-2">
          {Array.from({ length: 30 }).map((_, i) => (
            <div
              key={i}
              className="flex-1 rounded-sm bg-[#37322F] transition-all duration-75"
              style={{
                height: `${Math.min(100, Math.max(8, level * 3000 * (1 + Math.random() * 0.3)))}%`,
                opacity: level > silenceThreshold ? 0.8 : 0.2,
              }}
            />
          ))}
        </div>
      )}
    </div>
  )
}
