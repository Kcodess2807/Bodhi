"use client"

import { useEffect, useRef } from "react"
import { motion } from "framer-motion"
import { Building2, Briefcase, Code, Sparkles, User } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { type CompanyProfile } from "@/lib/api"

interface CompanyCarouselProps {
  companies: CompanyProfile[]
  selectedCompany: CompanyProfile | null
  onSelect: (company: CompanyProfile) => void
  onDelete: (company: CompanyProfile) => void
}

export function CompanyCarousel({ companies, selectedCompany, onSelect, onDelete }: CompanyCarouselProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  const getCompanyIcon = (index: number) => {
    const icons = [User, Building2, Briefcase, Code, Sparkles]
    const Icon = icons[index % icons.length]
    return <Icon className="w-5 h-5 stroke-1 text-muted-foreground" />
  }

  const isPremiumCard = (index: number) => index % 4 === 0

  // Auto-scroll effect
  useEffect(() => {
    const scrollContainer = scrollRef.current
    if (!scrollContainer) return

    let scrollPosition = 0
    const scrollSpeed = 0.5 // pixels per frame

    const animate = () => {
      if (!scrollContainer) return
      
      scrollPosition += scrollSpeed
      
      // Reset scroll when reaching the end
      if (scrollPosition >= scrollContainer.scrollWidth / 2) {
        scrollPosition = 0
      }
      
      scrollContainer.scrollLeft = scrollPosition
      requestAnimationFrame(animate)
    }

    const animationId = requestAnimationFrame(animate)

    // Pause on hover
    const handleMouseEnter = () => cancelAnimationFrame(animationId)
    const handleMouseLeave = () => requestAnimationFrame(animate)

    scrollContainer.addEventListener("mouseenter", handleMouseEnter)
    scrollContainer.addEventListener("mouseleave", handleMouseLeave)

    return () => {
      cancelAnimationFrame(animationId)
      scrollContainer.removeEventListener("mouseenter", handleMouseEnter)
      scrollContainer.removeEventListener("mouseleave", handleMouseLeave)
    }
  }, [companies])

  // Duplicate companies for infinite scroll effect
  const duplicatedCompanies = [...companies, ...companies]

  return (
    <div className="relative overflow-hidden">
      <div
        ref={scrollRef}
        className="flex gap-4 overflow-x-hidden py-4"
        style={{ scrollBehavior: "auto" }}
      >
        {duplicatedCompanies.map((company, index) => {
          const isSelected =
            selectedCompany?.company_name === company.company_name &&
            selectedCompany?.role === company.role
          const originalIndex = index % companies.length

          return (
            <motion.div
              key={`${company.company_name}-${company.role}-${index}`}
              onClick={() => onSelect(company)}
              whileHover={{ scale: 1.05 }}
              className={`group relative cursor-pointer rounded-xl border border-white/40 p-4 min-w-[200px] flex-shrink-0 transition-all duration-300 shadow-md backdrop-blur-xl ${
                isSelected
                  ? "ring-2 ring-black/20 bg-white/80"
                  : isPremiumCard(originalIndex)
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
                className="absolute top-2 right-2 w-6 h-6 rounded-full bg-white/80 text-destructive opacity-0 group-hover:opacity-100 transition-all duration-200 hover:bg-white hover:scale-105 flex items-center justify-center z-10"
                aria-label="Delete company"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                </svg>
              </button>

              {/* Icon */}
              <div className="mb-3"> 
                {getCompanyIcon(originalIndex)}
              </div>

              {/* Content */}
              <div className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold tracking-tight text-foreground truncate">
                    {company.company_name}
                  </h3>
                  {isPremiumCard(originalIndex) && <Badge className="text-[10px] px-1 py-0">Premium</Badge>}
                </div>
                <Badge variant="secondary" className="text-xs w-fit">{company.role}</Badge>
              </div>
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}
