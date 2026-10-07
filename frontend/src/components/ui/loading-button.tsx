import { Loader2, type LucideIcon } from "lucide-react"
import type { ComponentProps } from "react"

import { Button } from "@/components/ui/button"

type LoadingButtonProps = ComponentProps<typeof Button> & {
  loading?: boolean
  /** Shown before the label; a spinner takes its place while loading. */
  icon?: LucideIcon
}

/** A button that is disabled, with a spinner, while its action runs. */
function LoadingButton({
  loading = false,
  icon: Icon,
  disabled,
  children,
  ...props
}: LoadingButtonProps) {
  return (
    <Button disabled={loading || disabled} {...props}>
      {loading ? <Loader2 className="animate-spin" /> : Icon && <Icon />}
      {children}
    </Button>
  )
}

export { LoadingButton }
