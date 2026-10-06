import type { ExportFormat, MigrationSource } from "@/client"
import {
  METRICOOL_API_GUIDE_URL,
  METRICOOL_APP_URL,
  SPROUT_API_DOCS_URL,
  SPROUT_APP_URL,
} from "./guideContent"

interface SourceInfo {
  label: string
  /** The short version of the guide, shown in the dialog. */
  steps: string[]
  /** The plan or permissions the tool requires for API access. */
  requirement: string
  appUrl: string
  docs: { label: string; href: string }
  /** Metricool also needs the user ID, and optionally a brand ID. */
  needsUserId: boolean
}

export const SOURCES: Record<MigrationSource, SourceInfo> = {
  sprout_social: {
    label: "Sprout Social",
    steps: [
      "Log in to Sprout Social and open Settings → Global Features → API.",
      "Accept the Analytics API terms if Sprout asks you to.",
      "Under API Token Management, click Generate API Token, name it “Prism” and copy it.",
    ],
    requirement:
      "Needs a Sprout plan with API access and the API Permissions permission.",
    appUrl: SPROUT_APP_URL,
    docs: { label: "Sprout's API docs", href: SPROUT_API_DOCS_URL },
    needsUserId: false,
  },
  metricool: {
    label: "Metricool",
    steps: [
      "Log in to Metricool, open Account settings → API and copy your API access token.",
      "Open any brand: the address bar ends with …?blogId=12345&userId=6789. Copy the number after userId=.",
      "Leave Brand ID empty: Prism finds all your brands without it.",
    ],
    requirement: "Needs a Metricool Advanced or Custom plan.",
    appUrl: METRICOOL_APP_URL,
    docs: { label: "Metricool's API guide", href: METRICOOL_API_GUIDE_URL },
    needsUserId: true,
  },
}

export const MIGRATION_SOURCES = Object.keys(SOURCES) as MigrationSource[]

export const EXPORT_FORMATS: Record<ExportFormat, string> = {
  hootsuite: "Hootsuite",
  sprout_social: "Sprout Social",
  buffer: "Buffer",
  metricool: "Metricool",
  later: "Later",
  agorapulse: "Agorapulse",
  csv: "Other CSV",
}

export const sourceLabel = (source: string) =>
  SOURCES[source as MigrationSource]?.label ?? source
