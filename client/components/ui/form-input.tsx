import { InputHTMLAttributes } from "react"

interface FormInputProps extends InputHTMLAttributes<HTMLInputElement> {
  fullWidth?: boolean
}

export function FormInput({ fullWidth, className = "", ...props }: FormInputProps) {
  const baseClasses =
    "w-full px-4 py-3.5 rounded-xl border-2 border-[rgba(55,50,47,0.12)] bg-white text-[#2F3037] placeholder:text-[rgba(55,50,47,0.35)] focus:outline-none focus:ring-4 focus:ring-[#37322F]/10 focus:border-[#37322F] hover:border-[rgba(55,50,47,0.2)] shadow-[0px_2px_8px_rgba(55,50,47,0.04)] transition-all font-sans text-[15px]"
  
  return (
    <input
      className={`${baseClasses} ${fullWidth ? "col-span-full" : ""} ${className}`}
      {...props}
    />
  )
}
