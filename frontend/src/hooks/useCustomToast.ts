import { AxiosError } from "axios"
import { toast } from "sonner"

import { ApiError } from "@/client"

/** The human-readable message of a failed API call. */
function apiErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const detail = (err.body as { detail?: unknown } | undefined)?.detail
    // FastAPI validation errors are a list of {msg, ...}
    if (Array.isArray(detail) && detail.length > 0) return String(detail[0].msg)
    if (typeof detail === "string" && detail) return detail
  }
  if (err instanceof AxiosError || err instanceof Error) return err.message
  return "Something went wrong."
}

const showSuccessToast = (description: string) => {
  toast.success("Success!", { description })
}

const showErrorToast = (description: string) => {
  toast.error("Something went wrong!", { description })
}

const showApiError = (err: unknown) => showErrorToast(apiErrorMessage(err))

// The functions are module-level, so they keep the same identity across
// renders and are safe to use in effect dependencies.
const useCustomToast = () => ({
  showSuccessToast,
  showErrorToast,
  showApiError,
})

export default useCustomToast
