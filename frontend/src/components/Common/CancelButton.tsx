import type { ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { DialogClose } from "@/components/ui/dialog"

/** Closes the dialog it is in, without submitting its form. */
export function CancelButton({
  disabled,
  children = "Cancel",
}: {
  disabled?: boolean
  children?: ReactNode
}) {
  return (
    <DialogClose asChild>
      <Button variant="outline" type="button" disabled={disabled}>
        {children}
      </Button>
    </DialogClose>
  )
}
