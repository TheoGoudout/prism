import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { z } from "zod"

import type { SchedulePublic } from "@/client"
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
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
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
import useCustomToast from "@/hooks/useCustomToast"
import { recipientsError, splitEmails } from "./emails"
import { FREQUENCY_LABELS, formatHour, WEEKDAYS } from "./labels"

const browserTimeZone = () => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
  } catch {
    return "UTC"
  }
}

// Intl.supportedValuesOf is ES2022, newer than the configured TypeScript lib
const TIME_ZONES: string[] = (() => {
  try {
    const intl = Intl as unknown as {
      supportedValuesOf: (key: "timeZone") => string[]
    }
    return intl.supportedValuesOf("timeZone")
  } catch {
    return ["UTC"]
  }
})()

const formSchema = z
  .object({
    enabled: z.boolean(),
    frequency: z.enum(["weekly", "biweekly", "monthly"]),
    weekday: z.number().int().min(0).max(6),
    day_of_month: z.number().int().min(1).max(28),
    hour: z.number().int().min(0).max(23),
    timezone: z.string().min(1),
    email_enabled: z.boolean(),
    recipients: z.string(),
  })
  .superRefine((data, ctx) => {
    const error = recipientsError(data.recipients, data.email_enabled)
    if (error)
      ctx.addIssue({ code: "custom", path: ["recipients"], message: error })
  })

type FormData = z.infer<typeof formSchema>

function toFormData(schedule: SchedulePublic | undefined): FormData {
  // A schedule that was never saved defaults to the browser's time zone
  const saved = schedule?.next_run_at != null || schedule?.enabled
  return {
    enabled: schedule?.enabled ?? false,
    frequency: schedule?.frequency ?? "weekly",
    weekday: schedule?.weekday ?? 0,
    day_of_month: schedule?.day_of_month ?? 1,
    hour: schedule?.hour ?? 8,
    timezone: saved ? (schedule?.timezone ?? "UTC") : browserTimeZone(),
    email_enabled: schedule?.email_enabled ?? false,
    recipients: (schedule?.email_recipients ?? []).join(", "),
  }
}

function NumberSelect({
  value,
  onChange,
  options,
  disabled,
}: {
  value: number
  onChange: (value: number) => void
  options: { value: number; label: string }[]
  disabled: boolean
}) {
  return (
    <Select
      value={String(value)}
      onValueChange={(v) => onChange(Number(v))}
      disabled={disabled}
    >
      <FormControl>
        <SelectTrigger className="w-full">
          <SelectValue />
        </SelectTrigger>
      </FormControl>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={String(option.value)}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export function ScheduleDialog({
  open,
  onOpenChange,
  schedule,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  schedule: SchedulePublic | undefined
}) {
  const workspace = useCurrentWorkspace()
  const queryClient = useQueryClient()
  const { showSuccessToast, showApiError } = useCustomToast()
  const editable = canManage(workspace)

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    values: toFormData(schedule),
  })
  const frequency = form.watch("frequency")
  const disabled = !editable

  const saveMut = useMutation({
    mutationFn: ({ recipients, ...data }: FormData) =>
      AnalysesService.updateSchedule({
        workspaceId: workspace.id,
        requestBody: { ...data, email_recipients: splitEmails(recipients) },
      }),
    onSuccess: (saved) => {
      queryClient.setQueryData(["analysis-schedule", workspace.id], saved)
      showSuccessToast(
        saved.enabled ? "Analysis scheduled" : "Scheduled analysis turned off",
      )
      onOpenChange(false)
    },
    onError: showApiError,
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Scheduled analysis</DialogTitle>
          <DialogDescription>
            {editable
              ? "Run the AI analysis automatically, and email the report."
              : "Only owners and admins can change the schedule."}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit((d) => saveMut.mutate(d))}
            className="flex flex-col gap-4"
          >
            <FormField
              control={form.control}
              name="enabled"
              render={({ field }) => (
                <FormItem className="flex items-center gap-2">
                  <FormControl>
                    <Checkbox
                      checked={field.value}
                      onCheckedChange={(v) => field.onChange(v === true)}
                      disabled={disabled}
                    />
                  </FormControl>
                  <FormLabel>Run the analysis automatically</FormLabel>
                </FormItem>
              )}
            />

            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="frequency"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Frequency</FormLabel>
                    <Select
                      value={field.value}
                      onValueChange={field.onChange}
                      disabled={disabled}
                    >
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {Object.entries(FREQUENCY_LABELS).map(([v, label]) => (
                          <SelectItem key={v} value={v}>
                            {label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FormItem>
                )}
              />
              {frequency === "monthly" ? (
                <FormField
                  control={form.control}
                  name="day_of_month"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Day of the month</FormLabel>
                      <NumberSelect
                        value={field.value}
                        onChange={field.onChange}
                        disabled={disabled}
                        options={Array.from({ length: 28 }, (_, i) => ({
                          value: i + 1,
                          label: String(i + 1),
                        }))}
                      />
                    </FormItem>
                  )}
                />
              ) : (
                <FormField
                  control={form.control}
                  name="weekday"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Day</FormLabel>
                      <NumberSelect
                        value={field.value}
                        onChange={field.onChange}
                        disabled={disabled}
                        options={WEEKDAYS.map((label, value) => ({
                          value,
                          label,
                        }))}
                      />
                    </FormItem>
                  )}
                />
              )}
              <FormField
                control={form.control}
                name="hour"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Time</FormLabel>
                    <NumberSelect
                      value={field.value}
                      onChange={field.onChange}
                      disabled={disabled}
                      options={Array.from({ length: 24 }, (_, value) => ({
                        value,
                        label: formatHour(value),
                      }))}
                    />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="timezone"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Time zone</FormLabel>
                    <Select
                      value={field.value}
                      onValueChange={field.onChange}
                      disabled={disabled}
                    >
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {(TIME_ZONES.includes(field.value)
                          ? TIME_ZONES
                          : [field.value, ...TIME_ZONES]
                        ).map((tz) => (
                          <SelectItem key={tz} value={tz}>
                            {tz}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FormItem>
                )}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              Each run analyzes the full{" "}
              {frequency === "monthly"
                ? "month"
                : frequency === "biweekly"
                  ? "two weeks"
                  : "week"}{" "}
              before it.
            </p>

            <FormField
              control={form.control}
              name="email_enabled"
              render={({ field }) => (
                <FormItem className="flex items-center gap-2">
                  <FormControl>
                    <Checkbox
                      checked={field.value}
                      onCheckedChange={(v) => field.onChange(v === true)}
                      disabled={disabled}
                    />
                  </FormControl>
                  <FormLabel>Email the report when it's ready</FormLabel>
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="recipients"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Recipients</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="alice@example.com, bob@example.com"
                      disabled={disabled}
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>
                    Separate addresses with commas.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline" type="button">
                  {editable ? "Cancel" : "Close"}
                </Button>
              </DialogClose>
              {editable && (
                <LoadingButton type="submit" loading={saveMut.isPending}>
                  Save
                </LoadingButton>
              )}
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
