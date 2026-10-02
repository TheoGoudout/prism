import { z } from "zod"

const MAX_RECIPIENTS = 20

/** Addresses typed in one field, separated by commas, semicolons or spaces. */
export const splitEmails = (value: string) =>
  value
    .split(/[\s,;]+/)
    .map((email) => email.trim())
    .filter(Boolean)

/** Why a recipients field is invalid, or null. */
export function recipientsError(
  value: string,
  required: boolean,
): string | null {
  const emails = splitEmails(value)
  const invalid = emails.find((e) => !z.email().safeParse(e).success)
  if (invalid) return `${invalid} is not a valid email address`
  if (emails.length > MAX_RECIPIENTS)
    return `At most ${MAX_RECIPIENTS} recipients`
  if (required && emails.length === 0) return "Add at least one recipient"
  return null
}
