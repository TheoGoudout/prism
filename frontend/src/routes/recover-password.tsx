import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { LoginService } from "@/client"
import { AuthForm } from "@/components/Common/AuthForm"
import { TextField } from "@/components/Common/FormFields"
import useCustomToast from "@/hooks/useCustomToast"
import { pageHead, redirectIfLoggedIn } from "@/lib/routing"
import { emailSchema } from "@/lib/validation"

const formSchema = z.object({ email: emailSchema })

type FormData = z.infer<typeof formSchema>

export const Route = createFileRoute("/recover-password")({
  component: RecoverPassword,
  beforeLoad: redirectIfLoggedIn,
  head: pageHead("Recover Password"),
})

function RecoverPassword() {
  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    defaultValues: { email: "" },
  })
  const { showSuccessToast, showApiError } = useCustomToast()

  const mutation = useMutation({
    mutationFn: ({ email }: FormData) =>
      LoginService.recoverPassword({ email }),
    onSuccess: () => {
      showSuccessToast("Password recovery email sent successfully")
      form.reset()
    },
    onError: showApiError,
  })

  return (
    <AuthForm
      title="Password Recovery"
      form={form}
      onSubmit={(data) => mutation.mutate(data)}
      submitLabel="Continue"
      loading={mutation.isPending}
      footer={{
        text: "Remember your password?",
        linkLabel: "Log in",
        to: "/login",
      }}
    >
      <TextField
        control={form.control}
        name="email"
        label="Email"
        type="email"
        placeholder="user@example.com"
        data-testid="email-input"
      />
    </AuthForm>
  )
}
