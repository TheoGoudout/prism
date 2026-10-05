import type { ExportFormat, MigrationSource } from "@/client"

interface SourceInfo {
  label: string
  /** Where to find the credentials in the tool. */
  help: string
  tokenLabel: string
  /** Metricool also needs the user ID, and sometimes a brand ID. */
  needsUserId: boolean
}

export const SOURCES: Record<MigrationSource, SourceInfo> = {
  sprout_social: {
    label: "Sprout Social",
    help: "Create an API token in Sprout Social under Settings → Global Features → API. API access is included in Sprout's Advanced plan.",
    tokenLabel: "API token",
    needsUserId: false,
  },
  metricool: {
    label: "Metricool",
    help: "Find your API token in Metricool under Account settings → API. Your user ID and brand ID (blogId) are in Metricool's address bar: …?blogId=1234&userId=5678. API access is included in Metricool's Advanced plan.",
    tokenLabel: "User token",
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
