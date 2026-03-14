"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import { SignInButton, UserButton } from "@clerk/nextjs"

export default function Navbar() {
  const { isSignedIn } = useAuth()
  const pathname = usePathname()

  const navLinks = [
    { href: "/interview", label: "Interview" },
    { href: "/companies", label: "Companies" },
    { href: "/roles", label: "Roles" },
    { href: "/resumes", label: "Resumes" },
  ]

  const isActive = (href: string) => pathname === href

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 flex justify-center items-center px-4 py-4 animate-fade-in-up">
      {/* Enhanced glassmorphism container */}
      <div 
        className="relative w-full max-w-[900px] h-14 py-2 px-5 overflow-hidden rounded-[50px] flex justify-between items-center transition-all duration-300 group"
        style={{
          background: "rgba(255, 255, 255, 0.75)",
          backdropFilter: "blur(20px) saturate(180%)",
          WebkitBackdropFilter: "blur(20px) saturate(180%)",
          border: "1px solid rgba(255, 255, 255, 0.5)",
          boxShadow: "0 0 0 1px rgba(255, 255, 255, 0.8) inset, 0 4px 12px rgba(0, 0, 0, 0.08), 0 8px 32px rgba(0, 0, 0, 0.04)",
        }}
      >
        {/* Subtle gradient overlay */}
        <div 
          className="absolute inset-0 opacity-50 pointer-events-none"
          style={{
            background: "linear-gradient(135deg, rgba(255, 255, 255, 0.4) 0%, rgba(255, 255, 255, 0) 50%, rgba(255, 255, 255, 0.2) 100%)",
          }}
        />
        
        {/* Shimmer effect on hover */}
        <div 
          className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"
          style={{
            background: "linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.3) 50%, transparent 100%)",
            transform: "translateX(-100%)",
            animation: "shimmer 3s infinite",
          }}
        />

        {/* Content */}
        <div className="relative z-10 flex items-center justify-between w-full">
          {/* Logo */}
          <Link
            href="/"
            className="text-[#2F3037] text-xl font-bold font-sans tracking-tight hover:opacity-80 transition-all duration-200 hover:scale-105 shrink-0"
            style={{ fontFamily: "var(--font-inter), ui-sans-serif, sans-serif" }}
          >
            Bodhi
          </Link>

          {/* Navigation Links - Hidden on mobile, shown on tablet+ */}
          {isSignedIn && (
            <div className="hidden md:flex items-center gap-1 mx-4">
              {navLinks.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`px-4 py-1.5 rounded-full text-[13px] font-medium transition-all duration-200 ${
                    isActive(link.href)
                      ? "bg-[rgba(55,50,47,0.12)] text-[#37322F] shadow-sm"
                      : "text-[rgba(55,50,47,0.65)] hover:text-[#37322F] hover:bg-[rgba(55,50,47,0.06)]"
                  }`}
                >
                  {link.label}
                </Link>
              ))}
            </div>
          )}

          {/* Right side */}
          <div className="flex items-center gap-3 shrink-0">
            {isSignedIn ? (
              <div className="flex items-center gap-2">
                {/* Mobile menu button */}
                <div className="md:hidden relative group/menu">
                  <button className="px-3 py-1.5 text-[rgba(55,50,47,0.65)] hover:text-[#37322F] text-sm font-medium transition-all duration-200 hover:bg-[rgba(55,50,47,0.06)] rounded-full">
                    Menu
                  </button>
                  {/* Dropdown with enhanced glassmorphism */}
                  <div 
                    className="absolute right-0 top-full mt-2 w-48 rounded-2xl opacity-0 invisible group-hover/menu:opacity-100 group-hover/menu:visible transition-all duration-200 overflow-hidden"
                    style={{
                      background: "rgba(255, 255, 255, 0.85)",
                      backdropFilter: "blur(20px) saturate(180%)",
                      WebkitBackdropFilter: "blur(20px) saturate(180%)",
                      border: "1px solid rgba(255, 255, 255, 0.5)",
                      boxShadow: "0 4px 16px rgba(0, 0, 0, 0.12), 0 8px 32px rgba(0, 0, 0, 0.08)",
                    }}
                  >
                    {navLinks.map((link) => (
                      <Link
                        key={link.href}
                        href={link.href}
                        className={`block px-4 py-2.5 text-sm font-medium transition-colors ${
                          isActive(link.href)
                            ? "bg-[rgba(55,50,47,0.08)] text-[#37322F]"
                            : "text-[rgba(55,50,47,0.65)] hover:text-[#37322F] hover:bg-[rgba(55,50,47,0.04)]"
                        }`}
                      >
                        {link.label}
                      </Link>
                    ))}
                  </div>
                </div>
                <UserButton />
              </div>
            ) : (
              <SignInButton mode="modal">
                <button className="px-[14px] py-[6px] bg-white shadow-[0px_1px_2px_rgba(55,50,47,0.12)] overflow-hidden rounded-full flex justify-center items-center cursor-pointer transition-all duration-200 hover:shadow-[0px_2px_4px_rgba(55,50,47,0.16)] hover:scale-105 active:scale-95">
                  <span className="text-[#37322F] text-[13px] font-medium leading-5 font-sans">
                    Log in
                  </span>
                </button>
              </SignInButton>
            )}
          </div>
        </div>
      </div>

      <style jsx>{`
        @keyframes shimmer {
          0% {
            transform: translateX(-100%);
          }
          100% {
            transform: translateX(100%);
          }
        }
      `}</style>
    </nav>
  )
}
