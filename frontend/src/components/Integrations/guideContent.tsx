import type { ReactNode } from "react"

import type { Platform } from "@/client"

/**
 * Step-by-step "how to connect" guides shown on the Integrations page.
 *
 * Written for people who are not technical: plain words, one action per
 * step. The platforms' own screens change often, so re-check every guide
 * against the live flow when bumping GUIDES_REVIEWED_ON. Screenshots are
 * regenerated with `bun run tutorial-screenshots` (Prism's own screens) and
 * `bun run tutorial-screenshots:platforms` (the platforms' screens; see
 * scripts/platform-screenshots.ts). A step whose image hasn't been captured
 * yet shows its text only.
 */

export const GUIDES_REVIEWED_ON = "October 2026"

const SCREENSHOTS = "/assets/images/tutorials"

export interface GuideStep {
  title: string
  body: ReactNode
  image?: { src: string; alt: string }
}

export interface ConnectionGuide {
  /** Short description of what gets connected. */
  summary: string
  /** What the person needs before they start. */
  beforeYouStart: ReactNode[]
  steps: GuideStep[]
  /** "Something went wrong" tips. */
  troubleshooting: ReactNode[]
  /** The platform's own help page for the prerequisites. */
  helpLink: { label: string; href: string }
}

/** A screenshot of a platform's own screen. */
function shot(file: string, alt: string): GuideStep["image"] {
  return { src: `${SCREENSHOTS}/${file}`, alt }
}

// Steps every guide starts and ends with: they happen in Prism itself.

function openMenuStep(platform: Platform, label: string): GuideStep {
  return {
    title: `Choose ${label} in Prism`,
    body: (
      <>
        On this page, click the <strong>Connect platform</strong> button (top
        right), then click <strong>{label}</strong> in the list. A new page from{" "}
        {label} opens in the same tab.
      </>
    ),
    image: {
      src: `${SCREENSHOTS}/${platform}-menu.png`,
      alt: `The "Connect platform" menu open, with ${label} highlighted`,
    },
  }
}

function doneStep(platform: Platform, label: string): GuideStep {
  return {
    title: "You're done!",
    body: (
      <>
        You are brought back to this page with a green{" "}
        <strong>Platform connected</strong> message. {label} now shows in{" "}
        <strong>Connected accounts</strong> with the status{" "}
        <strong>active</strong>. Your first numbers usually appear within a few
        minutes, and they are refreshed automatically every night.
      </>
    ),
    image: {
      src: `${SCREENSHOTS}/${platform}-connected.png`,
      alt: `${label} listed in Connected accounts with the status "active"`,
    },
  }
}

const RECONNECT_TIP = (
  <>
    If the status later shows <strong>expired</strong>, click{" "}
    <strong>Reconnect</strong> next to it and follow this guide again. Your data
    is kept.
  </>
)

export const CONNECTION_GUIDES: Record<Platform, ConnectionGuide> = {
  facebook: {
    summary:
      "Connect the Facebook Pages of your brand (not personal profiles).",
    beforeYouStart: [
      <>
        A Facebook account that has <strong>full control</strong> (admin access)
        of the Page you want to follow.
      </>,
      <>About 2 minutes.</>,
    ],
    steps: [
      openMenuStep("facebook", "Facebook"),
      {
        title: "Log in to Facebook",
        body: (
          <>
            If Facebook asks you to log in, use the account that manages your
            Page. If you are already logged in, Facebook shows{" "}
            <strong>Continue as [your name]</strong>: check that it is the right
            person, then click it.
          </>
        ),
        image: shot(
          "facebook-continue.png",
          "Facebook asking to continue as the logged-in person",
        ),
      },
      {
        title: "Choose your Pages",
        body: (
          <>
            Facebook asks which Pages Prism may see. Pick{" "}
            <strong>Opt in to current Pages only</strong> and tick the Pages you
            want, or pick{" "}
            <strong>Opt in to all current and future Pages</strong>. Then click{" "}
            <strong>Continue</strong>. If you only see an{" "}
            <strong>Edit access</strong> (or{" "}
            <strong>Edit previous settings</strong>) link, click it to get to
            this list.
          </>
        ),
        image: shot(
          "facebook-pages.png",
          "Facebook's list of Pages to share with Prism",
        ),
      },
      {
        title: "Allow access",
        body: (
          <>
            Facebook lists what Prism will be able to do (read your Pages' posts
            and statistics). Leave every switch <strong>on</strong> and click{" "}
            <strong>Save</strong>, then <strong>Got it</strong>. Prism can never
            post or change anything on your Page.
          </>
        ),
        image: shot(
          "facebook-permissions.png",
          "Facebook's summary of what Prism will be able to do",
        ),
      },
      doneStep("facebook", "Facebook"),
    ],
    troubleshooting: [
      <>
        <strong>A Page is missing?</strong> On Facebook, open{" "}
        <strong>
          Settings &amp; privacy → Settings → Business integrations
        </strong>
        , remove Prism, then connect again and tick that Page. Also check that
        you have full control of the Page.
      </>,
      RECONNECT_TIP,
    ],
    helpLink: {
      label: "Facebook Help: Page access",
      href: "https://www.facebook.com/help/187316341316631",
    },
  },

  instagram: {
    summary:
      "Connect an Instagram business or creator account. This goes through Facebook.",
    beforeYouStart: [
      <>
        Your Instagram account must be a <strong>professional</strong> account
        (Business or Creator). In the Instagram app: open your profile, tap the
        menu <strong>☰</strong>, then{" "}
        <strong>Account type and tools → Switch to professional account</strong>
        .
      </>,
      <>
        It must be <strong>linked to a Facebook Page</strong>. In the Instagram
        app: <strong>Edit profile → Page → Connect or create</strong>, then pick
        your Page.
      </>,
      <>
        The <strong>Facebook</strong> login of someone with full control of that
        Page. (You will log in with Facebook, not with Instagram.)
      </>,
    ],
    steps: [
      openMenuStep("instagram", "Instagram"),
      {
        title: "Log in with Facebook",
        body: (
          <>
            A <strong>Facebook</strong> page opens. This is normal: Instagram
            statistics are shared through Facebook. Log in, or click{" "}
            <strong>Continue as [your name]</strong> if you are already logged
            in.
          </>
        ),
        image: shot(
          "instagram-continue.png",
          "Facebook asking to continue as the logged-in person",
        ),
      },
      {
        title: "Choose your Instagram account",
        body: (
          <>
            Tick the Instagram account you want to follow and click{" "}
            <strong>Continue</strong>.
          </>
        ),
        image: shot(
          "instagram-accounts.png",
          "Facebook's list of Instagram accounts to share with Prism",
        ),
      },
      {
        title: "Choose the Facebook Page linked to it",
        body: (
          <>
            Tick the Facebook Page your Instagram account is linked to (this is
            required, even if you don't want Facebook statistics) and click{" "}
            <strong>Continue</strong>.
          </>
        ),
        image: shot(
          "instagram-pages.png",
          "Facebook's list of Pages to share with Prism",
        ),
      },
      {
        title: "Allow access",
        body: (
          <>
            Leave every switch <strong>on</strong>, click <strong>Save</strong>,
            then <strong>Got it</strong>. Prism can only read statistics; it
            never posts anything.
          </>
        ),
        image: shot(
          "instagram-permissions.png",
          "Facebook's summary of what Prism will be able to do",
        ),
      },
      doneStep("instagram", "Instagram"),
    ],
    troubleshooting: [
      <>
        <strong>"We couldn't connect to the platform"?</strong> This usually
        means Prism found no professional Instagram account linked to the Pages
        you ticked. Check the two points in "Before you start", then try again
        and make sure you tick both the Instagram account and its Page.
      </>,
      <>
        <strong>Your account isn't in the list?</strong> On Facebook, open{" "}
        <strong>
          Settings &amp; privacy → Settings → Business integrations
        </strong>
        , remove Prism, then connect again.
      </>,
      RECONNECT_TIP,
    ],
    helpLink: {
      label: "Instagram Help: set up a professional account",
      href: "https://help.instagram.com/502981923235522",
    },
  },

  twitter: {
    summary: "Connect an X (formerly Twitter) account.",
    beforeYouStart: [
      <>The username and password of the X account you want to follow.</>,
      <>
        Tip: if you use several X accounts, log in to x.com with the right one{" "}
        <strong>before</strong> you start. X connects the account you are
        currently logged in with.
      </>,
    ],
    steps: [
      openMenuStep("twitter", "Twitter / X"),
      {
        title: "Log in to X",
        body: (
          <>
            If X asks you to log in, do so. If you end up on your X home feed
            instead of an authorization page, come back to Prism and repeat step
            1: now that you're logged in, it will work.
          </>
        ),
      },
      {
        title: "Click “Authorize app”",
        body: (
          <>
            X shows the app name and what it may do (read your posts and
            profile). Check the account shown at the top, then click{" "}
            <strong>Authorize app</strong>. Prism cannot post on your behalf.
          </>
        ),
        image: shot(
          "twitter-authorize.png",
          "X's authorization page with the Authorize app button",
        ),
      },
      doneStep("twitter", "Twitter / X"),
    ],
    troubleshooting: [
      <>
        <strong>The wrong account got connected?</strong> Click the bin icon
        next to it to disconnect it, switch account on x.com, then connect
        again.
      </>,
      RECONNECT_TIP,
    ],
    helpLink: {
      label: "X Help: connected apps",
      href: "https://help.x.com/en/managing-your-account/connect-or-revoke-access-to-third-party-apps",
    },
  },

  linkedin: {
    summary:
      "Connect the LinkedIn Pages of your company (not your personal profile).",
    beforeYouStart: [
      <>
        You must be a <strong>Super admin</strong> of the company's LinkedIn
        Page. To check: open the Page, click{" "}
        <strong>Admin tools → Manage admins</strong>. Ask an existing Super
        admin to give you the role if needed.
      </>,
      <>Your LinkedIn email and password.</>,
    ],
    steps: [
      openMenuStep("linkedin", "LinkedIn"),
      {
        title: "Sign in to LinkedIn",
        body: (
          <>
            If LinkedIn asks you to sign in, use your own LinkedIn account (the
            one that is a Super admin of the Page).
          </>
        ),
      },
      {
        title: "Click “Allow”",
        body: (
          <>
            LinkedIn lists what Prism may access (your basic profile and your
            Pages' posts and statistics). Click <strong>Allow</strong>.
          </>
        ),
        image: shot(
          "linkedin-allow.png",
          "LinkedIn's authorization page with the Allow button",
        ),
      },
      doneStep("linkedin", "LinkedIn"),
    ],
    troubleshooting: [
      <>
        <strong>No numbers for your Page?</strong> Prism only reads Pages where
        you are a <strong>Super admin</strong>. Content admins and analysts are
        not enough. Get the role, then click the sync icon (two arrows) next to
        LinkedIn.
      </>,
      RECONNECT_TIP,
    ],
    helpLink: {
      label: "LinkedIn Help: Page admin roles",
      href: "https://www.linkedin.com/help/linkedin/answer/a541981",
    },
  },

  tiktok: {
    summary: "Connect a TikTok account and the statistics of its videos.",
    beforeYouStart: [
      <>
        Access to the TikTok account you post with: its login, or the TikTok app
        on a phone where you are logged in (to scan a QR code).
      </>,
    ],
    steps: [
      openMenuStep("tiktok", "TikTok"),
      {
        title: "Log in to TikTok",
        body: (
          <>
            Choose how to log in. The easiest is <strong>Use QR code</strong>:
            in the TikTok app on your phone, tap the scan icon and point your
            camera at the code on screen. You can also log in with your phone
            number, email or username.
          </>
        ),
      },
      {
        title: "Allow access",
        body: (
          <>
            TikTok lists what Prism would like to see (your profile, your videos
            and their statistics). Leave every option <strong>on</strong>: if
            you turn one off, some numbers will be missing. Then click{" "}
            <strong>Continue</strong> (some versions say{" "}
            <strong>Authorize</strong>).
          </>
        ),
        image: shot(
          "tiktok-authorize.png",
          "TikTok's list of what Prism would like to access",
        ),
      },
      doneStep("tiktok", "TikTok"),
    ],
    troubleshooting: [
      <>
        <strong>Some numbers are missing?</strong> You may have turned off a
        permission. Disconnect TikTok with the bin icon and connect again,
        leaving every option on.
      </>,
      RECONNECT_TIP,
    ],
    helpLink: {
      label: "TikTok Help: manage app permissions",
      href: "https://support.tiktok.com/en/account-and-privacy/account-privacy-settings/third-party-apps-and-services",
    },
  },

  google_analytics: {
    summary: "Connect your website's visitor statistics from Google Analytics.",
    beforeYouStart: [
      <>
        A Google account that can see your Google Analytics property (at least
        the <strong>Viewer</strong> role). To check: open analytics.google.com,
        click <strong>Admin</strong> (gear icon, bottom left), then{" "}
        <strong>Property access management</strong>.
      </>,
      <>Prism reads Google Analytics 4 properties.</>,
    ],
    steps: [
      openMenuStep("google_analytics", "Google Analytics"),
      {
        title: "Choose your Google account",
        body: (
          <>
            Google asks you to choose an account. Click the one that has access
            to your Google Analytics (it may be a work account).
          </>
        ),
        image: shot("google_analytics-account.png", "Google's account chooser"),
      },
      {
        title: "Tick the box and continue",
        body: (
          <>
            Google lists what Prism would like to do:{" "}
            <strong>See and download your Google Analytics data</strong>. If
            there is a checkbox next to it, <strong>tick it</strong> (or tick{" "}
            <strong>Select all</strong>); otherwise Prism gets no data. Then
            click <strong>Continue</strong>.
          </>
        ),
        image: shot(
          "google_analytics-consent.png",
          "Google's permission page with the Google Analytics checkbox",
        ),
      },
      doneStep("google_analytics", "Google Analytics"),
    ],
    troubleshooting: [
      <>
        <strong>"Google hasn't verified this app"?</strong> Don't click through.
        Contact the person who set up Prism for your team.
      </>,
      <>
        <strong>No data appears?</strong> You probably left the checkbox
        unticked. Disconnect Google Analytics with the bin icon and connect
        again, ticking the box.
      </>,
      RECONNECT_TIP,
    ],
    helpLink: {
      label: "Google Analytics Help: access and permissions",
      href: "https://support.google.com/analytics/answer/9305788",
    },
  },
}
