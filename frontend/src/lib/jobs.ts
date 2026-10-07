/** Background jobs (analyses, migrations) and how the UI follows them. */

type JobStatus = "pending" | "running" | "completed" | "failed"

/** How often a job still running is polled. */
const POLL_MS = 4000

export const isUnfinished = (status: JobStatus) =>
  status === "pending" || status === "running"

/** A `refetchInterval` polling while any of the jobs is unfinished. */
export const pollWhileUnfinished =
  <T>(statuses: (data: T) => JobStatus[]) =>
  (query: { state: { data?: T } }) =>
    query.state.data !== undefined &&
    statuses(query.state.data).some(isUnfinished)
      ? POLL_MS
      : false
