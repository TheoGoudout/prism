import { zodResolver } from "@hookform/resolvers/zod"
import { createFileRoute } from "@tanstack/react-router"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { AuthForm } from "@/components/Common/AuthForm"
import { PasswordField, TextField } from "@/components/Common/FormFields"
import useAuth from "@/hooks/useAuth"
import { pageHead, redirectIfLoggedIn } from "@/lib/routing"
import {
  confirmPasswordSchema,
  emailSchema,
  PASSWORDS_DONT_MATCH,
  passwordSchema,
  passwordsMatch,
} from "@/lib/validation"

const formSchema = z
  .object({
    email: emailSchema,
    full_name: z.string().min(1, { message: "Full Name is required" }),
    password: passwordSchema,
    confirm_password: confirmPasswordSchema,
  })
  .refine(passwordsMatch("password"), PASSWORDS_DONT_MATCH)

type FormData = z.infer<typeof formSchema>

export const Route = createFileRoute("/signup")({
  component: SignUp,
  beforeLoad: redirectIfLoggedIn,
  head: pageHead("Sign Up"),
})

function SignUp() {
  const { signUpMutation } = useAuth()
  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      email: "",
      full_name: "",
      password: "",
      confirm_password: "",
    },
  })

  return (
    <AuthForm
      title="Create an account"
      form={form}
      onSubmit={({ confirm_password: _, ...user }) =>
        signUpMutation.mutate(user)
      }
      submitLabel="Sign Up"
      loading={signUpMutation.isPending}
      footer={{
        text: "Already have an account?",
        linkLabel: "Log in",
        to: "/login",
      }}
    >
      <TextField
        control={form.control}
        name="full_name"
        label="Full Name"
        placeholder="User"
        data-testid="full-name-input"
      />
      <TextField
        control={form.control}
        name="email"
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
