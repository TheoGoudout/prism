import type { Platform } from "@/client"
import { cn } from "@/lib/utils"

/** Brand colour and a short monogram per platform. */
const PLATFORM_MARKS: Record<Platform, { color: string; text: string }> = {
  facebook: { color: "#1877f2", text: "f" },
  instagram: { color: "#e1306c", text: "IG" },
  twitter: { color: "#0f1419", text: "X" },
  linkedin: { color: "#0a66c2", text: "in" },
  tiktok: { color: "#ff0050", text: "TT" },
  google_analytics: { color: "#e37400", text: "GA" },
  mailchimp: { color: "#241c15", text: "MC" },
  klaviyo: { color: "#232426", text: "K" },
  brevo: { color: "#0b996e", text: "B" },
}

/** A small tile identifying a platform, in its brand colour. */
export function PlatformIcon({
  platform,
  className,
}: {
  platform: Platform
  className?: string
}) {
  const { color, text } = PLATFORM_MARKS[platform]
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex size-8 shrink-0 items-center justify-center rounded-md text-xs font-bold text-white dark:ring-1 dark:ring-white/15",
        className,
      )}
      style={{ backgroundColor: color }}
    >
      {text}
    </span>
  )
}
