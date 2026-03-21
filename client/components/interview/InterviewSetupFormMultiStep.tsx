"use client"

import { useState } from "react"
import { MultiStepForm } from "@/components/ui/multi-step-form"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { AlertTriangle, Info, Globe, ArrowUpRight, Briefcase, User } from "lucide-react"
import { type CandidateProfile, uploadResume } from "@/lib/api"

export interface InterviewFormData {
  candidate_name: string
  company: string
  role: string
  mode: "standard" | "option_a"
  user_id: string
  jd_text: string
}

interface InterviewSetupFormMultiStepProps {
  onSubmit: (formData: InterviewFormData) => void
  loading?: boolean
}

const TooltipIcon = ({ text }: { text: string }) => (
  <TooltipProvider>
    <Tooltip>
      <TooltipTrigger asChild>
        <Info className="h-4 w-4 text-muted-foreground cursor-pointer" />
      </TooltipTrigger>
      <TooltipContent>
        <p>{text}</p>
      </TooltipContent>
    </Tooltip>
  </TooltipProvider>
)

export function InterviewSetupFormMultiStep({
  onSubmit,
  loading,
}: InterviewSetupFormMultiStepProps) {
  const [currentStep, setCurrentStep] = useState(1)
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
  })

  const totalSteps = 2

  const handleNext = () => {
    // Validation for each step
    if (currentStep === 1) {
      if (!form.mode) {
        setError("Please select an interview mode")
        return
      }
      if (form.mode === "option_a" && !form.user_id) {
        setError("Please upload your resume to continue")
        return
      }
    }

    if (currentStep === 2) {
      if (!form.candidate_name) {
        setError("Please enter your name")
        return
      }
      if (form.mode === "standard" && (!form.company || !form.role)) {
        setError("Please fill in all required fields")
        return
      }
    }



    setError("")

    if (currentStep < totalSteps) {
      setCurrentStep(currentStep + 1)
    } else {
      onSubmit(form)
    }
  }

  const handleBack = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1)
      setError("")
    }
  }

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

  return (
    <div className="flex h-full w-full items-center justify-center bg-background p-4">
      <MultiStepForm
        currentStep={currentStep}
        totalSteps={totalSteps}
        title="Mock Interview"
        description="Hands-free voice conversation. Speak naturally — Bodhi listens, responds, and loops."
        onBack={handleBack}
        onNext={handleNext}
        nextButtonText={currentStep === totalSteps ? "Continue →" : "Next Step"}
        footerContent={
          <a
            href="#"
            className="flex items-center gap-1 text-sm text-primary hover:underline"
          >
            Need Help? <ArrowUpRight className="h-4 w-4" />
          </a>
        }
      >
        {/* Step 1: Interview Mode Selection */}
        {currentStep === 1 && (
          <div className="space-y-6">
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Label htmlFor="mode">Interview Mode</Label>
                <TooltipIcon text="Choose how you want to prepare for your interview" />
              </div>
              <Select
                value={form.mode}
                onValueChange={(value) => {
                  setForm({
                    ...form,
                    mode: value as "standard" | "option_a",
                  })
                  setUploadedProfile(null)
                  setError("")
                }}
              >
                <SelectTrigger id="mode" className="w-full">
                  <Briefcase className="h-4 w-4 mr-2 text-muted-foreground" />
                  <SelectValue placeholder="Select interview mode..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="standard">Company-Based</SelectItem>
                  <SelectItem value="option_a">Resume-Based</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {form.mode === "option_a" && !form.user_id && (
              <div className="space-y-2 animate-fade-in-up">
                <div className="flex items-center gap-2">
                  <Label htmlFor="resume">Upload Resume</Label>
                  <TooltipIcon text="Upload your resume in PDF or DOCX format" />
                </div>
                <Input
                  id="resume"
                  type="file"
                  accept=".pdf,.docx"
                  onChange={handleResumeUpload}
                  disabled={uploading}
                />
                {uploading && (
                  <p className="text-xs text-muted-foreground flex items-center gap-2">
                    <span className="w-3 h-3 border-2 border-muted-foreground/30 border-t-foreground rounded-full animate-spin" />
                    Uploading and parsing resume...
                  </p>
                )}
              </div>
            )}

            {form.mode === "option_a" && uploadedProfile && (
              <Alert className="border-[rgba(55,50,47,0.15)] bg-[#F7F5F3]">
                <AlertDescription>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium text-[#37322F]">
                        Resume uploaded successfully
                      </p>
                      <button
                        type="button"
                        onClick={() => {
                          setUploadedProfile(null)
                          setForm((p) => ({ ...p, user_id: "" }))
                        }}
                        className="text-xs text-muted-foreground hover:text-foreground transition"
                      >
                        Change
                      </button>
                    </div>
                    <div className="text-xs">
                      <p className="font-medium">{uploadedProfile.name}</p>
                      {uploadedProfile.email && (
                        <p className="text-muted-foreground">{uploadedProfile.email}</p>
                      )}
                      {uploadedProfile.skills.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {uploadedProfile.skills.slice(0, 5).map((s, i) => (
                            <span
                              key={i}
                              className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium"
                            >
                              {s}
                            </span>
                          ))}
                          {uploadedProfile.skills.length > 5 && (
                            <span className="text-[10px] text-muted-foreground">
                              +{uploadedProfile.skills.length - 5} more
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </AlertDescription>
              </Alert>
            )}

            {error && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </div>
        )}

        {/* Step 2: Personal & Company Details */}
        {currentStep === 2 && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
              <div className="space-y-2 md:col-span-2">
                <div className="flex items-center gap-2">
                  <Label htmlFor="name">Your Name</Label>
                  <TooltipIcon text="Enter your full name as it should appear in the interview" />
                </div>
                <Input
                  id="name"
                  placeholder="Enter your name"
                  value={form.candidate_name}
                  onChange={(e) =>
                    setForm({ ...form, candidate_name: e.target.value })
                  }
                />
              </div>

              {form.mode === "standard" && (
                <>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Label htmlFor="company">Company</Label>
                      <TooltipIcon text="The company you're interviewing with" />
                    </div>
                    <Input
                      id="company"
                      placeholder="Enter company name"
                      value={form.company}
                      onChange={(e) =>
                        setForm({ ...form, company: e.target.value })
                      }
                    />
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Label htmlFor="role">Role</Label>
                      <TooltipIcon text="The position you're applying for" />
                    </div>
                    <Input
                      id="role"
                      placeholder="e.g. Software Engineer"
                      value={form.role}
                      onChange={(e) => setForm({ ...form, role: e.target.value })}
                    />
                  </div>
                </>
              )}
            </div>

            {error && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </div>
        )}

        {/* Step 2 no longer has a step 3 for JD - JD is optional in company/standard step 2 */}

      </MultiStepForm>
    </div>
  )
}
