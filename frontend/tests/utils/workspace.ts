import { expect, type Page } from "@playwright/test"

export const randomWorkspaceName = () =>
  `Workspace ${Math.random().toString(36).substring(7)}`

/** Wait until the app has loaded past the auth redirect. */
async function waitForAppShell(page: Page) {
  await expect(
    page
      .getByRole("heading", { name: "Create your first workspace" })
      .or(page.getByTestId("user-menu")),
  ).toBeVisible()
}

/** Complete the "create your first workspace" onboarding through the UI. */
export async function createFirstWorkspace(
  page: Page,
  name: string = randomWorkspaceName(),
) {
  await page.getByRole("button", { name: "Create workspace" }).click()
  await page.getByLabel("Name").fill(name)
  await page.getByRole("button", { name: "Create", exact: true }).click()
  await expect(page.getByTestId("user-menu")).toBeVisible()
  return name
}

/**
 * Make sure the logged-in user has a workspace, creating one if they land
 * on the onboarding screen. Returns once the main app shell is visible.
 */
export async function ensureWorkspace(page: Page) {
  await waitForAppShell(page)
  if (await page.getByTestId("user-menu").isVisible()) return
  await createFirstWorkspace(page)
}

export async function expectDashboard(page: Page) {
  await expect(page.getByText("Last 7 days")).toBeVisible()
}
