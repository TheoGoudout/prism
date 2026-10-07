import { Link } from "@tanstack/react-router"

import { Button } from "@/components/ui/button"

/** A full-page message (404, crash) with a way back home. */
export function ErrorPage({
  code,
  message,
  action,
  testId,
}: {
  code: string
  message: string
  action: string
  testId: string
}) {
  return (
    <div
      className="flex min-h-screen flex-col items-center justify-center gap-4 p-4 text-center"
      data-testid={testId}
    >
      <span className="text-6xl font-bold leading-none md:text-8xl">
        {code}
      </span>
      <span className="text-2xl font-bold">Oops!</span>
      <p className="text-lg text-muted-foreground">{message}</p>
      <Button asChild>
        <Link to="/">{action}</Link>
      </Button>
    </div>
  )
}
