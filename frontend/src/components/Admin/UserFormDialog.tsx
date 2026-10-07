import type { ReactNode } from "react"
import type { UseFormReturn } from "react-hook-form"
import { z } from "zod"
import { CancelButton } from "@/components/Common/CancelButton"
import {
  CheckboxField,
  PasswordField,
  TextField,
} from "@/components/Common/FormFields"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Form } from "@/components/ui/form"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  confirmPasswordSchema,
  emailSchema,
  PASSWORDS_DONT_MATCH,
  passwordSchema,
  passwordsMatch,
} from "@/lib/validation"

/** A new user needs a password; an edited one keeps theirs if left empty. */
export function userFormSchema(creating: boolean) {
  return z
    .object({
      email: emailSchema,
      full_name: z.string().optional(),
      password: creating
        ? passwordSchema
        : z.union([z.literal(""), passwordSchema]),
      confirm_password: creating ? confirmPasswordSchema : z.string(),
      is_superuser: z.boolean(),
      is_active: z.boolean(),
    })
    .refine(passwordsMatch("password"), PASSWORDS_DONT_MATCH)
}

export type UserFormData = z.infer<ReturnType<typeof userFormSchema>>

/** The user as the API takes it: no confirmation, no empty password. */
export function toUserUpdate({
  confirm_password: _,
  password,
  ...user
}: UserFormData) {
  return password ? { ...user, password } : user
}

/** The admin's form to create or edit a user, in a dialog. */
export function UserFormDialog({
  open,
  onOpenChange,
  trigger,
  title,
  description,
  form,
  onSubmit,
  loading,
  creating,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  trigger: ReactNode
  title: string
  description: string
  form: UseFormReturn<UserFormData>
  onSubmit: (data: UserFormData) => void
  loading: boolean
  creating: boolean
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {trigger}
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <div className="grid gap-4 py-4">
              <TextField
                control={form.control}
                name="email"
                label="Email"
                type="email"
                placeholder="Email"
                required
              />
              <TextField
                control={form.control}
                name="full_name"
                label="Full Name"
                placeholder="Full name"
              />
              <PasswordField
                control={form.control}
                name="password"
                label="Set Password"
                placeholder="Password"
                required={creating}
              />
              <PasswordField
                control={form.control}
                name="confirm_password"
                label="Confirm Password"
                placeholder="Password"
                required={creating}
              />
              <CheckboxField
                control={form.control}
                name="is_superuser"
                label="Is superuser?"
              />
              <CheckboxField
                control={form.control}
                name="is_active"
                label="Is active?"
              />
            </div>

            <DialogFooter>
              <CancelButton disabled={loading} />
              <LoadingButton type="submit" loading={loading}>
                Save
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
