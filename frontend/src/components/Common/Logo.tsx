import { Link } from "@tanstack/react-router"

import { cn } from "@/lib/utils"

interface LogoProps {
  variant?: "full" | "icon" | "responsive"
  className?: string
  asLink?: boolean
}

/** Prism mark: a beam of light split into colours. Same art as the favicon. */
function PrismIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
      className={cn("size-6 shrink-0", className)}
    >
      <path
        d="M1 18.5 11.5 16"
        stroke="currentColor"
        strokeOpacity=".5"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M14 4 25 26H3L14 4Z"
        fill="#6366f1"
        fillOpacity=".15"
        stroke="#6366f1"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path
        d="m18.5 15 12-4"
        stroke="#ef4444"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="m18.5 16.5 12 0"
        stroke="#22c55e"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="m18.5 18 12 4"
        stroke="#3b82f6"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function Logo({
  variant = "full",
  className,
  asLink = true,
}: LogoProps) {
  const wordmark = (
    <span className="text-lg font-semibold tracking-tight">Prism</span>
  )

  const content = (
    <span
      role="img"
      aria-label="Prism"
      className={cn(
        "inline-flex items-center gap-2 text-foreground",
        className,
      )}
    >
      <PrismIcon />
      {variant === "full" && wordmark}
      {variant === "responsive" && (
        <span className="group-data-[collapsible=icon]:hidden">{wordmark}</span>
      )}
    </span>
  )

  if (!asLink) {
    return content
  }

  return <Link to="/">{content}</Link>
}
