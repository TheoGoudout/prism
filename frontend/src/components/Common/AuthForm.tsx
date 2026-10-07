import { Link as RouterLink } from "@tanstack/react-router"
import type { ReactNode } from "react"
import type { FieldValues, UseFormReturn } from "react-hook-form"

import { AuthLayout } from "@/components/Common/AuthLayout"
import { Form } from "@/components/ui/form"
import { LoadingButton } from "@/components/ui/loading-button"

/**
 * The form of a logged-out page (log in, sign up...): a title, the fields,
 * the submit button, and a link to the page to go to instead.
 */
export function AuthForm<T extends FieldValues>({
  title,
  form,
  onSubmit,
  submitLabel,
  loading,
  children,
  footer,
}: {
  title: string
  form: UseFormReturn<T>
  onSubmit: (data: T) => void
  submitLabel: string
  loading: boolean
  children: ReactNode
  footer: { text: string; linkLabel: string; to: "/login" | "/signup" }
}) {
  return (
    <AuthLayout>
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit((data) => {
            if (!loading) onSubmit(data)
          })}
          className="flex flex-col gap-6"
        >
          <h1 className="text-center text-2xl font-bold">{title}</h1>

          <div className="grid gap-4">
            {children}
            <LoadingButton type="submit" className="w-full" loading={loading}>
              {submitLabel}
            </LoadingButton>
          </div>

          <div className="text-center text-sm">
            {footer.text}{" "}
            <RouterLink to={footer.to} className="underline underline-offset-4">
              {footer.linkLabel}
            </RouterLink>
          </div>
        </form>
      </Form>
    </AuthLayout>
  )
}
