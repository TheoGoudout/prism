import type { IntegrationStatus, Platform } from "@/client"

export const PLATFORM_LABELS: Record<Platform, string> = {
  facebook: "Facebook",
  instagram: "Instagram",
  twitter: "Twitter / X",
  linkedin: "LinkedIn",
  tiktok: "TikTok",
  google_analytics: "Google Analytics",
  mailchimp: "Mailchimp",
  klaviyo: "Klaviyo",
  brevo: "Brevo",
}

export const PLATFORMS = Object.keys(PLATFORM_LABELS) as Platform[]

export function platformLabel(platform: string): string {
  return PLATFORM_LABELS[platform as Platform] ?? platform
}

/** How to get the key of a platform connected with an API key, not OAuth. */
export interface ApiKeyHelp {
  /** Where the key is created, step by step. */
  steps: string[]
  /** The page of the platform where keys are managed. */
  keysUrl: string
}

export const API_KEY_PLATFORMS: Partial<Record<Platform, ApiKeyHelp>> = {
  brevo: {
    steps: [
      'Open the API keys page of Brevo (link below) and click "Generate a new API key".',
      "Name it Prism, click Generate, then copy the key.",
    ],
    keysUrl: "https://app.brevo.com/settings/keys/api",
  },
}

/** Whether the platform is connected by pasting an API key. */
export const usesApiKey = (platform: Platform) => platform in API_KEY_PLATFORMS

/** Expired integrations must be reconnected before they can sync again. */
export const needsReconnect = (status: IntegrationStatus) =>
  status === "expired"
