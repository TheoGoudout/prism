import { useNavigate } from "@tanstack/react-router"
import { Building2, ChevronsUpDown, Plus, Users } from "lucide-react"
import { useState } from "react"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"
import CreateWorkspaceModal from "@/components/Workspaces/CreateWorkspaceModal"
import { useWorkspace } from "@/contexts/WorkspaceContext"

export function WorkspaceSelector() {
  const { isMobile, setOpenMobile } = useSidebar()
  const navigate = useNavigate()
  const { workspaces, currentWorkspace, setCurrentWorkspace } = useWorkspace()
  const [createOpen, setCreateOpen] = useState(false)

  if (!currentWorkspace) return null

  return (
    <>
      <SidebarMenu>
        <SidebarMenuItem>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <SidebarMenuButton
                size="lg"
                className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
              >
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                  <Building2 className="size-4" />
                </div>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-semibold">
                    {currentWorkspace.name}
                  </span>
                  <span className="truncate text-xs text-muted-foreground capitalize">
                    {currentWorkspace.role}
                  </span>
                </div>
                <ChevronsUpDown className="ml-auto" />
              </SidebarMenuButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg"
              align="start"
              side={isMobile ? "bottom" : "right"}
              sideOffset={4}
            >
              <DropdownMenuLabel className="text-xs text-muted-foreground">
                Workspaces
              </DropdownMenuLabel>
              {workspaces.map((ws) => (
                <DropdownMenuItem
                  key={ws.id}
                  onClick={() => setCurrentWorkspace(ws)}
                  className="gap-2 p-2"
                >
                  <div className="flex size-6 items-center justify-center rounded-sm border">
                    <Building2 className="size-4 shrink-0" />
                  </div>
                  <span className="flex-1 truncate">{ws.name}</span>
                  {ws.id === currentWorkspace.id && (
                    <span className="text-xs text-muted-foreground">
                      Current
                    </span>
                  )}
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                className="gap-2 p-2"
                onClick={() => {
                  setOpenMobile(false)
                  navigate({ to: "/settings", search: { tab: "members" } })
                }}
              >
                <div className="flex size-6 items-center justify-center rounded-md border bg-background">
                  <Users className="size-4" />
                </div>
                <div className="font-medium text-muted-foreground">
                  Members & settings
                </div>
              </DropdownMenuItem>
              <DropdownMenuItem
                className="gap-2 p-2"
                onClick={() => setCreateOpen(true)}
              >
                <div className="flex size-6 items-center justify-center rounded-md border bg-background">
                  <Plus className="size-4" />
                </div>
                <div className="font-medium text-muted-foreground">
                  New workspace
                </div>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </SidebarMenuItem>
      </SidebarMenu>
      <CreateWorkspaceModal
        isOpen={createOpen}
        onClose={() => setCreateOpen(false)}
      />
    </>
  )
}
