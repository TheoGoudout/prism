import type { IntegrationStatus, Platform } from "@/client"

export const PLATFORM_LABELS: Record<Platform, string> = {
  facebook: "Facebook",
  instagram: "Instagram",
  twitter: "Twitter / X",
  linkedin: "LinkedIn",
  tiktok: "TikTok",
  google_analytics: "Google Analytics",
}

export const PLATFORMS = Object.keys(PLATFORM_LABELS) as Platform[]

export function platformLabel(platform: string): string {
  return PLATFORM_LABELS[platform as Platform] ?? platform
}

/** Expired integrations must be reconnected before they can sync again. */
export const needsReconnect = (status: IntegrationStatus) =>
  status === "expired"
