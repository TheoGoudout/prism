import { zodResolver } from "@hookform/resolvers/zod"
import { createFileRoute, Link as RouterLink } from "@tanstack/react-router"
import { useForm } from "react-hook-form"
import { z } from "zod"

import type { Body_login_login_access_token as AccessToken } from "@/client"
import { AuthForm } from "@/components/Common/AuthForm"
import { PasswordField, TextField } from "@/components/Common/FormFields"
import useAuth from "@/hooks/useAuth"
import { pageHead, redirectIfLoggedIn } from "@/lib/routing"
import { emailSchema, passwordSchema } from "@/lib/validation"

const formSchema = z.object({
  username: emailSchema,
  password: passwordSchema,
}) satisfies z.ZodType<AccessToken>

type FormData = z.infer<typeof formSchema>

export const Route = createFileRoute("/login")({
  component: Login,
  beforeLoad: redirectIfLoggedIn,
  head: pageHead("Log In"),
})

function Login() {
  const { loginMutation } = useAuth()
  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: { username: "", password: "" },
  })

  return (
    <AuthForm
      title="Login to your account"
      form={form}
      onSubmit={(data) => loginMutation.mutate(data)}
      submitLabel="Log In"
      loading={loginMutation.isPending}
      footer={{
        text: "Don't have an account yet?",
        linkLabel: "Sign up",
        to: "/signup",
      }}
    >
      <TextField
        control={form.control}
        name="username"
        label="Email"
        type="email"
        placeholder="user@example.com"
        data-testid="email-input"
      />
      <PasswordField
        control={form.control}
        name="password"
        label="Password"
        placeholder="Password"
        data-testid="password-input"
      />
      <RouterLink
        to="/recover-password"
        className="-mt-2 justify-self-end text-sm underline-offset-4 hover:underline"
      >
        Forgot your password?
      </RouterLink>
    </AuthForm>
  )
}
