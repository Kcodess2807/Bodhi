"use client"

import { Building2, Briefcase, Code, User, Trash2, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { type CompanyProfile } from "@/lib/api"

interface CompanyDetailProps {
  company: CompanyProfile
  index: number
  onDelete: (company: CompanyProfile) => void
  onClose: () => void
}

export function CompanyDetail({ company, index, onDelete, onClose }: CompanyDetailProps) {
  const isPremiumCard = (index: number) => index % 4 === 0

  return (
    <div className="bg-white rounded-3xl shadow-[0px_20px_80px_rgba(0,0,0,0.25)] overflow-hidden">
      {/* Header Section */}
      <div className="relative px-8 pt-8 pb-6 bg-gradient-to-br from-[#FAFAFA] via-white to-[#F7F5F3]">
        <button
          onClick={onClose}
          className="absolute top-6 right-6 w-10 h-10 rounded-full hover:bg-[rgba(55,50,47,0.06)] transition-all flex items-center justify-center group"
        >
          <X className="w-5 h-5 text-[rgba(55,50,47,0.4)] group-hover:text-[rgba(55,50,47,0.8)] transition-colors" />
        </button>

        <div className="flex items-start gap-5 pr-12">
          
          <div className="space-y-3 flex-1 min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <h2 className="text-3xl font-bold tracking-tight text-[#2F3037]">
                {company.company_name}
              </h2>
              {isPremiumCard(index) && (
                <Badge className="text-xs bg-gradient-to-r from-[#37322F] to-[#2A2624] text-white border-0 px-3 py-1">
                  Premium
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Briefcase className="w-4 h-4 text-[rgba(55,50,47,0.4)]" />
              <span className="text-base text-[rgba(55,50,47,0.7)] font-medium">
                {company.role}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Content Section - Scrollable */}
      <div className="overflow-y-auto max-h-[calc(85vh-240px)] px-8 py-6 bg-gradient-to-b from-white to-[#FAFAFA]">
        <div className="space-y-6">
          {/* Description Section */}
          {company.description && (
            <div className="group">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#37322F]/10 to-[#2A2624]/10 flex items-center justify-center">
                  <Building2 className="w-4 h-4 text-[#37322F]" />
                </div>
                <h3 className="text-sm font-bold uppercase tracking-wider text-[#37322F]">
                  Description
                </h3>
              </div>
              <div className="pl-10">
                <p className="text-[rgba(55,50,47,0.8)] leading-relaxed text-[15px]">
                  {company.description}
                </p>
              </div>
            </div>
          )}

          {/* Divider */}
          {company.description && company.hiring_patterns && (
            <div className="border-t border-[rgba(55,50,47,0.08)]" />
          )}

          {/* Hiring Patterns Section */}
          {company.hiring_patterns && (
            <div className="group">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#37322F]/10 to-[#2A2624]/10 flex items-center justify-center">
                  <User className="w-4 h-4 text-[#37322F]" />
                </div>
                <h3 className="text-sm font-bold uppercase tracking-wider text-[#37322F]">
                  Hiring Patterns
                </h3>
              </div>
              <div className="pl-10">
                <p className="text-[rgba(55,50,47,0.8)] leading-relaxed text-[15px]">
                  {company.hiring_patterns}
                </p>
              </div>
            </div>
          )}

          {/* Divider */}
          {company.hiring_patterns && company.tech_stack && (
            <div className="border-t border-[rgba(55,50,47,0.08)]" />
          )}

          {/* Tech Stack Section */}
          {company.tech_stack && (
            <div className="group">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#37322F]/10 to-[#2A2624]/10 flex items-center justify-center">
                  <Code className="w-4 h-4 text-[#37322F]" />
                </div>
                <h3 className="text-sm font-bold uppercase tracking-wider text-[#37322F]">
                  Tech Stack
                </h3>
              </div>
              <div className="pl-10">
                <div className="flex flex-wrap gap-2">
                  {company.tech_stack.split(",").map((tech, i) => (
                    <span
                      key={`${tech}-${i}`}
                      className="rounded-lg bg-white border-2 border-[rgba(55,50,47,0.08)] px-3 py-1.5 text-sm font-medium text-[#2F3037] shadow-sm hover:border-[rgba(55,50,47,0.15)] hover:shadow-md transition-all"
                    >
                      {tech.trim()}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Footer with Delete Button */}
      <div className="px-8 py-6 border-t border-[rgba(55,50,47,0.08)] bg-gradient-to-br from-[#FAFAFA] to-white">
        <button
          onClick={() => onDelete(company)}
          className="w-full flex items-center justify-center gap-2 px-4 py-3.5 rounded-xl bg-white text-red-600 hover:bg-red-50 transition-all font-semibold border-2 border-red-200 hover:border-red-300 shadow-sm hover:shadow-md"
        >
          <Trash2 className="w-4 h-4" />
          <span>Delete Company Profile</span>
        </button>
      </div>
    </div>
  )
}

