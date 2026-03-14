"use client"

import { useState } from "react"
import { FormInput } from "@/components/ui/form-input"
import { PrimaryButton } from "@/components/ui/primary-button"
import { type CandidateProfile, uploadResume } from "@/lib/api"

interface InterviewSetupFormProps {
  onSubmit: (formData: InterviewFormData) => void
  loading?: boolean
}

export interface InterviewFormData {
  candidate_name: string
  company: string
  role: string
  mode: "standard" | "option_a" | "option_b"
  user_id: string
  jd_text: string
  interviewer_persona: "bodhi" | "riya"
}

export function InterviewSetupForm({ onSubmit, loading }: InterviewSetupFormProps) {
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState("")
  const [uploadedProfile, setUploadedProfile] = useState<CandidateProfile | null>(null)
  
  const [form, setForm] = useState<InterviewFormData>({
    candidate_name: "",
    company: "",
    role: "Software Engineer",
    mode: "standard",
    user_id: "",
    jd_text: "",
    interviewer_persona: "bodhi",
  })

  const handleResumeUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    
    setUploading(true)
    setError("")
    
    try {
      const result = await uploadResume(file)
      setUploadedProfile(result.profile)
      setForm((prev) => ({
        ...prev,
        user_id: result.user_id,
        candidate_name: result.profile.name || prev.candidate_name,
      }))
    } catch (err) {
      setError(String(err))
    } finally {
      setUploading(false)
    }
  }

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    onSubmit(form)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 animate-fade-in-up">
          {error}
        </div>
      )}

      <div>
        <label className="block text-xs font-semibold text-[rgba(55,50,47,0.6)] mb-2 uppercase tracking-wider">
          Interview Mode
        </label>
        <select
          value={form.mode}
          onChange={(e) => {
            setForm({
              ...form,
              mode: e.target.value as "standard" | "option_a" | "option_b",
            })
            setUploadedProfile(null)
            setError("")
          }}
          className="w-full rounded-xl border border-[rgba(55,50,47,0.15)] bg-[#F7F5F3] px-3 py-2.5 text-sm text-[#37322F] focus:outline-none focus:ring-2 focus:ring-[rgba(55,50,47,0.15)] transition"
        >
          <option value="standard">Standard (Company-based)</option>
          <option value="option_a">Resume-Based</option>
          <option value="option_b">JD-Targeted</option>
        </select>
      </div>

      {form.mode !== "standard" && !form.user_id && (
        <div className="space-y-2 animate-fade-in-up">
          <label className="block text-xs font-semibold text-[rgba(55,50,47,0.6)] uppercase tracking-wider">
            Upload Resume (PDF or DOCX)
          </label>
          <input
            type="file"
            accept=".pdf,.docx"
            onChange={handleResumeUpload}
            disabled={uploading}
            className="w-full rounded-xl border border-[rgba(55,50,47,0.15)] bg-[#F7F5F3] px-3 py-2.5 text-sm text-[#37322F] 
              file:mr-4 file:py-1.5 file:px-4 file:rounded-full file:border-0 
              file:bg-[#37322F] file:text-white file:text-xs file:font-semibold 
              hover:file:bg-[#2a2520] disabled:opacity-50 transition"
          />
          {uploading && (
            <p className="text-xs text-[rgba(55,50,47,0.5)] flex items-center gap-2">
              <span className="w-3 h-3 border-2 border-[rgba(55,50,47,0.3)] border-t-[#37322F] rounded-full animate-spin" />
              Uploading and parsing resume...
            </p>
          )}
        </div>
      )}

      {form.mode !== "standard" && uploadedProfile && (
        <div className="rounded-xl border border-green-700 bg-green-900/20 p-4 space-y-2 animate-fade-in-up">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-green-300 flex items-center gap-2">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M3 7L6 10L11 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Resume Uploaded
            </p>
            <button
              type="button"
              onClick={() => {
                setUploadedProfile(null)
                setForm((p) => ({ ...p, user_id: "" }))
              }}
              className="text-xs text-[rgba(55,50,47,0.5)] hover:text-[#37322F] transition"
            >
              Change
            </button>
          </div>
          <div className="text-xs text-[rgba(55,50,47,0.7)]">
            <p className="font-medium text-[#37322F]">{uploadedProfile.name}</p>
            {uploadedProfile.email && (
              <p className="text-[rgba(55,50,47,0.5)]">{uploadedProfile.email}</p>
            )}
            {uploadedProfile.skills.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {uploadedProfile.skills.slice(0, 5).map((s, i) => (
                  <span
                    key={i}
                    className="rounded-full bg-[rgba(55,50,47,0.1)] px-2 py-0.5 text-[10px] font-medium"
                  >
                    {s}
                  </span>
                ))}
                {uploadedProfile.skills.length > 5 && (
                  <span className="text-[10px] text-[rgba(55,50,47,0.4)]">
                    +{uploadedProfile.skills.length - 5} more
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      <FormInput
        placeholder="Your name *"
        required
        value={form.candidate_name}
        onChange={(e) => setForm({ ...form, candidate_name: e.target.value })}
      />

      {form.mode === "standard" && (
        <>
          <FormInput
            placeholder="Company *"
            required
            value={form.company}
            onChange={(e) => setForm({ ...form, company: e.target.value })}
          />
          <FormInput
            placeholder="Role *"
            required
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value })}
          />
        </>
      )}

      {form.mode === "option_b" && (
        <div className="animate-fade-in-up">
          <label className="block text-xs font-semibold text-[rgba(55,50,47,0.6)] mb-2 uppercase tracking-wider">
            Job Description *
          </label>
          <textarea
            placeholder="Paste the full job description here..."
            value={form.jd_text}
            onChange={(e) => setForm({ ...form, jd_text: e.target.value })}
            className="w-full min-h-32 rounded-xl border border-[rgba(55,50,47,0.15)] bg-[#F7F5F3] px-3 py-2.5 text-sm text-[#37322F] placeholder-[rgba(55,50,47,0.4)] focus:outline-none focus:ring-2 focus:ring-[rgba(55,50,47,0.15)] transition resize-y"
            required
          />
        </div>
      )}

      <div>
        <label className="block text-xs font-semibold text-[rgba(55,50,47,0.6)] mb-3 uppercase tracking-wider">
          Choose Interviewer
        </label>
        <div className="grid grid-cols-2 gap-3">
          <button
            type="button"
            onClick={() => setForm({ ...form, interviewer_persona: "bodhi" })}
            className={`flex flex-col items-center p-4 rounded-xl border transition-all ${
              form.interviewer_persona === "bodhi"
                ? "bg-[#37322F] border-[#37322F] text-white"
                : "bg-[#F7F5F3] border-[rgba(55,50,47,0.15)] text-[#37322F] hover:border-[#37322F]"
            }`}
          >
            <div className={`w-10 h-10 rounded-full flex items-center justify-center mb-2 ${
              form.interviewer_persona === "bodhi" ? "bg-[rgba(255,255,255,0.2)]" : "bg-[rgba(55,50,47,0.1)]"
            }`}>
              <span className="text-xl">🧔</span>
            </div>
            <span className="text-sm font-bold">Bodhi</span>
            <span className={`text-[10px] mt-0.5 ${
              form.interviewer_persona === "bodhi" ? "text-[rgba(255,255,255,0.7)]" : "text-[rgba(55,50,47,0.5)]"
            }`}>Tough but Fair</span>
          </button>

          <button
            type="button"
            onClick={() => setForm({ ...form, interviewer_persona: "riya" })}
            className={`flex flex-col items-center p-4 rounded-xl border transition-all ${
              form.interviewer_persona === "riya"
                ? "bg-[#37322F] border-[#37322F] text-white"
                : "bg-[#F7F5F3] border-[rgba(55,50,47,0.15)] text-[#37322F] hover:border-[#37322F]"
            }`}
          >
            <div className={`w-10 h-10 rounded-full flex items-center justify-center mb-2 ${
              form.interviewer_persona === "riya" ? "bg-[rgba(255,255,255,0.2)]" : "bg-[rgba(55,50,47,0.1)]"
            }`}>
              <span className="text-xl">👩‍💼</span>
            </div>
            <span className="text-sm font-bold">Riya</span>
            <span className={`text-[10px] mt-0.5 ${
              form.interviewer_persona === "riya" ? "text-[rgba(255,255,255,0.7)]" : "text-[rgba(55,50,47,0.5)]"
            }`}>Supportive</span>
          </button>
        </div>
      </div>

      <PrimaryButton type="submit" fullWidth loading={loading}>
        Continue →
      </PrimaryButton>
    </form>
  )
}