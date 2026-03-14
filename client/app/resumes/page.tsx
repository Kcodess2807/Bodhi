"use client"

import Link from "next/link"
import { useState, useEffect } from "react"
import Navbar from "@/components/Navbar"
import { StatusMessage } from "@/components/ui/status-message"
import { PrimaryButton } from "@/components/ui/primary-button"
import { uploadResume, getCurrentUserStatus, getResumeProfile, type CandidateProfile } from "@/lib/api"

type UploadResult = {
  user_id: string
  profile: CandidateProfile
}

export default function ResumesPage() {
  const [uploading, setUploading] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [result, setResult] = useState<UploadResult | null>(null)
  const [existingProfile, setExistingProfile] = useState<CandidateProfile | null>(null)
  const [userId, setUserId] = useState<string | null>(null)

  // Load existing resume on mount
  useEffect(() => {
    const loadExistingResume = async () => {
      try {
        const status = await getCurrentUserStatus()
        if (status.has_resume && status.user_id) {
          setUserId(status.user_id)
          const profile = await getResumeProfile(status.user_id)
          setExistingProfile(profile)
        }
      } catch (err) {
        console.error("Failed to load existing resume:", err)
      } finally {
        setLoading(false)
      }
    }
    loadExistingResume()
  }, [])

  const handleUpload = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formEl = e.currentTarget
    const fileInput = formEl.elements.namedItem("file") as HTMLInputElement
    const file = fileInput.files?.[0]

    if (!file) {
      setError("Please select a file")
      return
    }

    setUploading(true)
    setError("")
    setResult(null)

    try {
      const res = await uploadResume(file)
      setResult(res)
      setExistingProfile(res.profile)
      setUserId(res.user_id)
      formEl.reset()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload resume")
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#F7F5F3] font-sans relative overflow-hidden">
      {/* Animated Grid Background */}
      <div className="absolute inset-0 opacity-[0.03] pointer-events-none">
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: `
              linear-gradient(to right, #37322F 1px, transparent 1px),
              linear-gradient(to bottom, #37322F 1px, transparent 1px)
            `,
            backgroundSize: "60px 60px",
          }}
        />
      </div>

      {/* Gradient Orbs */}
      <div className="absolute top-0 left-1/4 w-96 h-96 bg-[#E8E3DF] rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-float" />
      <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-[#DED9D5] rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-float" style={{ animationDelay: "2s" }} />

      <Navbar />

      <main className="relative pt-24 pb-16 px-4 sm:px-6 max-w-4xl mx-auto space-y-8">
        {/* Modern Header Section */}
        <div className="text-center mb-12 animate-fade-in-up">
          <h1 className="text-5xl sm:text-6xl font-bold text-[#2F3037] mb-4 tracking-tight">
            Resume Management
          </h1>
          <p className="text-lg text-[rgba(55,50,47,0.65)] max-w-2xl mx-auto leading-relaxed">
            Upload your resume to create a profile for resume-based and JD-targeted interviews.
          </p>
        </div>

        {error && <StatusMessage message={error} type="error" />}

        {/* My Resume Section - Show if exists */}
        {!loading && existingProfile && (
          <div className="animate-fade-in-up" style={{ animationDelay: "0.1s" }}>
            <h2 className="text-3xl font-bold text-[#2F3037] mb-6 tracking-tight">My Resume</h2>
            <div className="space-y-5 rounded-2xl border-2 border-[rgba(55,50,47,0.08)] bg-white/70 backdrop-blur-sm p-8 shadow-[0px_8px_24px_rgba(55,50,47,0.08)]">
              {existingProfile.name && (
                <Field label="Name" value={existingProfile.name} />
              )}
              {existingProfile.email && (
                <Field label="Email" value={existingProfile.email} />
              )}
              {existingProfile.summary && (
                <Field
                  label="Summary"
                  value={existingProfile.summary}
                  paragraph
                />
              )}

              {existingProfile.skills.length > 0 && (
                <div>
                  <FieldLabel>Skills</FieldLabel>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {existingProfile.skills.map((skill, i) => (
                      <span
                        key={i}
                        className="rounded-full bg-[rgba(55,50,47,0.07)] px-3 py-1 text-xs text-[#37322F] font-medium transition-all duration-200 hover:bg-[rgba(55,50,47,0.12)]"
                      >
                        {skill}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {existingProfile.experience.length > 0 && (
                <div>
                  <FieldLabel>Experience</FieldLabel>
                  <div className="space-y-3 mt-2">
                    {existingProfile.experience.map((exp, i) => (
                      <div
                        key={i}
                        className="rounded-xl bg-[rgba(55,50,47,0.04)] border border-[rgba(55,50,47,0.07)] p-4 transition-all duration-200 hover:border-[rgba(55,50,47,0.12)] hover:shadow-sm"
                      >
                        <p className="text-sm font-semibold text-[#37322F]">
                          {exp.title}
                        </p>
                        <p className="text-xs text-[rgba(55,50,47,0.5)] mt-0.5">
                          {exp.company} · {exp.duration}
                        </p>
                        <p className="mt-2 text-xs text-[rgba(55,50,47,0.7)] leading-5">
                          {exp.description}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {existingProfile.education.length > 0 && (
                <div>
                  <FieldLabel>Education</FieldLabel>
                  <div className="space-y-2 mt-2">
                    {existingProfile.education.map((edu, i) => (
                      <div key={i}>
                        <p className="text-sm font-semibold text-[#37322F]">
                          {edu.degree}
                        </p>
                        <p className="text-xs text-[rgba(55,50,47,0.5)]">
                          {edu.institution} · {edu.year}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {existingProfile.projects && existingProfile.projects.length > 0 && (
                <div>
                  <FieldLabel>Projects</FieldLabel>
                  <div className="space-y-3 mt-2">
                    {existingProfile.projects.map((project, i) => (
                      <div
                        key={i}
                        className="rounded-xl bg-[rgba(55,50,47,0.04)] border border-[rgba(55,50,47,0.07)] p-4 transition-all duration-200 hover:border-[rgba(55,50,47,0.12)] hover:shadow-sm"
                      >
                        <p className="text-sm font-semibold text-[#37322F]">
                          {project.name}
                        </p>
                        <p className="mt-2 text-xs text-[rgba(55,50,47,0.7)] leading-5">
                          {project.description}
                        </p>
                        {project.technologies.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            {project.technologies.map((tech, j) => (
                              <span
                                key={j}
                                className="rounded-full bg-[rgba(55,50,47,0.07)] px-2 py-0.5 text-xs text-[#37322F] font-medium"
                              >
                                {tech}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Interview CTAs for existing resume */}
              {userId && (
                <div className="flex flex-col sm:flex-row gap-3 pt-6 border-t border-[rgba(55,50,47,0.10)]">
                  <Link
                    href={`/interview?mode=option_a&user_id=${userId}`}
                    className="flex-1 rounded-xl bg-gradient-to-r from-[#37322F] to-[#2A2624] py-3.5 text-center text-sm font-semibold text-white
                      transition-all duration-200 hover:from-[#2A2624] hover:to-[#1F1C1A] hover:shadow-[0px_6px_20px_rgba(55,50,47,0.3)]
                      hover:scale-[1.02] active:scale-[0.98]"
                  >
                    Resume-Based Interview →
                  </Link>
                  <Link
                    href={`/interview?mode=option_b&user_id=${userId}`}
                    className="flex-1 rounded-xl border-2 border-[rgba(55,50,47,0.15)] bg-white py-3.5 text-center text-sm font-semibold text-[#37322F]
                      transition-all duration-200 hover:border-[rgba(55,50,47,0.25)] hover:shadow-[0px_4px_16px_rgba(55,50,47,0.12)]
                      hover:scale-[1.02] active:scale-[0.98]"
                  >
                    JD-Targeted Interview →
                  </Link>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Upload Form Section */}
        <div className="animate-fade-in-up" style={{ animationDelay: existingProfile ? "0.2s" : "0.1s" }}>
          <h2 className="text-3xl font-bold text-[#2F3037] mb-6 tracking-tight">
            {existingProfile ? "Upload New Resume" : "Upload Resume"}
          </h2>
          <form
            onSubmit={handleUpload}
            className="space-y-5 rounded-2xl border-2 border-[rgba(55,50,47,0.08)] bg-white/70 backdrop-blur-sm p-8 shadow-[0px_8px_24px_rgba(55,50,47,0.08)]"
          >
            <div>
              <label className="mb-3 block text-sm font-semibold text-[#37322F]">
                Resume File{" "}
                <span className="text-[rgba(55,50,47,0.45)] font-normal">
                  (PDF or DOCX)
                </span>
              </label>
              <input
                type="file"
                name="file"
                accept=".pdf,.docx"
                disabled={uploading}
                className="w-full rounded-xl border-2 border-[rgba(55,50,47,0.12)] bg-white px-4 py-3.5 text-sm text-[#37322F]
                  file:mr-4 file:py-2 file:px-5 file:rounded-full file:border-0
                  file:bg-gradient-to-r file:from-[#37322F] file:to-[#2A2624] file:text-white file:text-xs file:font-semibold
                  hover:file:from-[#2A2624] hover:file:to-[#1F1C1A] hover:file:shadow-lg
                  focus:outline-none focus:ring-4 focus:ring-[#37322F]/10 focus:border-[#37322F]
                  disabled:opacity-50 transition-all"
              />
            </div>

            <PrimaryButton type="submit" fullWidth loading={uploading} disabled={uploading}>
              {uploading ? "Uploading & Parsing…" : "Upload Resume"}
            </PrimaryButton>
          </form>
        </div>

        {/* Result */}
        {result && (
          <div className="space-y-6 animate-fade-in-up" style={{ animationDelay: "0.3s" }}>
            {/* Success header */}
            <div className="rounded-2xl border-2 border-[rgba(55,50,47,0.08)] bg-white/70 backdrop-blur-sm p-6 shadow-[0px_8px_24px_rgba(55,50,47,0.08)]">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-5 h-5 rounded-full bg-[#37322F] flex items-center justify-center shrink-0">
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                    <path
                      d="M2 5L4 7L8 3"
                      stroke="white"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </div>
                <span className="font-semibold text-[#37322F] text-sm">
                  Resume uploaded successfully
                </span>
              </div>
              <p className="text-xs text-[rgba(55,50,47,0.55)] mb-2">
                User ID for resume-based interviews:
              </p>
              <div className="rounded-xl bg-[#F7F5F3] border border-[rgba(55,50,47,0.10)] px-3 py-2 font-mono text-sm text-[#37322F] break-all">
                {result.user_id}
              </div>
            </div>

            {/* Extracted profile */}
            <div className="space-y-5 rounded-2xl border-2 border-[rgba(55,50,47,0.08)] bg-white/70 backdrop-blur-sm p-8 shadow-[0px_8px_24px_rgba(55,50,47,0.08)]">
              <h3 className="text-xl font-bold text-[#2F3037] tracking-tight">
                Extracted Profile
              </h3>

              {result.profile.name && (
                <Field label="Name" value={result.profile.name} />
              )}
              {result.profile.email && (
                <Field label="Email" value={result.profile.email} />
              )}
              {result.profile.summary && (
                <Field
                  label="Summary"
                  value={result.profile.summary}
                  paragraph
                />
              )}

              {result.profile.skills.length > 0 && (
                <div>
                  <FieldLabel>Skills</FieldLabel>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {result.profile.skills.map((skill, i) => (
                      <span
                        key={i}
                        className="rounded-full bg-[rgba(55,50,47,0.07)] px-3 py-1 text-xs text-[#37322F] font-medium transition-all duration-200 hover:bg-[rgba(55,50,47,0.12)]"
                      >
                        {skill}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {result.profile.experience.length > 0 && (
                <div>
                  <FieldLabel>Experience</FieldLabel>
                  <div className="space-y-3 mt-2">
                    {result.profile.experience.map((exp, i) => (
                      <div
                        key={i}
                        className="rounded-xl bg-[rgba(55,50,47,0.04)] border border-[rgba(55,50,47,0.07)] p-4 transition-all duration-200 hover:border-[rgba(55,50,47,0.12)] hover:shadow-sm"
                      >
                        <p className="text-sm font-semibold text-[#37322F]">
                          {exp.title}
                        </p>
                        <p className="text-xs text-[rgba(55,50,47,0.5)] mt-0.5">
                          {exp.company} · {exp.duration}
                        </p>
                        <p className="mt-2 text-xs text-[rgba(55,50,47,0.7)] leading-5">
                          {exp.description}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {result.profile.education.length > 0 && (
                <div>
                  <FieldLabel>Education</FieldLabel>
                  <div className="space-y-2 mt-2">
                    {result.profile.education.map((edu, i) => (
                      <div key={i}>
                        <p className="text-sm font-semibold text-[#37322F]">
                          {edu.degree}
                        </p>
                        <p className="text-xs text-[rgba(55,50,47,0.5)]">
                          {edu.institution} · {edu.year}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Interview CTAs */}
            <div className="flex flex-col sm:flex-row gap-3">
              <Link
                href={`/interview?mode=option_a&user_id=${result.user_id}`}
                className="flex-1 rounded-xl bg-gradient-to-r from-[#37322F] to-[#2A2624] py-3.5 text-center text-sm font-semibold text-white
                  transition-all duration-200 hover:from-[#2A2624] hover:to-[#1F1C1A] hover:shadow-[0px_6px_20px_rgba(55,50,47,0.3)]
                  hover:scale-[1.02] active:scale-[0.98]"
              >
                Resume-Based Interview →
              </Link>
              <Link
                href={`/interview?mode=option_b&user_id=${result.user_id}`}
                className="flex-1 rounded-xl border-2 border-[rgba(55,50,47,0.15)] bg-white py-3.5 text-center text-sm font-semibold text-[#37322F]
                  transition-all duration-200 hover:border-[rgba(55,50,47,0.25)] hover:shadow-[0px_4px_16px_rgba(55,50,47,0.12)]
                  hover:scale-[1.02] active:scale-[0.98]"
              >
                JD-Targeted Interview →
              </Link>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

// ── Small reusable field components ────────────────────────────────────────

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-xs font-semibold text-[rgba(55,50,47,0.45)] uppercase tracking-wider">
      {children}
    </p>
  )
}

function Field({
  label,
  value,
  paragraph = false,
}: {
  label: string
  value: string
  paragraph?: boolean
}) {
  return (
    <div>
      <FieldLabel>{label}</FieldLabel>
      <p
        className={`mt-1 text-sm text-[#37322F] ${paragraph ? "leading-6 text-[rgba(55,50,47,0.8)]" : ""}`}
      >
        {value}
      </p>
    </div>
  )
}
