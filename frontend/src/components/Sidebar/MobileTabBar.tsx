import { Link, useRouterState } from "@tanstack/react-router"

import { cn } from "@/lib/utils"
import { navItems } from "./AppSidebar"

/**
 * The main sections as a tab bar along the bottom of the screen, on phones
 * only: community managers check their numbers between meetings, one-handed.
 * Everything else (workspace, admin, settings) stays in the sidebar sheet.
 */
export function MobileTabBar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })

  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 flex border-t bg-card/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden">
      {navItems.map((item) => {
        const active =
          item.path === "/"
            ? pathname === "/"
            : pathname === item.path || pathname.startsWith(`${item.path}/`)
        return (
          <Link
            key={item.path}
            to={item.path}
            className={cn(
              "relative flex flex-1 flex-col items-center gap-1 py-2 text-[0.6875rem] font-medium",
              active ? "text-primary" : "text-muted-foreground",
            )}
          >
            {active && (
              <span
                aria-hidden="true"
                className="bg-spectrum absolute inset-x-4 top-0 h-0.5 rounded-full"
              />
            )}
            <item.icon className="size-5" />
            <span className="max-w-full truncate px-1">{item.title}</span>
          </Link>
        )
      })}
    </nav>
  )
}
