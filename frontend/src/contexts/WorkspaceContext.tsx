import { useQuery } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { createContext, useContext, useState } from "react"
import type { WorkspacePublic } from "@/client"
import { WorkspacesService } from "@/client"

const STORAGE_KEY = "prism:workspace_id"

function readStoredId(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null // storage can be unavailable (e.g. privacy mode)
  }
}

function storeId(id: string) {
  try {
    localStorage.setItem(STORAGE_KEY, id)
  } catch {
    // Not remembering the choice across reloads is acceptable
  }
}

interface WorkspaceContextValue {
  workspaces: WorkspacePublic[]
  /** The selected workspace; null only while loading or if the user has none. */
  currentWorkspace: WorkspacePublic | null
  setCurrentWorkspace: (workspace: WorkspacePublic) => void
  isLoading: boolean
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null)

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [selectedId, setSelectedId] = useState(readStoredId)
  const { data, isLoading } = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => WorkspacesService.listWorkspaces(),
  })

  const workspaces = data ?? []
  // Derived rather than stored, so a renamed workspace shows its new name and
  // a deleted (or left) one falls back to the first remaining workspace.
  const currentWorkspace =
    workspaces.find((w) => w.id === selectedId) ?? workspaces[0] ?? null

  const setCurrentWorkspace = (workspace: WorkspacePublic) => {
    storeId(workspace.id)
    setSelectedId(workspace.id)
  }

  return (
    <WorkspaceContext.Provider
      value={{ workspaces, currentWorkspace, setCurrentWorkspace, isLoading }}
    >
      {children}
    </WorkspaceContext.Provider>
  )
}

export function useWorkspace(): WorkspaceContextValue {
  const context = useContext(WorkspaceContext)
  if (!context)
    throw new Error("useWorkspace must be used in WorkspaceProvider")
  return context
}

/**
 * The selected workspace, for pages inside the app layout (which only renders
 * them once the user has a workspace).
 */
export function useCurrentWorkspace(): WorkspacePublic {
  const { currentWorkspace } = useWorkspace()
  if (!currentWorkspace) throw new Error("No workspace selected")
  return currentWorkspace
}
