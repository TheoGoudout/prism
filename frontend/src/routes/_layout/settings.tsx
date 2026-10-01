import { createFileRoute } from "@tanstack/react-router"

import ChangePassword from "@/components/UserSettings/ChangePassword"
import DeleteAccount from "@/components/UserSettings/DeleteAccount"
import UserInformation from "@/components/UserSettings/UserInformation"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import WorkspaceGeneral from "@/components/Workspaces/WorkspaceGeneral"
import WorkspaceMembers from "@/components/Workspaces/WorkspaceMembers"
import { useWorkspace } from "@/contexts/WorkspaceContext"
import useAuth from "@/hooks/useAuth"

const userTabs = [
  { value: "my-profile", title: "My profile", component: UserInformation },
  { value: "password", title: "Password", component: ChangePassword },
  { value: "danger-zone", title: "Danger zone", component: DeleteAccount },
]

const workspaceTabs = [
  { value: "workspace", title: "Workspace", component: WorkspaceGeneral },
  { value: "members", title: "Members", component: WorkspaceMembers },
]

export const Route = createFileRoute("/_layout/settings")({
  component: Settings,
  validateSearch: (search: Record<string, unknown>): { tab?: string } => ({
    tab: typeof search.tab === "string" ? search.tab : undefined,
  }),
  head: () => ({
    meta: [
      {
        title: "Settings - Prism",
      },
    ],
  }),
})

function Settings() {
  const { user: currentUser } = useAuth()
  const { currentWorkspace } = useWorkspace()
  const { tab } = Route.useSearch()
  const navigate = Route.useNavigate()

  if (!currentUser) {
    return null
  }

  // Superusers can't delete their own account
  const tabs = [
    ...userTabs.filter(
      (t) => !(currentUser.is_superuser && t.value === "danger-zone"),
    ),
    ...(currentWorkspace ? workspaceTabs : []),
  ]
  const activeTab = tabs.some((t) => t.value === tab) ? tab : "my-profile"

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          Manage your account
          {currentWorkspace
            ? ` and the ${currentWorkspace.name} workspace`
            : ""}
        </p>
      </div>

      <Tabs
        value={activeTab}
        onValueChange={(value) =>
          navigate({ search: { tab: value }, replace: true })
        }
      >
        <TabsList className="flex-wrap h-auto">
          {tabs.map((t) => (
            <TabsTrigger key={t.value} value={t.value}>
              {t.title}
            </TabsTrigger>
          ))}
        </TabsList>
        {tabs.map((t) => (
          <TabsContent key={t.value} value={t.value}>
            <t.component />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
