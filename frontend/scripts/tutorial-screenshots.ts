/**
 * Regenerates the Prism screenshots used by the "How to connect your
 * accounts" guides on the Integrations page
 * (public/assets/images/tutorials/).
 *
 * Builds the frontend (so dev-only overlays don't show) and runs it against
 * a mocked API, so no backend is needed:
 *
 *   bun run tutorial-screenshots
 *
 * Re-run it whenever the Integrations page changes.
 */
import { type ChildProcess, spawn, spawnSync } from "node:child_process"
import { mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { chromium, type Page } from "@playwright/test"

import type { IntegrationPublic, Platform } from "../src/client"
import { PLATFORM_LABELS, PLATFORMS } from "../src/lib/platforms"

const here = path.dirname(fileURLToPath(import.meta.url))
const OUT_DIR = path.join(here, "../public/assets/images/tutorials")
const PORT = 5179
const APP = `http://localhost:${PORT}`
const API = "http://api.prism.test"

const WORKSPACE = {
  id: "00000000-0000-0000-0000-000000000001",
  name: "Acme Coffee",
  slug: "acme-coffee",
  role: "owner",
}

const ACCOUNT_NAMES: Record<Platform, string> = {
  facebook: "Acme Coffee",
  instagram: "@acmecoffee",
  twitter: "@acmecoffee",
  linkedin: "Acme Coffee Ltd",
  tiktok: "acmecoffee",
  google_analytics: "acmecoffee.com",
}

function integration(platform: Platform): IntegrationPublic {
  return {
    id: `00000000-0000-0000-0001-00000000000${PLATFORMS.indexOf(platform)}`,
    workspace_id: WORKSPACE.id,
    platform,
    status: "active",
    external_account_id: "1",
    external_account_name: ACCOUNT_NAMES[platform],
    last_synced_at: new Date().toISOString(),
  }
}

/** Answer the app's API calls with fixed data; `integrations` is mutable. */
async function mockApi(page: Page, integrations: IntegrationPublic[]) {
  await page.route(`${API}/**`, async (route) => {
    const url = new URL(route.request().url())
    const json = (body: unknown) => route.fulfill({ json: body })
    if (url.pathname === "/api/v1/users/me") {
      return json({
        id: "u1",
        email: "sam@acmecoffee.com",
        full_name: "Sam Taylor",
        is_active: true,
        is_superuser: false,
      })
    }
    if (url.pathname === "/api/v1/workspaces/") return json([WORKSPACE])
    if (url.pathname.endsWith("/integrations/")) return json(integrations)
    return json({})
  })
}

/** Build the app and serve it with `vite preview`. */
async function startApp(outDir: string) {
  const cwd = path.join(here, "..")
  const env = { ...process.env, VITE_API_URL: API }
  const build = spawnSync("bunx", ["vite", "build", "--outDir", outDir], {
    cwd,
    env,
    stdio: "inherit",
  })
  if (build.status !== 0) throw new Error("Build failed")
  const server = spawn(
    "bunx",
    [
      "vite",
      "preview",
      "--outDir",
      outDir,
      "--port",
      String(PORT),
      "--strictPort",
    ],
    // Own process group, so stopping it also stops vite under bunx
    { cwd, env, stdio: "ignore", detached: true },
  )
  for (let i = 0; i < 60; i++) {
    try {
      await fetch(APP)
      return server
    } catch {
      await new Promise((r) => setTimeout(r, 500))
    }
  }
  stop(server)
  throw new Error("Preview server did not start")
}

/** Draw a red ring around an element, to show where to click. */
async function highlight(
  page: Page,
  box: { x: number; y: number; width: number; height: number } | null,
) {
  if (!box) throw new Error("Nothing to highlight")
  await page.evaluate((b) => {
    const ring = document.createElement("div")
    Object.assign(ring.style, {
      position: "fixed",
      left: `${b.x - 4}px`,
      top: `${b.y - 4}px`,
      width: `${b.width + 8}px`,
      height: `${b.height + 8}px`,
      border: "3px solid #dc2626",
      borderRadius: "10px",
      pointerEvents: "none",
      zIndex: "2147483647",
    })
    ring.dataset.highlight = ""
    document.body.append(ring)
  }, box)
}

function stop(server: ChildProcess) {
  if (server.pid) process.kill(-server.pid)
}

async function main() {
  const outDir = mkdtempSync(path.join(tmpdir(), "prism-screenshots-"))
  const server = await startApp(outDir)
  // PLAYWRIGHT_CHROMIUM lets you point at an already-installed browser
  const browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM || undefined,
  })
  try {
    const context = await browser.newContext({
      viewport: { width: 1280, height: 720 },
      deviceScaleFactor: 2,
      colorScheme: "light",
    })
    await context.addInitScript(() => {
      localStorage.setItem("access_token", "screenshot")
      localStorage.setItem("vite-ui-theme", "light")
    })
    const page = await context.newPage()

    for (const platform of PLATFORMS) {
      const label = PLATFORM_LABELS[platform]

      // Step 1: the "Connect platform" menu with this platform highlighted
      await mockApi(page, [])
      await page.goto(`${APP}/integrations`)
      await page.getByRole("button", { name: "Connect platform" }).click()
      const item = page.getByRole("menuitem", { name: label })
      await item.hover()
      await highlight(page, await item.boundingBox())
      const menu = page.getByRole("menu")
      const menuBox = await menu.boundingBox()
      if (!menuBox) throw new Error("Menu not visible")
      await page.screenshot({
        path: path.join(OUT_DIR, `${platform}-menu.png`),
        // The page header and the open menu, without the sidebar
        clip: {
          x: 264,
          y: 60,
          width: 1280 - 264,
          height: Math.ceil(menuBox.y + menuBox.height + 16 - 60),
        },
      })
      await page.keyboard.press("Escape")
      await page.unroute(`${API}/**`)

      // Last step: back from the platform, connected
      // A shorter window keeps the toast close to the table
      await page.setViewportSize({ width: 1280, height: 520 })
      await mockApi(page, [integration(platform)])
      await page.goto(`${APP}/integrations?connected=1`)
      await page
        .locator("[data-sonner-toast]")
        .getByText("Platform connected")
        .waitFor()
      await page.getByRole("cell", { name: ACCOUNT_NAMES[platform] }).waitFor()
      // Hide the guides themselves so the shot shows only the result
      await page.addStyleTag({
        content: "[data-connection-guides] { display: none; }",
      })
      await page.screenshot({
        path: path.join(OUT_DIR, `${platform}-connected.png`),
        clip: { x: 256, y: 0, width: 1280 - 256, height: 520 },
      })
      await page.setViewportSize({ width: 1280, height: 720 })
      await page.unroute(`${API}/**`)
      console.log(`✓ ${label}`)
    }
  } finally {
    await browser.close()
    stop(server)
    rmSync(outDir, { recursive: true, force: true })
  }
}

await main()
