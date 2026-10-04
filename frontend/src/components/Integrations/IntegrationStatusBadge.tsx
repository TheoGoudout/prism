import type { IntegrationStatus } from "@/client"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

const VARIANTS: Record<
  IntegrationStatus,
  "default" | "secondary" | "destructive"
> = {
  active: "default",
  error: "destructive",
  expired: "destructive",
  disconnected: "secondary",
}

export function IntegrationStatusBadge({
  status,
  className,
}: {
  status: IntegrationStatus
  className?: string
}) {
  return (
    <Badge
      variant={VARIANTS[status]}
      className={cn(
        "capitalize",
        status === "active" &&
          "border-transparent bg-success/12 text-success [a&]:hover:bg-success/20",
        className,
      )}
    >
      {status}
    </Badge>
  )
}
