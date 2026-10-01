import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

/** Placeholder rows shown while a list or table loads. */
export function SkeletonRows({
  count = 3,
  className = "h-12",
}: {
  count?: number
  className?: string
}) {
  return (
    <div className="space-y-2">
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} className={cn("w-full", className)} />
      ))}
    </div>
  )
}
