# Prism — Visual Identity

The graphical chart for the web app and the landing page. The tokens it
describes live in `frontend/src/index.css` (mirrored as CSS variables at the top
of `landing/index.html` and `landing/privacy.html`); this document says what
they are for.

## Who it is for, and how it should feel

Community managers, social media managers and agencies. They read their
numbers every day, and they put them in front of clients and bosses, so the
screens have to look as good as the work behind them.

**Clean · Professional · Confident · Luminous**

The name is the idea: one beam of light, split into colours. The interface is
quiet, cool neutrals and generous whitespace, so the data and the one
signature (the spectrum) can shine. Polished enough to screenshot into a
client report; never playful, never loud.

**Do**
- Keep the canvas calm: white cards on a near-white page, one accent colour
  (indigo) for actions.
- Let each metric keep its colour everywhere (KPI card, trend line).
- Prefer plain, precise wording: "Engagement rate", "Last 30 days".

**Don't**
- Don't use platform brand colours (Instagram pink, LinkedIn blue…) for
  anything but the platform's own icon.
- Don't use the spectrum gradient on data, or as large fills.
- Don't add new accent hues: a new metric takes the next chart slot.

## Colour

Tokens are in `frontend/src/index.css` (`:root` light, `.dark` dark),
exposed to Tailwind (`bg-primary`, `text-muted-foreground`…). Never hardcode
hex or Tailwind palette classes in components. Hex values below are
approximations for design tools.

### Brand

| Token | Light | Dark | Role |
|---|---|---|---|
| `--primary` | `oklch(0.51 0.22 277)` ≈ `#4F49DF` Prism indigo | `oklch(0.56 0.2 277)` ≈ `#5C5FE6` | Actions, links, focus, selection |
| `--spectrum` | indigo → violet → magenta → orange | same | The signature gradient (see below) |
| `--sidebar` | `oklch(0.235 0.06 277)` ≈ `#171A3A` ink indigo | `oklch(0.19 0.045 277)` ≈ `#0F1128` | The navigation frame, dark in both themes |

White on indigo is 6.1:1 in light mode and 4.8:1 in dark. Sidebar text on
the ink sidebar is 11:1.

### Spectrum

`--spectrum` is the light the prism splits: indigo `#4F49DF`, violet
`#8B46DF`, magenta `#D84497`, orange `#F27636`. Utilities: `bg-spectrum`,
`text-spectrum`. Its uses:

- the 4px band across the top of every page,
- primary buttons (an indigo→violet blend with an indigo glow),
- the workspace avatar,
- the short rule under the sign-in tagline.

It is a brand mark, never data, and never a large fill.

### Surfaces

| Token | Light | Dark |
|---|---|---|
| `--background` | `oklch(0.985 0.003 265)` ≈ `#F9FAFC` | `oklch(0.165 0.01 275)` ≈ `#0D0E13` |
| `--card` | white | `oklch(0.205 0.012 275)` ≈ `#15171D` |
| `--border` | `oklch(0.925 0.006 265)` | `oklch(1 0 0 / 9%)` |
| `--accent` | pale indigo tint, indigo text | deep indigo tint |

`bg-prism-glow` lays two soft radial lights (indigo and magenta) across the
top of each page.

### Data

The chart palette is categorical, in a **fixed order**, never cycled, with
the same hues in both modes:

| Slot | Light | Dark | Metric it belongs to |
|---|---|---|---|
| `--chart-1` | `#4F46E5` indigo | `#7471EC` | Views |
| `--chart-2` | `#E2602A` orange | `#E0662F` | Reach |
| `--chart-3` | `#0E966A` green | `#109476` | Engagements, engagement rate |
| `--chart-4` | `#C98500` amber | `#C58612` | Clicks |
| `--chart-5` | `#D6457F` pink | `#D4578A` | Followers, follower growth |

Validated with the dataviz palette validator against each mode's card
surface: all five pass adjacent-pair colour-blindness separation (worst ΔE
8.1 light) and 3:1 contrast; the first three also pass all-pairs, so
scatter-type charts stop at three series. Re-run the validator before
changing any value.

A metric keeps its slot everywhere: the KPI card's icon chip and 3px top rail
use the same colour as its trend line (`KpiCards.tsx`'s `tone`).

### Status

`--success` (active, top 5%), `--warning`, `--destructive` (expired, error,
bottom 5%). Always with a word or icon.

### Platform colours

Facebook, Instagram, X, LinkedIn, TikTok and Google Analytics keep their own
brand colours, in `PlatformIcon` only. In dark mode the tile gets a faint
ring so X's near-black stays visible.

## Typography

| Role | Family | Where |
|---|---|---|
| Display | **Manrope** (variable) | `h1`–`h3`, KPI values (`font-display text-3xl font-extrabold`) |
| Body / UI | **Inter** (variable), `cv11` | Everything else |

Headings track `-0.015em`. Every table uses tabular figures so numbers line
up. Fonts are bundled from `@fontsource-variable/*` and served from our own
domain: no Google Fonts and no third-party font CDN. The landing page
self-hosts the same files in `landing/fonts/`.

## Shape and depth

- **Radius** `0.625rem`; KPI icon chips `rounded-lg`.
- Cards are white with a hairline border; the primary button is the only
  element with a coloured shadow.
- The header is sticky and translucent (`bg-background/70 backdrop-blur`).

## Layout

- Ink-indigo sidebar: the logo, the workspace switcher (spectrum avatar),
  then the sections; the active item is a soft white highlight.
- The spectrum band, then a slim header, then the page: title, period
  ("Last 30 days · Acme Coffee"), a row of KPI cards, then charts and tables.
- Phones: the five main sections move to a tab bar along the bottom
  (`MobileTabBar`, sharing `navItems` with the sidebar); the active tab
  carries a short spectrum bar. Workspace, admin and settings stay in the
  sidebar sheet.
- Sign-in: an ink panel with soft coloured light falling across it, the logo,
  the tagline **"Every platform, one clear picture."**, and a glimpse of the
  dashboard: a frosted KPI card and a views-and-reach trend
  (`AuthPreview`).

## Logo

The prism mark (an indigo triangle splitting a grey beam into red, green and
blue rays) beside the "Prism" wordmark: `components/Common/Logo.tsx`, and
`docs/images/logo.svg` / `frontend/public/assets/images/prism-icon.svg` for
the README and favicon. On the ink sidebar and the sign-in panel the wordmark
is white. Don't recolour the rays or set the logo on the spectrum gradient.
