import { Button } from "@/components/ui/button"

export function HeroSection() {
  return (
    <section className="relative pt-54 pb-16">
      <div className="max-w-265 mx-auto px-4">
        <div className="flex flex-col items-center gap-12">
          {/* Hero Content */}
          <div className="max-w-234.25 flex flex-col items-center gap-3">
            <div className="flex flex-col items-center gap-6">
              <h1 className="max-w-187 text-center text-[#37322f] text-5xl md:text-[80px] font-normal leading-tight md:leading-24 font-serif">
                AI mock interviews tailored by Bodhi
              </h1>
              <p className="max-w-126.5 text-center text-[#37322f]/80 text-lg font-medium leading-7">
                Practice real interview flows with resume-aware coaching, structured feedback, and growth plans.
              </p>
            </div>
          </div>

          {/* CTA Button */}
          <div className="flex justify-center">
            <Button className="h-10 px-12 bg-[#37322f] hover:bg-[#37322f]/90 text-white rounded-full font-medium text-sm shadow-[0px_0px_0px_2.5px_rgba(255,255,255,0.08)_inset]">
              Start for free
            </Button>
          </div>
        </div>
      </div>
    </section>
  )
}
