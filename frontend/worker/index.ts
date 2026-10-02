/**
 * Cloudflare Worker in front of the frontend's static assets.
 *
 * Static assets are served by the `ASSETS` binding, which applies the
 * `single-page-application` not-found handling declared in `wrangler.jsonc`,
 * so unknown paths fall back to `index.html`.
 *
 * The only thing this Worker adds is what `nginx-backend-not-found.conf` does
 * in the Docker image: API-looking paths 404 instead of being answered by the
 * SPA shell, so a client pointed at the wrong host fails loudly.
 */

interface Env {
  ASSETS: { fetch: (request: Request) => Promise<Response> }
}

const BACKEND_PREFIXES = ["/api", "/docs", "/redoc"]

const isBackendPath = (pathname: string): boolean =>
  BACKEND_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  )

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url)

    if (isBackendPath(pathname)) {
      return new Response("Not Found", { status: 404 })
    }

    return env.ASSETS.fetch(request)
  },
}
