import { ButtonHTMLAttributes } from "react"

interface PrimaryButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  fullWidth?: boolean
  loading?: boolean
}

export function PrimaryButton({
  children,
  fullWidth,
  loading,
  disabled,
  className = "",
  ...props
}: PrimaryButtonProps) {
  return (
    <button
      className={`h-12 rounded-xl bg-gradient-to-r from-[#37322F] to-[#2A2624] px-6 py-3.5 text-sm font-semibold text-white transition-all duration-200 hover:from-[#2A2624] hover:to-[#1F1C1A] hover:shadow-[0px_6px_20px_rgba(55,50,47,0.3)] hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 font-sans ${
        fullWidth ? "w-full" : ""
      } ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading && (
        <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
      )}
      {children}
    </button>
  )
}
