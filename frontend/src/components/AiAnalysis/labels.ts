import type { AnalysisFrequency, PostAnalysis, SchedulePublic } from "@/client"

export type Verdict = PostAnalysis["verdict"]

export const VERDICT_LABELS: Record<Verdict, string> = {
  strong: "Strong",
  average: "Average",
  weak: "Weak",
}

export const VERDICT_CLASSES: Record<Verdict, string> = {
  strong:
    "border-transparent bg-green-500/15 text-green-700 dark:text-green-400",
  average:
    "border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-400",
  weak: "border-transparent bg-destructive/15 text-destructive",
}

export const FREQUENCY_LABELS: Record<AnalysisFrequency, string> = {
  weekly: "Weekly",
  biweekly: "Every two weeks",
  monthly: "Monthly",
}

/** Monday first, matching the API (0 = Monday). */
export const WEEKDAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
]

export const formatHour = (hour: number) =>
  `${hour.toString().padStart(2, "0")}:00`

/** "Weekly on Monday at 08:00 (Europe/Paris)". */
export function describeSchedule(schedule: SchedulePublic): string {
  const frequency = schedule.frequency ?? "weekly"
  const day =
    frequency === "monthly"
      ? `on day ${schedule.day_of_month ?? 1}`
      : `on ${WEEKDAYS[schedule.weekday ?? 0]}`
  return `${FREQUENCY_LABELS[frequency]} ${day} at ${formatHour(
    schedule.hour ?? 8,
  )} (${schedule.timezone ?? "UTC"})`
}
