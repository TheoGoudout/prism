import { X } from "lucide-react"
import { useId } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  type ClosedPeriod,
  type Day,
  lastDaysPeriod,
  monthBefore,
  type Period,
  previousPeriod,
  thisMonthPeriod,
  yearBefore,
} from "@/lib/comparison"

/** What the controls edit; the comparison may be half filled in. */
export interface PeriodSelection {
  main: Period
  compareFrom?: Day
  compareTo?: Day
}

function DateField({
  label,
  value,
  onChange,
  placeholder,
  min,
  max,
}: {
  label: string
  value: Day | undefined
  onChange: (value: Day | undefined) => void
  placeholder?: string
  min?: Day
  max: Day
}) {
  const id = useId()
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs text-muted-foreground">
        {label}
      </label>
      <Input
        id={id}
        type="date"
        className="h-8 w-40 text-sm"
        value={value ?? ""}
        placeholder={placeholder}
        min={min}
        max={max}
        onChange={(event) => onChange(event.target.value || undefined)}
      />
    </div>
  )
}

/**
 * The analytics period (end date optional: up to today) and the period it is
 * compared with (both dates), each with a few presets.
 */
export function PeriodControls({
  selection,
  onChange,
  now,
}: {
  selection: PeriodSelection
  onChange: (selection: PeriodSelection) => void
  now: Day
}) {
  const { main } = selection
  const setMain = (period: Period) => onChange({ ...selection, main: period })
  const setCompare = (period: ClosedPeriod | undefined) =>
    onChange({ main, compareFrom: period?.from, compareTo: period?.to })
  const comparing = selection.compareFrom || selection.compareTo

  return (
    <div className="flex flex-col gap-4 rounded-lg border bg-card p-4 lg:flex-row lg:gap-8">
      <fieldset className="space-y-2">
        <legend className="mb-2 text-sm font-medium">Period</legend>
        <div className="flex flex-wrap items-end gap-2">
          <DateField
            label="From"
            value={main.from}
            max={main.to ?? now}
            onChange={(from) => from && setMain({ ...main, from })}
          />
          <DateField
            label="To (empty: today)"
            value={main.to}
            min={main.from}
            max={now}
            onChange={(to) => setMain({ ...main, to })}
          />
        </div>
        <div className="flex flex-wrap gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setMain(lastDaysPeriod(30, now))}
          >
            Last 30 days
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setMain(thisMonthPeriod(now))}
          >
            This month
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setMain(monthBefore(now))}
          >
            Last month
          </Button>
        </div>
      </fieldset>

      <fieldset className="space-y-2">
        <legend className="mb-2 text-sm font-medium">Compare with</legend>
        <div className="flex flex-wrap items-end gap-2">
          <DateField
            label="From"
            value={selection.compareFrom}
            max={selection.compareTo ?? now}
            onChange={(compareFrom) => onChange({ ...selection, compareFrom })}
          />
          <DateField
            label="To"
            value={selection.compareTo}
            min={selection.compareFrom}
            max={now}
            onChange={(compareTo) => onChange({ ...selection, compareTo })}
          />
          {comparing && (
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Stop comparing"
              onClick={() => setCompare(undefined)}
            >
              <X />
            </Button>
          )}
        </div>
        <div className="flex flex-wrap gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setCompare(previousPeriod(main, now))}
          >
            Previous period
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setCompare(monthBefore(main.from))}
          >
            Previous month
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setCompare(yearBefore(main, now))}
          >
            Same period last year
          </Button>
        </div>
      </fieldset>
    </div>
  )
}
