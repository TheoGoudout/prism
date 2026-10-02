import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { VERDICT_CLASSES, VERDICT_LABELS, type Verdict } from "./labels"

export function VerdictBadge({
  verdict,
  className,
}: {
  verdict: Verdict
  className?: string
}) {
  return (
    <Badge className={cn(VERDICT_CLASSES[verdict], className)}>
      {VERDICT_LABELS[verdict]}
    </Badge>
  )
}
