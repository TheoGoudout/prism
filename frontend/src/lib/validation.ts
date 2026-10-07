import { z } from "zod"

/** The API's password rule: at least 8 characters. */
export const passwordSchema = z
  .string()
  .min(1, { message: "Password is required" })
  .min(8, { message: "Password must be at least 8 characters" })

export const confirmPasswordSchema = z
  .string()
  .min(1, { message: "Password confirmation is required" })

/**
 * Whether `confirm_password` repeats the `password` field (an empty optional
 * password needs no confirmation), for a schema's `.refine`:
 * `.refine(passwordsMatch("new_password"), PASSWORDS_DONT_MATCH)`.
 */
export const passwordsMatch =
  <K extends string>(password: K) =>
  (data: Partial<Record<K | "confirm_password", string>>) =>
    !data[password] || data[password] === data.confirm_password

export const PASSWORDS_DONT_MATCH = {
  message: "The passwords don't match",
  path: ["confirm_password"],
}

export const emailSchema = z.email({ message: "Invalid email address" })
