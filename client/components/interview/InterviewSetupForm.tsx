"use client"

import { useState, useEffect } from "react"
import { useUser } from "@clerk/nextjs"
import { FormInput } from "@/components/ui/form-input"
import { PrimaryButton } from "@/components/ui/primary-button"
import { type CandidateProfile, type CompanyProfile, uploadResume } from "@/lib/api"

interface InterviewSetupFormProps {
  onSubmit: (formData: InterviewFormData) => void
  loading?: boolean
}

export interface InterviewFormData {
  candidate_name: string
  company: string
  role: string
  experience_level: string
  mode: "standard" | "option_a" | "option_b"
  user_id: string
  jd_text: string
  interviewer_persona: "bodhi" | "riya"
}

export function InterviewSetupForm({ onSubmit, loading }: InterviewSetupFormProps) {
  const { user } = useUser()
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState("")
  const [uploadedProfile, setUploadedProfile] = useState<CandidateProfile | null>(null)
  const [checkingProfile, setCheckingProfile] = useState(false)
  const [selectedMode, setSelectedMode] = useState<"company" | "resume">("company")
  const [showJdField, setShowJdField] = useState(false)

  const [companies, setCompanies] = useState<CompanyProfile[]>([])

  useEffect(() => {
    import("@/lib/api").then(api => {
      api.listCompanies().then(setCompanies).catch(console.error)
    })
  }, [])

  const [form, setForm] = useState<InterviewFormData>({
    candidate_name: "",
    company: "",
    role: "Software Engineer",
    experience_level: "Mid-Level",
    mode: "standard",
    user_id: "",
    jd_text: "",
    interviewer_persona: "bodhi",
  })

  // Load user's name from database on mount
  useEffect(() => {
    const loadUserName = async () => {
      try {
        const response = await fetch("/api/users/me/profile", {
          headers: await (async () => {
            const { getAuthHeaders } = await import("@/lib/api")
            return getAuthHeaders()
          })()
        })

        if (response.ok) {
          const data = await response.json()
          if (data.full_name) {
            setForm((prev) => ({
              ...prev,
              candidate_name: data.full_name,
            }))
          } else if (user?.fullName) {
            // Fallback to Clerk name if no database name
            setForm((prev) => ({
              ...prev,
              candidate_name: user.fullName || "",
            }))
          }
        }
      } catch (err) {
        console.log("Could not load user name:", err)
        // Fallback to Clerk name
        if (user?.fullName) {
          setForm((prev) => ({
            ...prev,
            candidate_name: user.fullName || "",
          }))
        }
      }
    }

    loadUserName()
  }, [user])

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

  // Check if user already has a profile when switching to resume mode
  const checkExistingProfile = async () => {
    setCheckingProfile(true)
    setError("")

    try {
      const response = await fetch("/api/users/me/status", {
        headers: await (async () => {
          const { getAuthHeaders } = await import("@/lib/api")
          return getAuthHeaders()
        })()
      })

      if (response.ok) {
        const data = await response.json()

        if (data.has_resume && data.user_id) {
          const { getResumeProfile } = await import("@/lib/api")
          const profile = await getResumeProfile(data.user_id)

          if (profile) {
            setUploadedProfile(profile)
            setForm((prev) => ({
              ...prev,
              user_id: data.user_id,
              candidate_name: profile.name || prev.candidate_name,
            }))
          }
        }
      }
    } catch (err) {
      console.log("No existing profile found:", err)
    } finally {
      setCheckingProfile(false)
    }
  }

  const handleModeSwitch = (mode: "company" | "resume") => {
    setSelectedMode(mode)
    setUploadedProfile(null)
    setError("")
    setShowJdField(false)

    if (mode === "company") {
      setForm((prev) => ({
        ...prev,
        mode: "standard",
        user_id: "",
        jd_text: "",
      }))
    } else {
      setForm((prev) => ({
        ...prev,
        mode: "option_a",
        company: "",
        role: "Software Engineer",
        jd_text: "",
      }))
      checkExistingProfile()
    }
  }

  // When JD field is shown, check if user has resume and switch to option_b mode
  const handleShowJdField = () => {
    setShowJdField(true)
    
    // Check if user has a resume profile
    const checkResumeForJD = async () => {
      try {
        const response = await fetch("/api/users/me/status", {
          headers: await (async () => {
            const { getAuthHeaders } = await import("@/lib/api")
            return getAuthHeaders()
          })()
        })

        if (response.ok) {
          const data = await response.json()

          if (data.has_resume && data.user_id) {
            const { getResumeProfile } = await import("@/lib/api")
            const profile = await getResumeProfile(data.user_id)

            if (profile) {
              // Switch to option_b mode (JD-targeted with resume)
              setForm((prev) => ({
                ...prev,
                mode: "option_b",
                user_id: data.user_id,
                candidate_name: profile.name || prev.candidate_name,
              }))
              setUploadedProfile(profile)
            }
          }
        }
      } catch (err) {
        console.log("No existing profile found for JD mode:", err)
      }
    }

    checkResumeForJD()
  }

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    onSubmit(form)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 animate-fade-in-up">
          {error}
        </div>
      )}

      {/* ── Mode Selection Cards ────────────────────────── */}
      <div>
        <label className="block text-xs font-semibold text-[rgba(55,50,47,0.6)] mb-3 uppercase tracking-wider">
          Interview Mode
        </label>
        <div className="grid grid-cols-2 gap-3">
          <button
            type="button"
            onClick={() => handleModeSwitch("company")}
            className={`flex flex-col items-center p-4 rounded-xl border-2 transition-all duration-200 ${
              selectedMode === "company"
                ? "bg-[#37322F] border-[#37322F] text-white shadow-[0px_4px_16px_rgba(55,50,47,0.25)]"
                : "bg-[#F7F5F3] border-[rgba(55,50,47,0.12)] text-[#37322F] hover:border-[rgba(55,50,47,0.3)] hover:shadow-sm"
            }`}
          >
            <div className={`w-10 h-10 rounded-full flex items-center justify-center mb-2 ${
              selectedMode === "company" ? "bg-[rgba(255,255,255,0.15)]" : "bg-[rgba(55,50,47,0.08)]"
            }`}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
                <polyline points="9 22 9 12 15 12 15 22" />
              </svg>
            </div>
            <span className="text-sm font-bold">Company Based</span>
            <span className={`text-[10px] mt-0.5 ${
              selectedMode === "company" ? "text-[rgba(255,255,255,0.7)]" : "text-[rgba(55,50,47,0.5)]"
            }`}>Target a specific company</span>
          </button>

          <button
            type="button"
            onClick={() => handleModeSwitch("resume")}
            className={`flex flex-col items-center p-4 rounded-xl border-2 transition-all duration-200 ${
              selectedMode === "resume"
                ? "bg-[#37322F] border-[#37322F] text-white shadow-[0px_4px_16px_rgba(55,50,47,0.25)]"
                : "bg-[#F7F5F3] border-[rgba(55,50,47,0.12)] text-[#37322F] hover:border-[rgba(55,50,47,0.3)] hover:shadow-sm"
            }`}
          >
            <div className={`w-10 h-10 rounded-full flex items-center justify-center mb-2 ${
              selectedMode === "resume" ? "bg-[rgba(255,255,255,0.15)]" : "bg-[rgba(55,50,47,0.08)]"
            }`}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
                <polyline points="10 9 9 9 8 9" />
              </svg>
            </div>
            <span className="text-sm font-bold">Resume Based</span>
            <span className={`text-[10px] mt-0.5 ${
              selectedMode === "resume" ? "text-[rgba(255,255,255,0.7)]" : "text-[rgba(55,50,47,0.5)]"
            }`}>Based on your resume</span>
          </button>
        </div>
      </div>

      {/* ── Resume Upload (Resume mode only) ─────────────── */}
      {selectedMode === "resume" && !form.user_id && !checkingProfile && (
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

      {checkingProfile && (
        <div className="rounded-xl border border-[rgba(55,50,47,0.15)] bg-[#F7F5F3] p-4 animate-fade-in-up">
          <p className="text-xs text-[#37322F] flex items-center gap-2">
            <span className="w-3 h-3 border-2 border-[rgba(55,50,47,0.2)] border-t-[#37322F] rounded-full animate-spin" />
            Checking for existing resume...
          </p>
        </div>
      )}

      {selectedMode === "resume" && uploadedProfile && (
        <div className="rounded-xl border border-[rgba(55,50,47,0.15)] bg-[#F7F5F3] p-4 space-y-2 animate-fade-in-up">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-[#37322F] flex items-center gap-2">
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
            {uploadedProfile.skills?.length > 0 && (
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

      {/* ── Name Field (always shown) ────────────────────── */}
      <FormInput
        placeholder="Your name *"
        required
        value={form.candidate_name}
        onChange={(e) => setForm({ ...form, candidate_name: e.target.value })}
      />

      {/* ── Company & Role Fields (Company mode only) ───── */}
      {selectedMode === "company" && (
        <>
          <div className="space-y-1">
            <select
              required
              value={form.company}
              onChange={(e) => {
                 const selected = e.target.value;
                 setForm(prev => {
                    const newState = { ...prev, company: selected };
                    const comp = companies.find(c => c.company_name === selected);
                    if (comp) {
                       newState.role = comp.role;
                       if (comp.experience_level) newState.experience_level = comp.experience_level;
                    }
                    return newState;
                 });
              }}
              className="w-full rounded-xl border border-[rgba(55,50,47,0.15)] bg-[#F7F5F3] px-3 py-3 text-sm text-[#37322F] focus:outline-none focus:ring-2 focus:ring-[rgba(55,50,47,0.15)] transition"
            >
              <option value="" disabled>Select a Company *</option>
              {Array.from(new Set(companies.map(c => c.company_name))).map(cName => (
                <option key={cName} value={cName}>{cName}</option>
              ))}
            </select>
            {companies.length === 0 && (
              <p className="text-xs text-[rgba(55,50,47,0.5)] mt-1">
                No companies found. Create one in the Companies tab.
              </p>
            )}
          </div>
          <FormInput
            placeholder="Role *"
            required
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value })}
          />
          <div className="space-y-1">
            <select
              required
              value={form.experience_level}
              onChange={(e) => setForm({ ...form, experience_level: e.target.value })}
              className="w-full rounded-xl border border-[rgba(55,50,47,0.15)] bg-[#F7F5F3] px-3 py-3 text-sm text-[#37322F] focus:outline-none focus:ring-2 focus:ring-[rgba(55,50,47,0.15)] transition"
            >
              <option value="" disabled>Select Experience Level *</option>
              <option value="Intern">Intern</option>
              <option value="Junior">Junior</option>
              <option value="Mid-Level">Mid-Level</option>
              <option value="Senior">Senior</option>
            </select>
          </div>

          {/* Optional JD toggle + textarea */}
          {!showJdField ? (
            <button
              type="button"
              onClick={handleShowJdField}
              className="flex items-center gap-2 text-xs font-medium text-[rgba(55,50,47,0.55)] hover:text-[#37322F] transition-colors duration-200 group"
            >
              <span className="flex items-center justify-center w-5 h-5 rounded-full border border-[rgba(55,50,47,0.2)] group-hover:border-[#37322F] transition-colors">
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <line x1="5" y1="2" x2="5" y2="8" />
                  <line x1="2" y1="5" x2="8" y2="5" />
                </svg>
              </span>
              Add Job Description (optional)
            </button>
          ) : (
            <div className="animate-fade-in-up">
              <div className="flex items-center justify-between mb-2">
                <label className="block text-xs font-semibold text-[rgba(55,50,47,0.6)] uppercase tracking-wider">
                  Job Description
                  <span className="ml-1 text-[rgba(55,50,47,0.35)] normal-case font-normal">(optional)</span>
                </label>
                <button
                  type="button"
                  onClick={() => {
                    setShowJdField(false)
                    setForm((prev) => ({ ...prev, jd_text: "", mode: "standard", user_id: "" }))
                    setUploadedProfile(null)
                  }}
                  className="text-xs text-[rgba(55,50,47,0.45)] hover:text-[#37322F] transition"
                >
                  Remove
                </button>
              </div>
              {uploadedProfile && (
                <div className="rounded-xl border border-[rgba(55,50,47,0.15)] bg-[#F7F5F3] p-3 mb-3 animate-fade-in-up">
                  <p className="text-xs font-medium text-[#37322F] flex items-center gap-2">
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <path d="M3 7L6 10L11 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    Using your resume profile for JD-targeted interview
                  </p>
                  <p className="text-[10px] text-[rgba(55,50,47,0.5)] mt-1">
                    {uploadedProfile.name} • {uploadedProfile.skills?.length || 0} skills
                  </p>
                </div>
              )}
              <textarea
                placeholder="Paste the job description here to tailor your interview questions..."
                value={form.jd_text}
                onChange={(e) => setForm({ ...form, jd_text: e.target.value })}
                className="w-full min-h-28 rounded-xl border border-[rgba(55,50,47,0.15)] bg-[#F7F5F3] px-3 py-2.5 text-sm text-[#37322F] placeholder-[rgba(55,50,47,0.4)] focus:outline-none focus:ring-2 focus:ring-[rgba(55,50,47,0.15)] transition resize-y"
              />
            </div>
          )}
        </>
      )}

      {/* ── Interviewer Persona Selection ─────────────────── */}
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