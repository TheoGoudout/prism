import type { ConnectionGuide } from "@/components/Integrations/guideContent"

/**
 * Step-by-step "how to migrate" guides shown on the Integrations page, in
 * the same plain style as the connection guides. The tools' own screens
 * change often: re-check the menu names against them when updating these.
 * Sources: Sprout's API docs (https://api.sproutsocial.com/docs/, "Accessing
 * the APIs") and Metricool's API guide (help.metricool.com).
 */

export type MigrationGuideKey = "sprout_social" | "metricool" | "csv"

export const MIGRATION_GUIDES_REVIEWED_ON = "October 2026"

export const SPROUT_APP_URL = "https://app.sproutsocial.com"
export const SPROUT_API_DOCS_URL = "https://api.sproutsocial.com/docs/"
export const METRICOOL_APP_URL = "https://app.metricool.com"
export const METRICOOL_API_GUIDE_URL =
  "https://help.metricool.com/basic-guide-for-api-integration-r97af"

const matchAndMigrateStep = (tool: string) => ({
  title: "Match each profile to a Prism account",
  body: (
    <>
      Prism lists your {tool} profiles and picks the Prism account each one most
      likely is. Check each choice, set the ones you don't want to{" "}
      <strong>Don't migrate</strong>, choose how many years of history to bring
      over, then click <strong>Migrate</strong>.
    </>
  ),
})

const followProgressStep = (tool: string) => ({
  title: "Follow the migration",
  body: (
    <>
      The migration runs in the background: you can leave the page. Its progress
      shows in the <strong>Migrations</strong> section of this page, with the
      number of posts and days of metrics brought over for each profile. Prism
      deletes its copy of your {tool} credentials when the migration finishes.
    </>
  ),
})

const commonTroubleshooting = (tool: string) => [
  <>
    <strong>A profile has no Prism account to choose</strong>: connect that
    account in Prism first (<strong>Connect platform</strong>) and wait for its
    first sync, then start again.
  </>,
  <>
    <strong>"Some parts couldn't be fetched"</strong>: {tool} didn't answer for
    part of the period. Run the migration again later: what was already migrated
    is updated, never duplicated.
  </>,
  <>
    Migrated data only fills gaps: it never replaces the numbers Prism synced
    itself.
  </>,
]

export const MIGRATION_GUIDES: Record<MigrationGuideKey, ConnectionGuide> = {
  sprout_social: {
    summary:
      "Bring over your posts and daily profile metrics from Sprout Social, for Facebook, Instagram, LinkedIn, TikTok and X. You give Prism an API token; it takes about 3 minutes.",
    beforeYouStart: [
      <>
        A Sprout Social plan that includes <strong>API access</strong>. If
        you're not sure, ask your Sprout sales representative or support.
      </>,
      <>
        The <strong>API Permissions</strong> permission in Sprout. A Sprout
        admin can give it to you.
      </>,
      <>
        The accounts you want to migrate already connected in Prism (they are
        listed above under <strong>Connected accounts</strong>).
      </>,
    ],
    steps: [
      {
        title: "Open Sprout's API settings",
        body: (
          <>
            Log in to{" "}
            <a
              href={SPROUT_APP_URL}
              target="_blank"
              rel="noreferrer"
              className="text-primary underline-offset-4 hover:underline"
            >
              Sprout Social
            </a>
            , then go to <strong>Settings</strong> →{" "}
            <strong>Global Features</strong> → <strong>API</strong>.
          </>
        ),
      },
      {
        title: "Accept the API terms (first time only)",
        body: (
          <>
            If Sprout asks you to, accept the{" "}
            <strong>Analytics API Terms of Service</strong> at the top of the
            API page. To migrate X (Twitter) profiles, also accept the{" "}
            <strong>X Content End User License Agreement</strong> shown there.
          </>
        ),
      },
      {
        title: "Create a token",
        body: (
          <>
            In <strong>API Token Management</strong>, click{" "}
            <strong>Generate API Token</strong>, name it "Prism", and copy the
            token. Sprout only shows it once.
          </>
        ),
      },
      {
        title: "Paste it in Prism",
        body: (
          <>
            On this page, click <strong>Migrate from…</strong> →{" "}
            <strong>Sprout Social</strong>, paste the token, then click{" "}
            <strong>Find profiles</strong>.
          </>
        ),
      },
      matchAndMigrateStep("Sprout Social"),
      followProgressStep("Sprout Social"),
    ],
    troubleshooting: [
      <>
        <strong>"The credentials were rejected"</strong>: check that you copied
        the whole token, that it hasn't been invalidated in Sprout, and that
        your plan includes API access.
      </>,
      <>
        <strong>X profiles bring nothing over</strong>: accept the X Content End
        User License Agreement on Sprout's API page, then migrate again.
      </>,
      ...commonTroubleshooting("Sprout Social"),
    ],
    helpLink: {
      label: "Sprout Social's API documentation",
      href: SPROUT_API_DOCS_URL,
    },
  },

  metricool: {
    summary:
      "Bring over your posts and daily metrics from every brand in Metricool, for Facebook, Instagram, LinkedIn, TikTok and X. You give Prism your API token and user ID; it takes about 2 minutes.",
    beforeYouStart: [
      <>
        A Metricool <strong>Advanced</strong> or <strong>Custom</strong> plan:
        the Free and Starter plans don't include API access.
      </>,
      <>
        The accounts you want to migrate already connected in Prism (they are
        listed above under <strong>Connected accounts</strong>).
      </>,
    ],
    steps: [
      {
        title: "Copy your API token",
        body: (
          <>
            Log in to{" "}
            <a
              href={METRICOOL_APP_URL}
              target="_blank"
              rel="noreferrer"
              className="text-primary underline-offset-4 hover:underline"
            >
              Metricool
            </a>
            , open <strong>Account settings</strong> → <strong>API</strong>, and
            copy your API access token.
          </>
        ),
      },
      {
        title: "Find your user ID",
        body: (
          <>
            Open any of your brands in Metricool and look at the address bar: it
            ends like <code>?blogId=12345&amp;userId=6789</code>. The number
            after <code>userId=</code> is your user ID.
          </>
        ),
      },
      {
        title: "Paste them in Prism",
        body: (
          <>
            On this page, click <strong>Migrate from…</strong> →{" "}
            <strong>Metricool</strong>, paste the token and your user ID, then
            click <strong>Find profiles</strong>. Leave{" "}
            <strong>Brand ID</strong> empty: Prism finds all your brands without
            it.
          </>
        ),
      },
      matchAndMigrateStep("Metricool"),
      followProgressStep("Metricool"),
    ],
    troubleshooting: [
      <>
        <strong>"The credentials were rejected"</strong>: check the token and
        user ID, and that your plan is Advanced or Custom. If you created a new
        token in Metricool, the old one stops working.
      </>,
      <>
        <strong>Instagram follower totals are missing</strong>: Metricool's API
        only gives followers gained and lost per day for Instagram. Prism
        records the total itself from now on.
      </>,
      ...commonTroubleshooting("Metricool"),
    ],
    helpLink: {
      label: "Metricool's API guide",
      href: METRICOOL_API_GUIDE_URL,
    },
  },

  csv: {
    summary:
      "From Hootsuite, Buffer, Later, Agorapulse or any other tool: export a report as a CSV file and upload it. Prism recognises each tool's columns. No token needed.",
    beforeYouStart: [
      <>
        The account the report is about already connected in Prism (listed above
        under <strong>Connected accounts</strong>).
      </>,
      <>
        A report you can export as <strong>CSV</strong>. A PDF won't work; an
        Excel file can be opened in Excel or Google Sheets and saved as CSV.
      </>,
    ],
    steps: [
      {
        title: "Export a report from your tool",
        body: (
          <>
            In your tool's analytics or reports section, open a report for{" "}
            <strong>one profile</strong>: a <strong>post</strong> report (one
            row per post) or a <strong>profile</strong> report (one row per
            day). Pick the period you want, then export or download it as CSV.
          </>
        ),
      },
      {
        title: "Upload it in Prism",
        body: (
          <>
            On this page, click <strong>Migrate from…</strong> →{" "}
            <strong>Upload an export (CSV)</strong>. Choose the Prism account it
            belongs to, leave <strong>Detect automatically</strong>, choose the
            file, and click <strong>Upload</strong>.
          </>
        ),
      },
      {
        title: "Check the summary",
        body: (
          <>
            Prism shows how many posts or days it added, and lists any rows it
            couldn't read. Uploading the same file again is safe: it updates the
            data rather than duplicating it.
          </>
        ),
      },
      {
        title: "Repeat for each profile",
        body: (
          <>
            Upload a post report and a profile report for each account you want
            to migrate.
          </>
        ),
      },
    ],
    troubleshooting: [
      <>
        <strong>"No header row … was found"</strong>: the file must be the
        report's data with its column names (Date, Impressions, Likes…), not a
        summary. Export it again as CSV.
      </>,
      <>
        <strong>"The file covers several profiles"</strong>: filter the report
        on one profile before exporting.
      </>,
      <>
        <strong>Days and months are swapped</strong> (e.g. March 4 read as April
        3): choose your tool under <strong>Exported from</strong> instead of
        Detect automatically, and upload again.
      </>,
      <>
        <strong>Rows for other networks were skipped</strong>: the report
        covered several networks; only the chosen account's network is kept.
      </>,
    ],
  },
}
