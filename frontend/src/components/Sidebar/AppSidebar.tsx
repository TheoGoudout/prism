import {
  BarChart2,
  Home,
  Link2,
  Newspaper,
  Sparkles,
  Users,
} from "lucide-react"

import { SidebarAppearance } from "@/components/Common/Appearance"
import { Logo } from "@/components/Common/Logo"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarSeparator,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { type Item, Main } from "./Main"
import { User } from "./User"
import { WorkspaceSelector } from "./WorkspaceSelector"

/** The app's sections, shared by the sidebar and the mobile tab bar. */
export const navItems: Item[] = [
  { icon: Home, title: "Dashboard", path: "/" },
  { icon: BarChart2, title: "Analytics", path: "/analytics" },
  { icon: Newspaper, title: "Posts", path: "/posts" },
  { icon: Sparkles, title: "AI Analysis", path: "/ai-analysis" },
  { icon: Link2, title: "Integrations", path: "/integrations" },
]

function AppSidebar() {
  const { user: currentUser } = useAuth()

  const items = currentUser?.is_superuser
    ? [...navItems, { icon: Users, title: "Admin", path: "/admin" }]
    : navItems

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-4 py-4 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Logo variant="responsive" className="text-sidebar-accent-foreground" />
        <WorkspaceSelector />
      </SidebarHeader>
      <SidebarSeparator />
      <SidebarContent>
        <Main items={items} />
      </SidebarContent>
      <SidebarFooter>
        <SidebarAppearance />
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
