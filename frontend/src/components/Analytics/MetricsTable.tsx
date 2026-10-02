import type { ReactNode } from "react"

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { formatCompact } from "@/lib/format"

export interface MetricsTableRow {
  key: string
  label: ReactNode
  // Numbers are compact-formatted; strings (e.g. percentages) shown as is
  values: (number | string | null | undefined)[]
}

/** A label column followed by right-aligned values. */
export function MetricsTable({
  labelHeader,
  valueHeaders,
  rows,
}: {
  labelHeader: string
  valueHeaders: string[]
  rows: MetricsTableRow[]
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{labelHeader}</TableHead>
          {valueHeaders.map((header) => (
            <TableHead key={header} className="text-right">
              {header}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.key}>
            <TableCell className="max-w-xs">{row.label}</TableCell>
            {row.values.map((value, i) => (
              <TableCell key={valueHeaders[i]} className="text-right">
                {typeof value === "string" ? value : formatCompact(value)}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
