import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation } from "@tanstack/react-query"
import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { LoginService } from "@/client"
import { AuthForm } from "@/components/Common/AuthForm"
import { PasswordField } from "@/components/Common/FormFields"
import useCustomToast from "@/hooks/useCustomToast"
import { pageHead, redirectIfLoggedIn } from "@/lib/routing"
import {
  confirmPasswordSchema,
  PASSWORDS_DONT_MATCH,
  passwordSchema,
  passwordsMatch,
} from "@/lib/validation"

const searchSchema = z.object({
  token: z.string().catch(""),
})

const formSchema = z
  .object({
    new_password: passwordSchema,
    confirm_password: confirmPasswordSchema,
  })
  .refine(passwordsMatch("new_password"), PASSWORDS_DONT_MATCH)

type FormData = z.infer<typeof formSchema>

export const Route = createFileRoute("/reset-password")({
  component: ResetPassword,
  validateSearch: searchSchema,
  beforeLoad: ({ search }) => {
    redirectIfLoggedIn()
    if (!search.token) {
      throw redirect({ to: "/login" })
    }
  },
  head: pageHead("Reset Password"),
})

function ResetPassword() {
  const { token } = Route.useSearch()
  const { showSuccessToast, showApiError } = useCustomToast()
  const navigate = useNavigate()

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: { new_password: "", confirm_password: "" },
  })

  const mutation = useMutation({
    mutationFn: ({ new_password }: FormData) =>
      LoginService.resetPassword({ requestBody: { new_password, token } }),
    onSuccess: () => {
      showSuccessToast("Password updated successfully")
      form.reset()
      navigate({ to: "/login" })
    },
    onError: showApiError,
  })

  return (
    <AuthForm
      title="Reset Password"
      form={form}
      onSubmit={(data) => mutation.mutate(data)}
      submitLabel="Reset Password"
      loading={mutation.isPending}
      footer={{
        text: "Remember your password?",
        linkLabel: "Log in",
        to: "/login",
      }}
    >
      <PasswordField
        control={form.control}
        name="new_password"
        label="New Password"
        placeholder="New Password"
        data-testid="new-password-input"
      />
      <PasswordField
        control={form.control}
        name="confirm_password"
        label="Confirm Password"
        placeholder="Confirm Password"
        data-testid="confirm-password-input"
      />
    </AuthForm>
  )
}
