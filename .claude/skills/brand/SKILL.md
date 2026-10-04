---
name: brand
description: Apply Prism's visual identity (indigo + spectrum OKLCH tokens, validated chart palette, Manrope + Inter, ink sidebar). Use when styling new UI, choosing colors or chart colours, or reviewing visual changes.
---

# Visual identity

Authoritative source: `VISUAL_IDENTITY.md` at the repo root. This is the
short version.

## The feel

Clean, professional, confident — screens a community manager can paste into
a client report. Calm neutrals; the data and the spectrum provide the colour.

## Colour: tokens only

Tokens live in `frontend/src/index.css`, used through Tailwind classes. Never
hardcode hex or Tailwind palette classes in components.

| Token | Use |
|-------|-----|
| `primary` | Prism indigo: actions, links, focus |
| `bg-spectrum` / `text-spectrum` | Brand moments only: top band, primary buttons, avatar, sign-in rule. Never data, never large fills |
| `chart-1`…`chart-5` | Data, fixed order: views, reach, engagements, clicks, followers. Same hue for a metric everywhere (KPI `tone` = its trend line) |
| `success` / `warning` / `destructive` | Status, always with a word or icon |
| `sidebar-*` | Ink-indigo navigation, dark in both themes |
| `muted`, `border`, `card`, `background`, `accent` | Neutral chrome; `accent` is the pale-indigo hover |

Platform brand colours belong to `PlatformIcon` only. The chart palette is
validated (dataviz `validate_palette.js`, both modes) — re-run it before
changing a value; scatter-type charts stop at three series.

## Typography

- `font-display` — Manrope: `h1`–`h3` (automatic), KPI values.
- `font-sans` — Inter: everything else. Tables use tabular figures.
- Fonts are bundled from `@fontsource-variable/*`. Never add a font-CDN link.

## Layout

- Ink sidebar on desktop; on phones the main sections are `MobileTabBar`,
  which reads `navItems` from `AppSidebar` — add a section there, once.
- Sign-in panel: logo, tagline and `AuthPreview` on the ink background.

## Primitives

`frontend/src/components/ui/` is shadcn-generated: don't edit it. Style at
the call site.
