import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import type { TimeSeriesPoint } from "@/client"
import { Skeleton } from "@/components/ui/skeleton"
import { formatCompact } from "@/lib/format"

// Theme chart colours (defined in index.css; they adapt to dark mode)
const SERIES: { key: keyof TimeSeriesPoint; name: string; color: string }[] = [
  { key: "exposures", name: "Views", color: "var(--chart-1)" },
  { key: "reach", name: "Reach", color: "var(--chart-2)" },
  { key: "engagements", name: "Engagements", color: "var(--chart-3)" },
]

export function TrendChart({
  points,
  loading,
}: {
  points: TimeSeriesPoint[]
  loading: boolean
}) {
  if (loading) return <Skeleton className="h-64 w-full" />

  const data = points.map((point) => ({ ...point, day: point.date.slice(5) })) // MM-DD
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
        <XAxis
          dataKey="day"
          tick={{ fontSize: 11 }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tickFormatter={formatCompact}
          tick={{ fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          width={48}
        />
        <Tooltip
          formatter={(value) => formatCompact(value as number)}
          contentStyle={{ fontSize: 12, borderRadius: 6 }}
        />
        <Legend iconSize={10} wrapperStyle={{ fontSize: 12 }} />
        {SERIES.map(({ key, name, color }) => (
          <Line
            key={key}
            type="monotone"
            dataKey={key}
            name={name}
            stroke={color}
            dot={false}
            strokeWidth={2}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
