import { useQuery } from "@tanstack/react-query"

import { WorkspacesService } from "@/client"
import { SkeletonRows } from "@/components/Common/SkeletonRows"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useCurrentWorkspace } from "@/contexts/WorkspaceContext"
import useAuth from "@/hooks/useAuth"
import { AddMemberForm } from "./AddMemberForm"
import { MemberRow } from "./MemberRow"
import { canManage, ROLE_DESCRIPTIONS } from "./roles"

export default function WorkspaceMembers() {
  const workspace = useCurrentWorkspace()
  const { user } = useAuth()

  const membersQ = useQuery({
    queryKey: ["members", workspace.id],
    queryFn: () => WorkspacesService.listMembers({ workspaceId: workspace.id }),
  })
  const members = membersQ.data?.data ?? []
  const ownerCount = members.filter((m) => m.role === "owner").length

  return (
    <div className="flex flex-col gap-6 max-w-3xl">
      {canManage(workspace) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Add a member</CardTitle>
            <CardDescription>
              They need a Prism account first. Viewers can{" "}
              {ROLE_DESCRIPTIONS.viewer.toLowerCase()}, admins can also{" "}
              {ROLE_DESCRIPTIONS.admin.toLowerCase()}.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <AddMemberForm />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Members{membersQ.data ? ` (${membersQ.data.count})` : ""}
          </CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {membersQ.isLoading ? (
            <SkeletonRows />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Member</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {members.map((m) => (
                  <MemberRow
                    key={m.user_id}
                    member={m}
                    isMe={m.user_id === user?.id}
                    isLastOwner={m.role === "owner" && ownerCount === 1}
                  />
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
