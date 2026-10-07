import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { type UpdatePassword, UsersService } from "@/client"
import { PasswordField } from "@/components/Common/FormFields"
import { Form } from "@/components/ui/form"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"
import {
  confirmPasswordSchema,
  PASSWORDS_DONT_MATCH,
  passwordSchema,
  passwordsMatch,
} from "@/lib/validation"

const formSchema = z
  .object({
    current_password: passwordSchema,
    new_password: passwordSchema,
    confirm_password: confirmPasswordSchema,
  })
  .refine(passwordsMatch("new_password"), PASSWORDS_DONT_MATCH)

type FormData = z.infer<typeof formSchema>

const ChangePassword = () => {
  const { showSuccessToast, showApiError } = useCustomToast()
  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onSubmit",
    criteriaMode: "all",
    defaultValues: {
      current_password: "",
      new_password: "",
      confirm_password: "",
    },
  })

  const mutation = useMutation({
    mutationFn: (data: UpdatePassword) =>
      UsersService.updatePasswordMe({ requestBody: data }),
    onSuccess: () => {
      showSuccessToast("Password updated successfully")
      form.reset()
    },
    onError: showApiError,
  })

  return (
    <div className="max-w-md">
      <h3 className="text-lg font-semibold py-4">Change Password</h3>
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(({ confirm_password: _, ...data }) =>
            mutation.mutate(data),
          )}
          className="flex flex-col gap-4"
        >
          <PasswordField
            control={form.control}
            name="current_password"
            label="Current Password"
            placeholder="••••••••"
            data-testid="current-password-input"
          />
          <PasswordField
            control={form.control}
            name="new_password"
            label="New Password"
            placeholder="••••••••"
            data-testid="new-password-input"
          />
          <PasswordField
            control={form.control}
            name="confirm_password"
            label="Confirm Password"
            placeholder="••••••••"
            data-testid="confirm-password-input"
          />

          <LoadingButton
            type="submit"
            loading={mutation.isPending}
            className="self-start"
          >
            Update Password
          </LoadingButton>
        </form>
      </Form>
    </div>
  )
}

export default ChangePassword
