import { Heart } from "lucide-react"

// Two smooth lines, drawn once by hand: views above reach, as on the
// Analytics trend chart.
const VIEWS = "M0 38 C 20 30, 35 34, 55 24 S 90 12, 110 18 S 150 6, 180 8"
const REACH = "M0 48 C 22 42, 38 46, 58 38 S 92 30, 112 34 S 152 22, 180 24"

/**
 * A glimpse of the dashboard for the sign-in panel: one KPI card and a trend.
 * Frosted cards on the ink panel; the line colours are the chart palette's
 * first two hues, lifted for the dark ground.
 */
export function AuthPreview() {
  return (
    <div aria-hidden="true" className="flex items-start gap-4 text-white">
      <div className="w-44 rounded-xl border border-white/15 bg-white/8 p-4 backdrop-blur-md">
        <div className="flex items-center justify-between text-xs text-white/70">
          Engagements
          <span className="flex size-6 items-center justify-center rounded-md bg-[oklch(0.7_0.13_160/0.2)] text-[oklch(0.8_0.13_160)]">
            <Heart className="size-3.5" />
          </span>
        </div>
        <p className="mt-3 font-display text-3xl font-extrabold tracking-tight">
          156.4K
        </p>
        <p className="mt-1 text-xs text-[oklch(0.8_0.13_160)]">
          +12% vs last month
        </p>
      </div>
      <div className="mt-8 w-56 rounded-xl border border-white/15 bg-white/8 p-4 backdrop-blur-md">
        <p className="text-xs text-white/70">Views &amp; reach · 30 days</p>
        <svg viewBox="0 0 180 56" className="mt-3 h-16 w-full" fill="none">
          <title>Views and reach over 30 days</title>
          <path
            d={VIEWS}
            stroke="oklch(0.72 0.15 277)"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          <path
            d={REACH}
            stroke="oklch(0.75 0.15 45)"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
        </svg>
        <div className="mt-2 flex gap-3 text-[0.6875rem] text-white/70">
          <span className="flex items-center gap-1">
            <span className="size-2 rounded-full bg-[oklch(0.72_0.15_277)]" />
            Views
          </span>
          <span className="flex items-center gap-1">
            <span className="size-2 rounded-full bg-[oklch(0.75_0.15_45)]" />
            Reach
          </span>
        </div>
      </div>
    </div>
  )
}
