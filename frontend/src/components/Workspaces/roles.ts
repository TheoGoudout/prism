import type { WorkspacePublic, WorkspaceRole } from "@/client"

export const ROLE_LABELS: Record<WorkspaceRole, string> = {
  owner: "Owner",
  admin: "Admin",
  viewer: "Viewer",
}

export const ROLE_DESCRIPTIONS: Record<WorkspaceRole, string> = {
  owner: "Full control, including deleting the workspace",
  admin: "Manage integrations and members",
  viewer: "View dashboards and reports",
}

/** Owners and admins can manage integrations, members and settings. */
export function canManage(workspace: WorkspacePublic | null): boolean {
  return workspace?.role === "owner" || workspace?.role === "admin"
}
