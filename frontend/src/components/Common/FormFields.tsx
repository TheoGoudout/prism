import type { ComponentProps, ReactNode } from "react"
import type { Control, FieldPath, FieldValues } from "react-hook-form"

import { Checkbox } from "@/components/ui/checkbox"
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { PasswordInput } from "@/components/ui/password-input"

interface FieldProps<T extends FieldValues> {
  control: Control<T>
  name: FieldPath<T>
  label: ReactNode
  /** Marks the label with a red asterisk. */
  required?: boolean
  description?: ReactNode
  className?: string
}

type InputProps = Omit<ComponentProps<"input">, "name" | "required">

/** The label, with an asterisk on required fields. */
function FieldLabel({
  label,
  required,
}: {
  label: ReactNode
  required?: boolean
}) {
  return (
    <FormLabel>
      {label}
      {required && <span className="text-destructive"> *</span>}
    </FormLabel>
  )
}

function makeInputField(Control: typeof Input | typeof PasswordInput) {
  return function InputField<T extends FieldValues>({
    control,
    name,
    label,
    required,
    description,
    className,
    ...inputProps
  }: FieldProps<T> & InputProps) {
    return (
      <FormField
        control={control}
        name={name}
        render={({ field, fieldState }) => (
          <FormItem className={className}>
            <FieldLabel label={label} required={required} />
            <FormControl>
              <Control
                {...field}
                aria-invalid={fieldState.invalid}
                {...inputProps}
              />
            </FormControl>
            {description && <FormDescription>{description}</FormDescription>}
            <FormMessage />
          </FormItem>
        )}
      />
    )
  }
}

/** A labelled text input bound to a react-hook-form field. */
export const TextField = makeInputField(Input)

/** A labelled password input, with a button to show what was typed. */
export const PasswordField = makeInputField(PasswordInput)

/** A checkbox with its label on the right. */
export function CheckboxField<T extends FieldValues>({
  control,
  name,
  label,
  disabled,
}: Pick<FieldProps<T>, "control" | "name" | "label"> & {
  disabled?: boolean
}) {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem className="flex items-center gap-3 space-y-0">
          <FormControl>
            <Checkbox
              checked={field.value}
              onCheckedChange={(checked) => field.onChange(checked === true)}
              disabled={disabled}
            />
          </FormControl>
          <FormLabel className="font-normal">{label}</FormLabel>
        </FormItem>
      )}
    />
  )
}
