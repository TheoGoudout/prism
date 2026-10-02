import { useMutation, useQueryClient } from "@tanstack/react-query"
import { format, subDays } from "date-fns"
import { CalendarRange, Sparkles, TriangleAlert } from "lucide-react"
import { useState } from "react"

import type { AnalysisKind, AnalysisPublic } from "@/client"
import { AnalysesService } from "@/client"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { canManage } from "@/components/Workspaces/roles"
import { useCurrentWorkspace } from "@/contexts/WorkspaceContext"
import useAuth from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { type DateRange, lastDays } from "@/lib/format"
import { cn } from "@/lib/utils"
import { recipientsError, splitEmails } from "./emails"

interface PeriodOption {
  value: string
  label: string
  range: () => DateRange
}

const STANDARD_PERIODS: PeriodOption[] = [7, 14, 30, 90].map((days) => ({
  value: String(days),
  label: `Last ${days} days`,
  range: () => lastDays(days),
}))

/** The last 12 months, then this year to date and the three before it. */
function yearlyPeriods(): PeriodOption[] {
  const today = new Date()
  const year = today.getFullYear()
  return [
    {
      value: "last-12-months",
      label: "Last 12 months",
      range: () => ({
        dateFrom: format(subDays(today, 364), "yyyy-MM-dd"),
        dateTo: format(today, "yyyy-MM-dd"),
      }),
    },
    ...[0, 1, 2, 3].map((ago) => ({
      value: String(year - ago),
      label: ago === 0 ? `${year} (to date)` : String(year - ago),
      range: () => ({
        dateFrom: `${year - ago}-01-01`,
        dateTo: ago === 0 ? format(today, "yyyy-MM-dd") : `${year - ago}-12-31`,
      }),
    })),
  ]
}

const KINDS: {
  kind: AnalysisKind
  title: string
  description: string
  icon: typeof Sparkles
}[] = [
  {
    kind: "standard",
    title: "Recent performance",
    description: "Every post of a recent period, analyzed one by one.",
    icon: Sparkles,
  },
  {
    kind: "yearly",
    title: "Year in review",
    description:
      "A whole year: month-by-month trends, topics and the most notable posts.",
    icon: CalendarRange,
  },
]

export function RunAnalysisDialog({
  open,
  onOpenChange,
  onStarted,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onStarted: (analysis: AnalysisPublic) => void
}) {
  const workspace = useCurrentWorkspace()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showApiError } = useCustomToast()
  const manager = canManage(workspace)

  const [kind, setKind] = useState<AnalysisKind>("standard")
  const [periods, setPeriods] = useState({
    standard: "7",
    yearly: "last-12-months",
  })
  const [emailEnabled, setEmailEnabled] = useState(false)
  const [recipients, setRecipients] = useState(user?.email ?? "")
  const [showErrors, setShowErrors] = useState(false)

  const options = kind === "yearly" ? yearlyPeriods() : STANDARD_PERIODS
  const period = options.find((o) => o.value === periods[kind]) ?? options[0]
  const error = emailEnabled ? recipientsError(recipients, true) : null

  const runMut = useMutation({
    mutationFn: () => {
      const range = period.range()
      return AnalysesService.createAnalysis({
        workspaceId: workspace.id,
        requestBody: {
          kind,
          date_from: range.dateFrom,
          date_to: range.dateTo,
          email_recipients: emailEnabled ? splitEmails(recipients) : [],
        },
      })
    },
    onSuccess: (analysis) => {
      queryClient.invalidateQueries({ queryKey: ["analyses", workspace.id] })
      onOpenChange(false)
      onStarted(analysis)
    },
    onError: showApiError,
  })

  const submit = () => {
    setShowErrors(true)
    if (!error) runMut.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Run an analysis</DialogTitle>
          <DialogDescription>
            The AI reviews your posts and metrics across every connected
            platform.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="grid gap-3 sm:grid-cols-2">
            {KINDS.map((option) => {
              const disabled = option.kind === "yearly" && !manager
              return (
                <button
                  key={option.kind}
                  type="button"
                  disabled={disabled}
                  onClick={() => setKind(option.kind)}
                  aria-pressed={kind === option.kind}
                  className={cn(
                    "flex flex-col gap-1 rounded-lg border p-3 text-left text-sm transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50",
                    kind === option.kind && "border-primary bg-accent",
                  )}
                >
                  <span className="flex items-center gap-2 font-medium">
                    <option.icon className="size-4" />
                    {option.title}
                  </span>
                  <span className="text-muted-foreground">
                    {disabled
                      ? "Only owners and admins can run a yearly analysis."
                      : option.description}
                  </span>
                </button>
              )
            })}
          </div>

          <div className="flex flex-col gap-2">
            <Label>Period</Label>
            <Select
              value={period.value}
              onValueChange={(value) =>
                setPeriods((p) => ({ ...p, [kind]: value }))
              }
            >
              <SelectTrigger className="w-full" aria-label="Period">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {options.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {kind === "yearly" && (
            <p className="flex gap-2 rounded-md bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-300">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" />A yearly
              analysis sends up to 300 posts and a month-by-month breakdown to
              the AI, so it costs noticeably more than a regular one and can
              take a few minutes.
            </p>
          )}

          <div className="flex items-center gap-2">
            <Checkbox
              id="email-report"
              checked={emailEnabled}
              onCheckedChange={(v) => setEmailEnabled(v === true)}
            />
            <Label htmlFor="email-report">
              Email the report when it's ready
            </Label>
          </div>
          {emailEnabled && (
            <div className="flex flex-col gap-2">
              <Label htmlFor="report-recipients">Recipients</Label>
              <Input
                id="report-recipients"
                value={recipients}
                onChange={(e) => setRecipients(e.target.value)}
                placeholder="alice@example.com, bob@example.com"
                aria-invalid={showErrors && !!error}
              />
              {showErrors && error ? (
                <p className="text-sm text-destructive">{error}</p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Separate addresses with commas.
                </p>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" type="button">
              Cancel
            </Button>
          </DialogClose>
          <LoadingButton loading={runMut.isPending} onClick={submit}>
            <Sparkles />
            Run analysis
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
