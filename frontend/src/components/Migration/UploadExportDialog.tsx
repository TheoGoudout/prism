import { CircleCheck, Upload } from "lucide-react"
import { useState } from "react"
import type { ExportFormat, UploadResult } from "@/client"
import { CancelButton } from "@/components/Common/CancelButton"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useMigrationAccounts, useUploadExport } from "@/hooks/useMigrations"
import { plural } from "@/lib/format"
import { platformLabel } from "@/lib/platforms"
import { EXPORT_FORMATS } from "./sources"

const DETECT = "detect"

/** Migrate from a CSV report exported from any supported tool. */
export function UploadExportDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const accounts = useMigrationAccounts(open)
  const upload = useUploadExport()
  const [accountId, setAccountId] = useState("")
  const [exportFormat, setExportFormat] = useState(DETECT)
  const [file, setFile] = useState<File | null>(null)

  const close = (next: boolean) => {
    onOpenChange(next)
    if (!next) {
      upload.reset()
      setFile(null)
    }
  }

  const submit = () => {
    if (!file || !accountId) return
    upload.mutate({
      accountId,
      file,
      format: exportFormat === DETECT ? null : (exportFormat as ExportFormat),
    })
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Upload an export</DialogTitle>
          <DialogDescription>
            Export a post or profile performance report as CSV from Hootsuite,
            Sprout Social, Buffer, Metricool, Later, Agorapulse or any other
            tool, and add it to one of your accounts.
          </DialogDescription>
        </DialogHeader>

        {upload.data ? (
          <>
            <UploadSummary result={upload.data} />
            <DialogFooter>
              <Button variant="outline" onClick={() => upload.reset()}>
                Upload another file
              </Button>
              <Button onClick={() => close(false)}>Done</Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label>Account</Label>
                <Select value={accountId} onValueChange={setAccountId}>
                  <SelectTrigger className="w-full" aria-label="Account">
                    <SelectValue placeholder="Choose an account" />
                  </SelectTrigger>
                  <SelectContent>
                    {(accounts.data ?? []).map((account) => (
                      <SelectItem key={account.id} value={account.id}>
                        {platformLabel(account.platform)} · {account.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {accounts.data?.length === 0 && (
                  <p className="text-sm text-muted-foreground">
                    Connect the account in Prism first: history is added to
                    accounts that have synced at least once.
                  </p>
                )}
              </div>
              <div className="flex flex-col gap-2">
                <Label>Exported from</Label>
                <Select value={exportFormat} onValueChange={setExportFormat}>
                  <SelectTrigger className="w-full" aria-label="Exported from">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={DETECT}>Detect automatically</SelectItem>
                    {Object.entries(EXPORT_FORMATS).map(([value, label]) => (
                      <SelectItem key={value} value={value}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="export-file">CSV file</Label>
                <Input
                  id="export-file"
                  type="file"
                  accept=".csv,.tsv,.txt,text/csv"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
                <p className="text-xs text-muted-foreground">
                  Up to 10 MB. Uploading the same file again updates the data
                  rather than duplicating it.
                </p>
              </div>
            </div>
            <DialogFooter>
              <CancelButton />
              <LoadingButton
                icon={Upload}
                loading={upload.isPending}
                disabled={!file || !accountId}
                onClick={submit}
              >
                Upload
              </LoadingButton>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

function UploadSummary({ result }: { result: UploadResult }) {
  const what = result.kind === "posts" ? "posts" : "days of metrics"
  return (
    <div className="flex flex-col gap-3 text-sm">
      <p className="flex items-center gap-2 font-medium">
        <CircleCheck className="size-4 text-success" />
        {result.created} new and {result.updated} updated {what} from{" "}
        {EXPORT_FORMATS[result.format]}
      </p>
      {result.date_from && result.date_to && (
        <p className="text-muted-foreground">
          From {result.date_from} to {result.date_to}.
        </p>
      )}
      {result.skipped_other_networks > 0 && (
        <p className="text-muted-foreground">
          {plural(result.skipped_other_networks, "row")} for other networks{" "}
          {result.skipped_other_networks === 1 ? "was" : "were"} skipped.
        </p>
      )}
      {result.rejected > 0 && (
        <div className="rounded-md border border-warning/40 bg-warning/10 p-3 text-warning-foreground dark:text-warning">
          <p>{plural(result.rejected, "row")} couldn't be read:</p>
          <ul className="mt-1 list-disc pl-5">
            {result.errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
