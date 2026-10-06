import { ArrowRightLeft, FileUp, Route } from "lucide-react"

import type { MigrationSource } from "@/client"
import { GuideBody } from "@/components/Integrations/GuideBody"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  MIGRATION_GUIDES,
  MIGRATION_GUIDES_REVIEWED_ON,
  type MigrationGuideKey,
} from "./guideContent"
import type { MigrateActions } from "./MigrateDialogs"
import { SOURCES } from "./sources"

const TABS: {
  key: MigrationGuideKey
  label: string
  // Migrated through its API; the others are uploaded as CSV
  source?: MigrationSource
}[] = [
  {
    key: "sprout_social",
    label: SOURCES.sprout_social.label,
    source: "sprout_social",
  },
  { key: "metricool", label: SOURCES.metricool.label, source: "metricool" },
  { key: "csv", label: "Other tools (CSV)" },
]

/** One step-by-step guide per way of migrating from another tool, as tabs. */
export function MigrationGuides({
  editable,
  openSource,
  openUpload,
}: MigrateActions & { editable: boolean }) {
  return (
    <Card data-migration-guides>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Route className="size-4" />
          How to migrate from another tool
        </CardTitle>
        <CardDescription>
          Bring the history you have in another social media tool into Prism.
          Guides last checked: {MIGRATION_GUIDES_REVIEWED_ON}.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue={TABS[0].key}>
          <TabsList className="h-auto w-full flex-wrap justify-start">
            {TABS.map((tab) => (
              <TabsTrigger
                key={tab.key}
                value={tab.key}
                className="flex-none px-3 py-1.5"
              >
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>
          {TABS.map((tab) => (
            <TabsContent key={tab.key} value={tab.key} className="pt-4">
              <GuideBody
                guide={MIGRATION_GUIDES[tab.key]}
                action={
                  !editable ? (
                    <p className="text-sm text-muted-foreground">
                      Only workspace owners and admins can migrate data. Send
                      this guide to one of them.
                    </p>
                  ) : tab.source ? (
                    <Button
                      onClick={() => tab.source && openSource(tab.source)}
                    >
                      <ArrowRightLeft className="size-4" />
                      Migrate from {tab.label} now
                    </Button>
                  ) : (
                    <Button onClick={openUpload}>
                      <FileUp className="size-4" />
                      Upload an export now
                    </Button>
                  )
                }
              />
            </TabsContent>
          ))}
        </Tabs>
      </CardContent>
    </Card>
  )
}
