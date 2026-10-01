import { useQuery } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { createContext, useContext, useEffect, useState } from "react"
import type { WorkspacePublic } from "@/client"
import { WorkspacesService } from "@/client"

const STORAGE_KEY = "prism:workspace_id"

interface WorkspaceContextValue {
  workspaces: WorkspacePublic[]
  currentWorkspace: WorkspacePublic | null
  setCurrentWorkspace: (ws: WorkspacePublic) => void
  isLoading: boolean
}

const WorkspaceContext = createContext<WorkspaceContextValue>({
  workspaces: [],
  currentWorkspace: null,
  setCurrentWorkspace: () => {},
  isLoading: false,
})

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [currentWorkspace, setCurrentWorkspaceState] =
    useState<WorkspacePublic | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => WorkspacesService.listWorkspaces({}),
  })

  const workspaces = data?.data ?? []

  // Restore from localStorage or fall back to first workspace. Re-runs when
  // the list changes, so a renamed workspace is refreshed and a deleted (or
  // left) one is replaced.
  useEffect(() => {
    if (workspaces.length === 0) {
      setCurrentWorkspaceState(null)
      return
    }
    const saved = localStorage.getItem(STORAGE_KEY)
    const match = saved ? workspaces.find((w) => w.id === saved) : null
    setCurrentWorkspaceState(match ?? workspaces[0])
  }, [workspaces])

  const setCurrentWorkspace = (ws: WorkspacePublic) => {
    localStorage.setItem(STORAGE_KEY, ws.id)
    setCurrentWorkspaceState(ws)
  }

  return (
    <WorkspaceContext.Provider
      value={{ workspaces, currentWorkspace, setCurrentWorkspace, isLoading }}
    >
      {children}
    </WorkspaceContext.Provider>
  )
}

export function useWorkspace() {
  return useContext(WorkspaceContext)
}
