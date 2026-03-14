"use client"

import { useState } from "react"
import { Building2, Briefcase, Code, Sparkles, User } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { type CompanyProfile } from "@/lib/api"

interface CompanyBentoGridProps {
  companies: CompanyProfile[]
  onDelete: (company: CompanyProfile) => void
}

export function CompanyBentoGrid({ companies, onDelete }: CompanyBentoGridProps) {
  const [activeCompany, setActiveCompany] = useState<CompanyProfile | null>(null)
  const [isOpen, setIsOpen] = useState(false)

  const getCompanyIcon = (index: number) => {
    const icons = [User, Building2, Briefcase, Code, Sparkles]
    const Icon = icons[index % icons.length]
    return <Icon className="w-8 h-8 stroke-1 text-muted-foreground" />
  }

  const isPremiumCard = (index: number) => index % 4 === 0

  const handleOpen = (company: CompanyProfile) => {
    setActiveCompany(company)
    setIsOpen(true)
  }

  return (
    <>
      <div
        className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-6"
        style={{ animationDelay: "0.2s" }}
      >
      {companies.map((company, index) => (
        <div
          key={`${company.company_name}-${company.role}`}
          role="button"
          tabIndex={0}
          onClick={() => handleOpen(company)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault()
              handleOpen(company)
            }
          }}
          className={`group relative cursor-pointer rounded-2xl border border-white/40 p-6 min-h-[240px] flex flex-col justify-between transition-all duration-300 shadow-[0px_10px_30px_rgba(30,30,30,0.08)] backdrop-blur-xl outline-none focus:ring-2 focus:ring-black/10 hover:-translate-y-1 hover:shadow-[0px_18px_40px_rgba(30,30,30,0.12)] ${
            isPremiumCard(index)
              ? "bg-gradient-to-br from-white/80 via-white/55 to-white/35"
              : "bg-white/55"
          }`}
        >
          {/* Delete button */}
          <button
            onClick={(event) => {
              event.stopPropagation()
              onDelete(company)
            }}
            className="absolute top-4 right-4 w-8 h-8 rounded-full bg-white/80 text-destructive opacity-0 group-hover:opacity-100 transition-all duration-200 hover:bg-white hover:scale-105 flex items-center justify-center"
            aria-label="Delete company"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
            </svg>
          </button>

          {/* Icon */}
          <div className="transition-transform duration-300 group-hover:scale-110 group-hover:rotate-3">
            {getCompanyIcon(index)}
          </div>

          {/* Content */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <h3 className="text-xl font-semibold tracking-tight text-foreground">
              {company.company_name}
              </h3>
              {isPremiumCard(index) && <Badge>Premium</Badge>}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary">{company.role}</Badge>
            </div>
            {company.description && (
              <p className="text-muted-foreground text-sm leading-relaxed line-clamp-2">
                {company.description}
              </p>
            )}
            {company.hiring_patterns && (
              <p className="text-muted-foreground text-xs leading-relaxed line-clamp-2">
                Hiring patterns: {company.hiring_patterns}
              </p>
            )}
            {company.tech_stack && (
              <div className="mt-2 flex flex-wrap gap-1">
                {company.tech_stack.split(",").slice(0, 3).map((tech, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-medium text-muted-foreground"
                  >
                    {tech.trim()}
                  </span>
                ))}
                {company.tech_stack.split(",").length > 3 && (
                  <span className="inline-flex items-center rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                    +{company.tech_stack.split(",").length - 3}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      ))}
      </div>

      <Dialog
        open={isOpen}
        onOpenChange={(open) => {
          setIsOpen(open)
          if (!open) setActiveCompany(null)
        }}
      >
        <DialogContent className="max-w-2xl rounded-2xl border border-white/60 bg-white/90 p-6 shadow-[0px_20px_60px_rgba(30,30,30,0.18)] backdrop-blur-xl">
          {activeCompany && (
            <DialogHeader className="gap-3">
              <DialogTitle className="text-2xl font-semibold text-foreground">
                {activeCompany.company_name}
              </DialogTitle>
              <DialogDescription className="text-sm text-muted-foreground">
                {activeCompany.role}
              </DialogDescription>

              <div className="space-y-4 text-sm text-muted-foreground">
                {activeCompany.description && (
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-foreground/70">
                      Description
                    </p>
                    <p className="mt-1 leading-relaxed text-foreground/80">
                      {activeCompany.description}
                    </p>
                  </div>
                )}

                {activeCompany.hiring_patterns && (
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-foreground/70">
                      Hiring Patterns
                    </p>
                    <p className="mt-1 leading-relaxed text-foreground/80">
                      {activeCompany.hiring_patterns}
                    </p>
                  </div>
                )}

                {activeCompany.tech_stack && (
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-foreground/70">
                      Tech Stack
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {activeCompany.tech_stack.split(",").map((tech, i) => (
                        <span
                          key={`${tech}-${i}`}
                          className="rounded-full bg-white/70 px-3 py-1 text-xs font-medium text-foreground/80"
                        >
                          {tech.trim()}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </DialogHeader>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
