"use client"

import { useEffect, useState, useMemo } from "react"
import { Plus, X, Search, Building2, Briefcase, Code } from "lucide-react"
import Navbar from "@/components/Navbar"
import { StatusMessage } from "@/components/ui/status-message"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { CompanyDetail } from "@/components/companies/CompanyDetail"
import { cn } from "@/lib/utils"
import {
  type CompanyProfile,
  listCompanies,
  createCompany,
  deleteCompany,
} from "@/lib/api"

export default function CompaniesPage() {
  const [companies, setCompanies] = useState<CompanyProfile[]>([])
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState("")
  const [msgType, setMsgType] = useState<"success" | "error">("success")
  const [selectedCompany, setSelectedCompany] = useState<CompanyProfile | null>(null)
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")

  const [form, setForm] = useState({
    company_name: "",
    role: "general",
    description: "",
    hiring_patterns: "",
    tech_stack: "",
  })

  const load = () => {
    setLoading(true)
    listCompanies()
      .then(setCompanies)
      .catch((e) => {
        setMsg(String(e))
        setMsgType("error")
      })
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setMsg("")
    try {
      await createCompany(form)
      setForm({
        company_name: "",
        role: "general",
        description: "",
        hiring_patterns: "",
        tech_stack: "",
      })
      load()
      setMsg("Company profile created successfully")
      setMsgType("success")
      setIsFormOpen(false)
    } catch (err) {
      setMsg(String(err))
      setMsgType("error")
    }
  }

  const handleDelete = async (company: CompanyProfile) => {
    try {
      await deleteCompany(company.company_name, company.role)
      if (
        selectedCompany &&
        selectedCompany.company_name === company.company_name &&
        selectedCompany.role === company.role
      ) {
        setSelectedCompany(null)
      }
      load()
    } catch (err) {
      setMsg(String(err))
      setMsgType("error")
    }
  }

  const handleSelectCompany = (company: CompanyProfile) => {
    setSelectedCompany(company)
  }

  const handleCloseDetail = () => {
    setSelectedCompany(null)
  }

  // Filter companies based on search query
  const filteredCompanies = useMemo(() => {
    if (!searchQuery.trim()) return companies
    const query = searchQuery.toLowerCase()
    return companies.filter(
      (company) =>
        company.company_name.toLowerCase().includes(query) ||
        company.role.toLowerCase().includes(query) ||
        company.tech_stack?.toLowerCase().includes(query) ||
        company.description?.toLowerCase().includes(query)
    )
  }, [companies, searchQuery])

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

      <main className="relative pt-24 pb-16 px-4 sm:px-6 lg:px-10 w-full max-w-7xl mx-auto">
        {/* Header Section */}
        <div className="text-center mb-12 animate-fade-in-up">
          <h1 className="text-5xl sm:text-6xl font-bold text-[#2F3037] mb-4 tracking-tight">
            Company Profiles
          </h1>
          <p className="text-lg text-[rgba(55,50,47,0.65)] max-w-2xl mx-auto leading-relaxed">
            Build your target company database and tailor your interview prep to their culture, tech stack, and hiring patterns.
          </p>
        </div>

        {msg && <StatusMessage message={msg} type={msgType} />}

        {/* Search Bar */}
        <div className="mb-8 animate-fade-in-up" style={{ animationDelay: "0.1s" }}>
          <div className="relative max-w-2xl mx-auto">
            <Search className="absolute left-5 top-1/2 -translate-y-1/2 w-5 h-5 text-[rgba(55,50,47,0.4)]" />
            <input
              type="text"
              placeholder="Search companies, roles, or tech stack..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-14 pr-6 py-4 rounded-2xl border-2 border-[rgba(55,50,47,0.08)] bg-white/80 backdrop-blur-sm text-[#2F3037] placeholder:text-[rgba(55,50,47,0.35)] focus:outline-none focus:ring-4 focus:ring-[#37322F]/10 focus:border-[#37322F] transition-all font-sans text-[15px] shadow-[0px_4px_16px_rgba(55,50,47,0.04)]"
            />
          </div>
        </div>

        {/* Companies Grid */}
        <div className="animate-fade-in-up" style={{ animationDelay: "0.2s" }}>
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <LoadingSpinner />
            </div>
          ) : filteredCompanies.length === 0 ? (
            <div className="text-center py-20">
              <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-[rgba(55,50,47,0.06)] mb-6">
                <Building2 className="w-10 h-10 text-[rgba(55,50,47,0.3)]" />
              </div>
              <h3 className="text-xl font-semibold text-[#37322F] mb-2">
                {searchQuery ? "No companies found" : "No companies yet"}
              </h3>
              <p className="text-[rgba(55,50,47,0.6)] mb-6">
                {searchQuery
                  ? "Try adjusting your search terms"
                  : "Click the + button to add your first company profile"}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {filteredCompanies.map((company, index) => (
                <div
                  key={`${company.company_name}-${company.role}`}
                  className="group relative bg-white/70 backdrop-blur-sm rounded-2xl border-2 border-[rgba(55,50,47,0.08)] p-7 hover:border-[rgba(55,50,47,0.15)] transition-all duration-300 hover:shadow-[0px_8px_32px_rgba(55,50,47,0.12)] hover:-translate-y-1 cursor-pointer animate-fade-in-up"
                  style={{ animationDelay: `${0.3 + index * 0.05}s` }}
                  onClick={() => handleSelectCompany(company)}
                >
                  {/* Company Icon */}
                  <div className="w-16 h-16 rounded-xl bg-gradient-to-br from-[#37322F] to-[#2A2624] flex items-center justify-center mb-5 group-hover:scale-110 transition-transform shadow-lg">
                    <span className="text-2xl font-bold text-white">
                      {company.company_name.charAt(0).toUpperCase()}
                    </span>
                  </div>

                  {/* Company Name */}
                  <h3 className="text-2xl font-bold text-[#2F3037] mb-3 group-hover:text-[#37322F] transition-colors">
                    {company.company_name}
                  </h3>

                  {/* Role */}
                  <div className="flex items-center gap-2 mb-4">
                    <Briefcase className="w-4 h-4 text-[rgba(55,50,47,0.4)]" />
                    <span className="text-sm text-[rgba(55,50,47,0.65)] font-medium">
                      {company.role}
                    </span>
                  </div>

                  {/* Tech Stack */}
                  {company.tech_stack && (
                    <div className="flex items-start gap-2 mb-4">
                      <Code className="w-4 h-4 text-[rgba(55,50,47,0.4)] mt-1 flex-shrink-0" />
                      <div className="flex flex-wrap gap-1.5">
                        {company.tech_stack.split(",").slice(0, 4).map((tech, i) => (
                          <span
                            key={i}
                            className="text-xs px-2.5 py-1 rounded-lg bg-[rgba(55,50,47,0.06)] text-[rgba(55,50,47,0.7)] font-medium"
                          >
                            {tech.trim()}
                          </span>
                        ))}
                        {company.tech_stack.split(",").length > 4 && (
                          <span className="text-xs px-2.5 py-1 rounded-lg bg-[rgba(55,50,47,0.06)] text-[rgba(55,50,47,0.7)] font-medium">
                            +{company.tech_stack.split(",").length - 4}
                          </span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Description Preview */}
                  {company.description && (
                    <p className="text-sm text-[rgba(55,50,47,0.55)] line-clamp-3 leading-relaxed mb-4">
                      {company.description}
                    </p>
                  )}

                  {/* Hover Indicator */}
                  <div className="absolute bottom-5 right-5 opacity-0 group-hover:opacity-100 transition-opacity">
                    <div className="w-9 h-9 rounded-full bg-[#37322F] flex items-center justify-center shadow-lg">
                      <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Company Detail Modal */}
        {selectedCompany && (
          <>
            <div
              className="fixed inset-0 bg-black/50 backdrop-blur-md z-50 animate-fade-in"
              onClick={handleCloseDetail}
            />
            <div 
              className="fixed inset-0 z-50 flex items-center justify-center p-4"
              onClick={handleCloseDetail}
            >
              <div 
                className="w-full max-w-4xl max-h-[85vh] overflow-hidden animate-scale-in"
                onClick={(e) => e.stopPropagation()}
              >
                <CompanyDetail
                  company={selectedCompany}
                  index={companies.findIndex(
                    (c) =>
                      c.company_name === selectedCompany.company_name &&
                      c.role === selectedCompany.role
                  )}
                  onDelete={handleDelete}
                  onClose={handleCloseDetail}
                />
              </div>
            </div>
          </>
        )}
      </main>

      {/* Floating Action Button */}
      <button
        onClick={() => setIsFormOpen(true)}
        className={cn(
          "fixed bottom-8 right-8 w-16 h-16 rounded-full shadow-[0px_8px_32px_rgba(55,50,47,0.25)] transition-all duration-300 hover:scale-110 active:scale-95 z-40",
          "bg-gradient-to-br from-[#37322F] to-[#2A2624] hover:shadow-[0px_12px_48px_rgba(55,50,47,0.35)]",
          isFormOpen && "rotate-45"
        )}
        aria-label="Add company"
      >
        <Plus className="w-7 h-7 text-white mx-auto" />
      </button>

      {/* Modal Overlay */}
      {isFormOpen && (
        <>
          <div
            className="fixed inset-0 bg-black/50 backdrop-blur-md z-50 animate-fade-in"
            onClick={() => setIsFormOpen(false)}
          />

          {/* Floating Modal */}
          <div 
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            onClick={() => setIsFormOpen(false)}
          >
            <div
              className="bg-white rounded-3xl shadow-[0px_20px_80px_rgba(0,0,0,0.25)] w-full max-w-2xl max-h-[90vh] overflow-hidden animate-scale-in"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Modal Header */}
              <div className="relative px-8 pt-8 pb-6 border-b border-[rgba(55,50,47,0.08)] bg-gradient-to-br from-[#FAFAFA] to-white">
                <button
                  onClick={() => setIsFormOpen(false)}
                  className="absolute top-6 right-6 w-10 h-10 rounded-full hover:bg-[rgba(55,50,47,0.06)] transition-all flex items-center justify-center group"
                >
                  <X className="w-5 h-5 text-[rgba(55,50,47,0.4)] group-hover:text-[rgba(55,50,47,0.8)] transition-colors" />
                </button>
                <div className="pr-12">
                  <h2 className="text-3xl font-bold text-[#2F3037] font-sans tracking-tight">
                    Add Company Profile
                  </h2>
                  <p className="text-[rgba(55,50,47,0.6)] mt-2 font-sans leading-relaxed">
                    Create a new company profile to tailor your interview preparation
                  </p>
                </div>
              </div>

              {/* Modal Content - Scrollable */}
              <div className="overflow-y-auto max-h-[calc(90vh-180px)] px-8 py-6">
                <form onSubmit={handleCreate} className="space-y-6">
                  {/* Company Name */}
                  <div className="space-y-2.5">
                    <label className="block text-sm font-semibold text-[#37322F] font-sans">
                      Company Name <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Google, Microsoft, Startup Inc."
                      required
                      value={form.company_name}
                      onChange={(e) => setForm({ ...form, company_name: e.target.value })}
                      className="w-full px-4 py-3.5 rounded-xl border-2 border-[rgba(55,50,47,0.12)] bg-white text-[#2F3037] placeholder:text-[rgba(55,50,47,0.35)] focus:outline-none focus:ring-4 focus:ring-[#37322F]/10 focus:border-[#37322F] transition-all font-sans text-[15px]"
                    />
                  </div>

                  {/* Role */}
                  <div className="space-y-2.5">
                    <label className="block text-sm font-semibold text-[#37322F] font-sans">
                      Role
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Backend Engineer, Product Manager"
                      value={form.role}
                      onChange={(e) => setForm({ ...form, role: e.target.value })}
                      className="w-full px-4 py-3.5 rounded-xl border-2 border-[rgba(55,50,47,0.12)] bg-white text-[#2F3037] placeholder:text-[rgba(55,50,47,0.35)] focus:outline-none focus:ring-4 focus:ring-[#37322F]/10 focus:border-[#37322F] transition-all font-sans text-[15px]"
                    />
                  </div>

                  {/* Two Column Layout for Description and Hiring Patterns */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Description */}
                    <div className="space-y-2.5">
                      <label className="block text-sm font-semibold text-[#37322F] font-sans">
                        Description
                      </label>
                      <textarea
                        placeholder="Brief description of the company..."
                        value={form.description}
                        onChange={(e) => setForm({ ...form, description: e.target.value })}
                        rows={4}
                        className="w-full px-4 py-3.5 rounded-xl border-2 border-[rgba(55,50,47,0.12)] bg-white text-[#2F3037] placeholder:text-[rgba(55,50,47,0.35)] focus:outline-none focus:ring-4 focus:ring-[#37322F]/10 focus:border-[#37322F] transition-all font-sans text-[15px] resize-none"
                      />
                    </div>

                    {/* Hiring Patterns */}
                    <div className="space-y-2.5">
                      <label className="block text-sm font-semibold text-[#37322F] font-sans">
                        Hiring Patterns
                      </label>
                      <textarea
                        placeholder="What they look for in candidates..."
                        value={form.hiring_patterns}
                        onChange={(e) => setForm({ ...form, hiring_patterns: e.target.value })}
                        rows={4}
                        className="w-full px-4 py-3.5 rounded-xl border-2 border-[rgba(55,50,47,0.12)] bg-white text-[#2F3037] placeholder:text-[rgba(55,50,47,0.35)] focus:outline-none focus:ring-4 focus:ring-[#37322F]/10 focus:border-[#37322F] transition-all font-sans text-[15px] resize-none"
                      />
                    </div>
                  </div>

                  {/* Tech Stack */}
                  <div className="space-y-2.5">
                    <label className="block text-sm font-semibold text-[#37322F] font-sans">
                      Tech Stack
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. React, Python, AWS, PostgreSQL, Docker"
                      value={form.tech_stack}
                      onChange={(e) => setForm({ ...form, tech_stack: e.target.value })}
                      className="w-full px-4 py-3.5 rounded-xl border-2 border-[rgba(55,50,47,0.12)] bg-white text-[#2F3037] placeholder:text-[rgba(55,50,47,0.35)] focus:outline-none focus:ring-4 focus:ring-[#37322F]/10 focus:border-[#37322F] transition-all font-sans text-[15px]"
                    />
                  </div>

                  {/* Action Buttons */}
                  <div className="flex gap-3 pt-4">
                    <button
                      type="button"
                      onClick={() => setIsFormOpen(false)}
                      className="flex-1 h-12 rounded-xl border-2 border-[rgba(55,50,47,0.12)] hover:bg-[rgba(55,50,47,0.04)] font-sans font-semibold text-[#37322F] transition-all hover:border-[rgba(55,50,47,0.2)]"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className="flex-1 h-12 rounded-xl bg-gradient-to-r from-[#37322F] to-[#2A2624] hover:from-[#2A2624] hover:to-[#1F1C1A] text-white font-sans font-semibold shadow-[0px_4px_16px_rgba(55,50,47,0.25)] hover:shadow-[0px_6px_24px_rgba(55,50,47,0.35)] transition-all hover:scale-[1.02] active:scale-[0.98]"
                    >
                      Save Company Profile
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
