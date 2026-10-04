import { expect, test } from "@playwright/test"
import { createUser } from "./utils/privateApi"
import { randomEmail, randomPassword } from "./utils/random"
import { logInOnly } from "./utils/user"
import { createFirstWorkspace } from "./utils/workspace"

test.use({ storageState: { cookies: [], origins: [] } })

test("Analytics compares the period with another one", async ({ page }) => {
  const email = randomEmail()
  const password = randomPassword()
  await createUser({ email, password })
  await logInOnly(page, email, password)
  await createFirstWorkspace(page)

  await page.goto("/analytics?from=2026-03-01&to=2026-03-31")
  await expect(page.getByText(/^Mar 1 – Mar 31 ·/)).toBeVisible()

  await page.getByRole("button", { name: "Previous month" }).click()

  await expect(page).toHaveURL(/compareFrom=2026-02-01/)
  await expect(page).toHaveURL(/compareTo=2026-02-28/)
  await expect(
    page.getByText(/^Mar 1 – Mar 31 vs Feb 1 – Feb 28 ·/),
  ).toBeVisible()
  await expect(
    page.getByText(
      "The periods have different lengths: counts are compared per day.",
    ),
  ).toBeVisible()

  await page.getByRole("button", { name: "Stop comparing" }).click()
  await expect(page).not.toHaveURL(/compareFrom/)
})
