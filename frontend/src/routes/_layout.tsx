import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"

import { Footer } from "@/components/Common/Footer"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import { MobileTabBar } from "@/components/Sidebar/MobileTabBar"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { Skeleton } from "@/components/ui/skeleton"
import { NoWorkspace } from "@/components/Workspaces/NoWorkspace"
import { useWorkspace, WorkspaceProvider } from "@/contexts/WorkspaceContext"
import { isLoggedIn } from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout")({
  component: Layout,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({
        to: "/login",
      })
    }
  },
})

function LayoutInner() {
  const { currentWorkspace, isLoading } = useWorkspace()

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Skeleton className="h-8 w-48" />
      </div>
    )
  }

  // Pages below can rely on a workspace being selected (useCurrentWorkspace)
  if (!currentWorkspace) {
    return <NoWorkspace />
  }

  return (
    <SidebarProvider>
      <AppSidebar />
      {/* min-w-0: wide content (e.g. tables) scrolls instead of widening the page */}
      <SidebarInset className="bg-prism-glow min-w-0">
        <div aria-hidden="true" className="bg-spectrum h-1 shrink-0" />
        <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b bg-background/70 px-4 backdrop-blur">
          <SidebarTrigger className="-ml-1 text-muted-foreground" />
        </header>
        <main className="flex-1 p-6 pb-24 md:p-8">
          <div className="mx-auto max-w-7xl">
            <Outlet />
          </div>
        </main>
        {/* On phones the tab bar takes the footer's place */}
        <div className="hidden md:block">
          <Footer />
        </div>
        <MobileTabBar />
      </SidebarInset>
    </SidebarProvider>
  )
}

function Layout() {
  return (
    <WorkspaceProvider>
      <LayoutInner />
    </WorkspaceProvider>
  )
}
