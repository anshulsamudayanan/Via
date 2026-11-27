# VIA design system: Liquid Glass

Status: **implemented** (tokens in `packages/ui/src/styles.css`, primitives and motion tokens in
`packages/ui`). The current direction is **Liquid Glass**: the Black Glass base below, plus a
liquid-glass material, the Array display face, an editorial landing page and a denser, reference-led
dashboard. Older sections further down (exact hex values, 2–6 px radii, IBM Plex Sans) are historical
and superseded where they disagree.

## Liquid Glass (current)

**Direction.** Deterministic design review for KiCad boards: exact, instrument-like, unhurried. The
world is the bench at night: copper, soldermask and silkscreen on a dark canvas. The chrome stays quiet
(neutral glass, one purple accent); colour and detail go into the moments: the board renders and the
findings chart. The signature is the measurement mark, a dimension line with the measured gap in mono
(`0.118 mm`), used where a finding sits on copper.

**Material** (`<LiquidGlass variant>` in `@via/ui`, CSS `.glass-thin | -regular | -thick | -overlay`):
blur 16 / 22 / 28px + `saturate(180%) brightness(1.1)`, a 1px specular gradient rim (`::before`,
masked to the edge, white 25% top-left fading to 5%), an inner top highlight, an inner bottom shadow,
a soft outer shadow and an optional cursor sheen (not used on cards). `thick` (sidebar, navbar, mobile
top bar) also refracts its edges through an SVG `feTurbulence` + `feDisplacementMap` filter
(`#via-refraction`, defined once in the app providers). Refraction is opted in only on Chromium
(`html[data-refraction]`), because one unsupported `url()` would void the whole `backdrop-filter`
elsewhere. `overlay` is the dense variant for menus, dialogs, the ⌘K sheet and toasts. Stat and chart
cards keep the rim and fill but drop their own blur (`backdrop-blur-none`) to stay inside the blur budget.

**Ambient light.** Two static, near-neutral radial fields (`--via-ambient-1/2`) and film grain behind
everything. No colour washes, no drift, no scroll parallax.

**No glow.** Nothing carries a coloured shadow or halo: not buttons, not the active nav item, not chart
marks. Depth comes from glass steps, hairlines and the top highlight.

**Type.** Array (Indian Type Foundry, ITF Free Font License) for H1/H2, section titles, big stat
numbers and the wordmark. Headlines and figures use weight 400; 600 only for the wordmark. It is a wide
dot-matrix display face: tracking −0.02em at most (tighter makes the dots touch). Headlines are sentence
case without a trailing period and never colour individual words. The licence allows self-hosting but
not redistribution through a public repository, so the files are **never committed**:
`scripts/fetch-fonts.mjs` downloads the official files (pinned SHA-256) into the git-ignored
`apps/web/public/fonts/array/`, and the web image build runs it. Without them the display stack falls
back to SF Pro / Inter. Body: SF Pro (system) then Inter. Mono (IBM Plex Mono) for engineering values,
counts and meta. Labels are sentence case at normal tracking: no uppercase tracked eyebrows.

**Buttons.** One primary action per view: `Button variant="primary"`, a solid accent pill with a
hairline and a top highlight (`shadow-primary`). Secondary actions are `secondary` (tinted fill,
hairline) or `ghost` (text). The landing header has one button (Create account) with Sign in as a
ghost link.

**Board materials.** `--via-copper`, `--via-pad` (ENIG), `--via-mask`, `--via-mask-deep` and
`--via-silk` colour board renders only (landing illustrations, the dashboard's latest board, the
first-run board), never chrome.

**Charts.** The dashboard's findings chart follows the dataviz method: findings per day are discrete
events, so they are stacked bars (a line would invent slopes across empty days). Severity is ordered,
so the bars use a one-hue ramp (`--via-sev-1..4`; dark `#8f3a34 #c9483e #ff6b5e #ffb0a8`, light
`#e88d84 #d9594d #b8352b #7f1c15`), most severe at the base, validated as an ordinal ramp in both
themes; a legend, a hover/keyboard tooltip and a table view. No glow, no looping motion.

**Motion.** One short fade and 8px rise for the main content on load (`enter`, no blur). Hover is a
colour or surface step, press a 0.97 scale. No looping animation on things that are not live, no
parallax, no cursor tilt on content cards, no autoplaying carousels.

**Third-party code.** Third-party components are vendored verbatim under `apps/web/components/`
with marked "VIA EDIT" blocks only. The Originkit Light Glass Button and Liquid Grid were removed in the
unslop pass (purple cursor light and glowing grid); none are vendored at the moment.

## Black Glass

**Base and light.** Near-black base (`#030305`; light theme `#F2F2F7`). One fixed `Ambient` layer
behind every page: three radial colour fields (muted violet from the accent, indigo, a hint of blue)
that drift slowly (60–90 s loops) with gentle scroll parallax, plus film grain from an inline SVG.
Radial gradients, not filter blur, so it costs almost nothing to composite.

**Glass recipe** (`.glass-thin` / `.glass-regular` / `.glass-thick`, or `<Glass variant sheen>`):
translucent fill (white 4% / 6%; thick is a denser 72% dark tint for overlays), `backdrop-filter:
blur(20 / 28 / 40px) saturate(180%)`, a 1px hairline (white 10%), a top inner highlight
(`inset 0 1px 0 rgb(255 255 255 / .08)`) and a soft deep shadow. `sheen` adds a cursor-following
specular highlight on hover-capable devices. Without `backdrop-filter` support glass falls back to a
solid fill. The glass classes live in `@layer components` so utilities can override them.

**Blur budget.** At most about four blurred layers on screen. Rows, list items, chips and secondary
buttons inside a glass panel use tinted fills (`bg-surface`, hairline, top highlight), never their own
blur. Nested `backdrop-filter` can't see siblings under it, so overlays inside glass (the hero's DRC
callouts) use a dense fill instead.

**Text.** White with 62% (`muted`) and 54% (`subtle`) tiers; light theme 64% / 58%. These are the
brief's 60 / 40 tiers nudged so small text stays above 4.5:1 on glass, measured including the violet
light under it (dark: muted 5.9, subtle 4.9; light: muted 5.8, subtle 4.7). Accent text `#AD9BE4`
(5.1:1). Text-heavy glass gets `--via-scrim` behind it (the example finding's values).

**Colour.** Purple is the single accent: primary actions, active and selected states, focus, and
finding highlights. Status uses iOS system colours: green `#30D158` ok, amber `#FFB340` medium, red
`#FF453A` high and critical; low and info are neutral grey. The light theme uses Apple's accessible
variants (`#248A3D`, `#B25000`, `#D70015`).

**Radii.** Continuous and large: panels and cards 24–28px (`rounded-3xl`), dropzone and toasts 22px,
inputs 14px (`rounded-lg`), chips 10px, buttons, badges and the segmented control fully rounded.

**Type.** `-apple-system` / SF Pro on Apple devices (system font, never bundled), Inter elsewhere
(`@fontsource/inter`, OFL). Headlines 600 with tight tracking (−0.025 to −0.035em); body 15–17px on
the landing page with 1.6+ line height; 13–14px in the app. IBM Plex Mono stays for engineering
values only (net names, file types, measurements, revisions, check ids).

**Buttons.** `primary` is a glowing purple pill (`shadow-glow`); `secondary` a clear pill (tinted
fill, hairline, highlight). Both press down to 0.97 on a spring (`whileTap`).

**Motion** (Motion for React, `motion/react`; tokens in `@via/ui`: `SPRING`, `SPRING_SOFT`,
`SPRING_PRESS`, `enter`, `enterReduced`, `stagger`):
- Springs only (`stiffness` 300–500, `damping` 30, low bounce). Animate transform, opacity and filter.
- Entrances: fade + `blur(8px)` → 0 + 12px rise, staggered, `whileInView` once.
- Shared layout: the sidebar's active pill, the segmented control's thumb and the ⌘K highlight slide
  between items (`layoutId`); the sidebar collapse and project lists use `layout`.
- `LazyMotion` with `domMax` (needed for layout animations), `strict`, in the root `Providers`.
- `MotionConfig reducedMotion="user"` stops transform animations; components also check
  `useReducedMotion()` to turn off parallax, tilt, loops, count-ups and the skeleton shimmer, leaving
  short fades.

**Honesty still applies.** Nothing decorative is presented as data. Illustrations are labelled as
such, the example finding says "Example", and counters only animate real values (`CountUp` shows the
real value on first render and only tweens from the previous value when it changes, never from 0, so
nothing reads as a false zero).

## Colour

All colours are CSS variables on `[data-theme]` (`--via-*`), exposed to Tailwind as semantic
utilities (`bg-surface`, `text-muted`, `border-border`, …), which is the existing mechanism.
Components never use raw colours. Names stay the same as today, so existing screens restyle
automatically. Three tokens are new: `surface-sunken`, `accent-muted` and `accent-border`.

Contrast ratios below were measured (WCAG 2.x relative luminance) against the background and
panel colours.

### Dark theme (default): graphite

| Token | Value | Use | Contrast |
|---|---|---|---|
| `background` | `#111214` | App canvas | — |
| `surface-sunken` | `#0d0e10` | Sidebar, table headers, inset wells | — |
| `surface` | `#17181b` | Panels | — |
| `surface-raised` | `#1c1d21` | Menus, dialogs, popovers | — |
| `surface-hover` | `#212226` | Row and item hover | — |
| `border` | `#2a2b30` | Hairlines, dividers | — |
| `border-strong` | `#3a3c42` | Inputs, focused panels | — |
| `foreground` | `#e6e6e3` | Primary text (soft white, warm) | 15.0 : 1 |
| `muted` | `#9a9ca1` | Secondary text | 6.8 : 1 |
| `subtle` | `#80838a` | Metadata, timestamps | 4.9 : 1 (AA) |
| `accent` | `#8b7ab8` | Primary buttons, active marker, links | 5.0 : 1 |
| `accent-hover` | `#9b87d4` | Interactive accent (hover, focus) | 6.1 : 1 |
| `accent-foreground` | `#0f0e14` | Text on accent buttons | 5.1 : 1 on `accent` |
| `accent-soft` | `rgb(139 122 184 / 0.12)` | Active nav and selected-row surface | — |
| `accent-border` | `rgb(155 135 212 / 0.35)` | Selected-row edge | — |
| `ring` | `rgb(155 135 212 / 0.6)` | Focus ring | — |
| `success` | `#5fae84` | Muted green | 7.0 : 1 |
| `warning` | `#c9a14a` | Muted amber | 7.8 : 1 |
| `danger` | `#d9706a` | Muted red | 5.8 : 1 |
| `*-soft` | status colour at 12 % | Badge backgrounds | — |

Note: white text on `#8b7ab8` is only 3.8 : 1, so accent buttons use dark text in the dark theme.

### Light theme: neutral off-white

| Token | Value | Use | Contrast |
|---|---|---|---|
| `background` | `#f4f4f2` | Canvas (off-white, not pure white) | — |
| `surface-sunken` | `#ececea` | Sidebar, table headers | — |
| `surface` | `#ffffff` | Panels | — |
| `surface-raised` | `#ffffff` | Menus, dialogs (with shadow) | — |
| `surface-hover` | `#efefed` | Hover | — |
| `border` | `#dedfdc` | Hairlines | — |
| `border-strong` | `#c8cac6` | Inputs | — |
| `foreground` | `#1b1c1f` | Dark graphite text | 15.5 : 1 |
| `muted` | `#5c5f66` | Secondary text | 5.8 : 1 |
| `subtle` | `#6d7077` | Metadata | 4.5 : 1 (AA) |
| `accent` | `#5e4d93` | Deeper purple for light backgrounds | 6.4 : 1 |
| `accent-hover` | `#6a58a0` | Hover | 5.4 : 1 |
| `accent-foreground` | `#ffffff` | Text on accent | 7.1 : 1 |
| `accent-soft` | `rgb(94 77 147 / 0.08)` | Active and selected surface | — |
| `success` / `warning` / `danger` | `#2f7a52` / `#8a6110` / `#b4423c` | Status | 4.7 / 5.0 / 5.0 : 1 |

### Where purple appears (exhaustive)

- Primary button (one per view, at most).
- Active sidebar item: a 2 px left marker in `accent` plus an `accent-soft` surface.
- Selected table row or list item: `accent-soft` with an `accent-border` edge.
- Focus rings.
- Text links in body copy.
- The single "in progress" status (queued or running), so it reads as "VIA is working on it".

Everything else is neutral graphite. Status colours never use purple.

## Typography

**Proposed face: IBM Plex Sans and IBM Plex Mono**, self-hosted (Open Font License, no runtime
request to Google). Plex was drawn for engineering documentation: it has squared, legible numerals,
clear `0/O` and `1/l/I`, and a mono that matches it. It avoids the Inter/Geist look every generated
dashboard shares.

Delivery needs one of these (decision for approval):

- **A (recommended):** `@fontsource/ibm-plex-sans` and `@fontsource/ibm-plex-mono`, pinned, with
  only the 400, 500 and 600 weights in the Latin subset (about 90 KB woff2 in total). These are
  static files bundled at build time, with no network needed during the Docker build.
- **B:** keep today's system stack (`system-ui` / `ui-monospace`). No dependency; the look then
  varies by OS.

`next/font/google` is not proposed: it downloads at build time, which fails in network-restricted
builds.

### Scale (14 px base, 4 px grid)

| Role | Size / line height | Weight | Notes |
|---|---|---|---|
| Page title | 16 / 24 | 600 | One per page. No hero sizes. |
| Section title | 13 / 20 | 600 | Panel headers |
| Body | 14 / 20 | 400 | Default |
| Table and list | 13 / 20 | 400 | Dense rows |
| Label | 12 / 16 | 500 | Form labels, column headers (sentence case, `muted`) |
| Overline | 11 / 16 | 500 | Sidebar group names, uppercase, letter-spacing 0.06em, `subtle` |
| Metadata | 12 / 16 | 400 | Timestamps, counts (`subtle`, `tabular-nums`) |
| Mono | 12.5 / 20 | 400 | See below |

**Monospace is for engineering data only:** component references (`U3`, `R12`), net names (`+3V3`),
measurements (`0.254 mm`), file names and extensions (`.kicad_pcb`), revision numbers (`r4`), check
ids, and counts in tables. Never for headings or prose. A `<Mono>` primitive enforces this.

## Spacing, sizing and geometry

- **Spacing scale:** 4 px steps, using Tailwind's default (`1` = 4 px). Allowed gaps: 4, 8, 12,
  16, 24, 32. Panels use 12–16 px padding; page gutters are 24 px (desktop), 16 px (tablet and mobile).
- **Radii:** `radius-sm` 2 px (badges, kbd), `radius-md` 4 px (buttons, inputs, rows), `radius-lg`
  6 px (panels, dialogs, menus). Nothing larger. Avatars are the only round element.
- **Control heights:** 28 px (`sm`, toolbar and table actions), 32 px (`md`, default), 36 px (`lg`,
  primary page action and dialog footer). Inputs match buttons.
- **Rows:** 32 px compact (activity, nav), 40 px default (project table), 48 px with a second line.
- **Icons:** Lucide (already in use), 16 px in controls and nav, 14 px inline with metadata,
  stroke width 1.75. Icons accompany labels; icon-only buttons always have a tooltip and `aria-label`.
- **Borders:** 1 px everywhere. Elevation comes from surface steps, not shadows. Menus and dialogs
  only get `shadow-[0_8px_24px_rgb(0_0_0/0.35)]` in dark (`/0.12` in light).
- **Layout:** sidebar 232 px expanded, 52 px collapsed. Content max width 1440 px. Above that it
  centres; below it uses the full width, so a 1535 px screen no longer has 330 px of dead gutter.

## Components

The existing `@via/ui` package (Radix primitives with CVA and Tailwind) stays the only component
library; no second framework. Changes are restyles plus a few new primitives.

| Primitive | Status | Change |
|---|---|---|
| `Button` | exists | Heights 28/32/36. Variants: `primary` (purple), `secondary` (bordered), `ghost`, `danger`. Remove any rounded-full. |
| `Input`, `Select`, `Textarea` | exist | 32 px, `border-strong`, purple focus ring |
| `Badge` | exists | 2 px radius, 11 px medium; tones `neutral/accent/success/warning/danger` |
| `StatusDot` | exists | Pairs with a text label, never colour alone |
| `Table` | exists | Sticky `surface-sunken` header, 40 px rows, sortable header button with `aria-sort` |
| `Dialog`, `DropdownMenu`, `Tooltip` | exist | Restyle; enter/exit via CSS `data-state` keyframes |
| `Kbd` | **new** | Keyboard hint (`⌘K`) |
| `Mono` | **new** | Engineering identifiers |
| `Panel` | **new (replaces most `Card` use)** | Flat bordered region with a 40 px header row (title, meta, actions) |
| `CommandMenu` | **new** | Global search (projects via `q`, pages, actions) on Radix Dialog with listbox semantics. No new dependency |
| `Sheet` | **new** | Mobile navigation drawer on Radix Dialog |
| `NavItem` | **new (web app)** | Sidebar entry with active, disabled and "Soon" states and a collapsed tooltip |
| `ToastProvider` / `useToast` | **new** | Our own (no dependency): bottom-right stack (bottom-centre on phones), at most three, `status` role (errors `alert`), pauses on hover or focus, 5 s (errors 8 s). Use for results of an action the user started (upload finished, project created), never for page state |

### State conventions

| State | Treatment |
|---|---|
| Loading | Skeleton bars at the real row height (no spinners for lists) |
| Empty | One line of what this is, one action. Icon at 16 px, `subtle`. No illustration, except the dashboard's first-run state (below) |
| Error | `danger` text with the API's message and a **Retry** button |
| Unavailable | The section header stays; the body says why (for example "Requires analysis data, not exposed by the API yet") |
| Coming soon | Nav items are disabled, `subtle`, with a "Soon" badge, `aria-disabled`, and not focusable as a link |

### Dashboard first-run state

The only place in the signed-in app that uses the display serif (`font-display`, Instrument Serif,
a token in `packages/ui/src/styles.css`) and an illustration: a static, theme-token SVG of a bare
board. No glow, no grain, no animation. Everything else in the app stays flat.

## Motion

`motion` 14.12.0 is already a dependency. Proposed split:

- **CSS transitions** (no JS) for hover and colour changes (100 ms), sidebar width collapse
  (160 ms, `cubic-bezier(0.2, 0, 0, 1)`), and Radix menu, tooltip and dialog enter/exit via
  `data-state` keyframes (120 ms fade plus a 4 px translate).
- **`motion/react`** only where CSS can't do it cleanly:
  - the active-nav marker sliding between items (`layoutId`);
  - mobile `Sheet` drag/slide with `AnimatePresence` exit;
  - command-menu results reordering (`layout`).

  Load it with `LazyMotion` and `domAnimation` and the `m` component to keep the bundle cost small.
- **Never:** page entrance animations, staggered card reveals, looping or pulsing elements (except
  the existing spinner for an active job), parallax.
- **Reduced motion:** wrap the shell in `<MotionConfig reducedMotion="user">`. The existing global
  CSS rule already zeroes CSS durations.

## Component source: shadcn/ui

New components come from **shadcn/ui** (not 21st.dev). shadcn copies source into the repo, built on
the same Radix + CVA + `cn` stack `@via/ui` already uses, so it adds no runtime dependencies.
Existing components that credit a 21st.dev pattern in their header comment keep that credit.

**Setup.** `packages/ui/components.json` (style `new-york`, Radix, Tailwind v4, lucide) writes
components to `packages/ui/src/components/`; `apps/web/components.json` sends `ui` components
there too, so running from either directory works. Generated files import `cn` from `@via/ui/cn`
(a package export; `packages/ui` resolves it through its tsconfig `paths` and vitest alias).

```bash
cd packages/ui && pnpm dlx shadcn@4.23.0 add <component>   # pinned CLI; never shadcn@latest
```

Never run `shadcn init`: it would rewrite `styles.css` with its own palette. Bump the pinned CLI
version deliberately (at least two weeks old), like any other dependency.

**After every `add`**, before committing:

1. Review the diff. Revert anything the CLI wrote to `styles.css` and any dependency it added
   (justify and pin exact versions if one is genuinely needed).
2. Translate shadcn's colour names to VIA tokens. VIA's `accent` is purple and `muted` is a *text*
   colour, so `bg-accent` and `bg-muted` from shadcn would render wrong:

   | shadcn | VIA |
   |---|---|
   | `bg-primary` / `text-primary-foreground` | `bg-accent` / `text-accent-foreground` (primary action only) |
   | `bg-accent` / `text-accent-foreground` (hover, highlighted item) | `bg-surface-hover` / `text-foreground` |
   | `bg-muted` | `bg-surface` |
   | `text-muted-foreground` | `text-muted` (or `text-subtle` for metadata) |
   | `bg-popover` / `bg-card` | `bg-surface-raised` / `bg-surface` (or `Glass` within the blur budget) |
   | `bg-secondary` | `bg-surface` |
   | `border-input` | `border-border-strong` |
   | `bg-destructive` / `text-destructive` | `bg-danger-soft` / `text-danger` |
   | `ring-ring/50`, `ring-offset-*` | `ring-ring` (VIA's ring token already carries its opacity) |

3. Apply Black Glass: the radii above, `m.*` from `motion/react` with the `@via/ui` springs instead of
   `tw-animate-css` classes, and `data-state` enter/exit keyframes for Radix overlays.
4. Export it from `packages/ui/src/index.ts`, add a test in `components.test.tsx`, and add it to the
   component table above.

## Tooling used for this proposal

- **21st.dev MCP** (connected, free tier, AI generation off): searched the catalog for collapsible
  sidebars and command palettes as references for the icon rail, the mobile sheet and grouped
  ⌘K results. No component was installed. The catalog components assume shadcn and add their own
  dependencies; VIA already has Radix primitives, so the patterns are re-implemented on `@via/ui`.
- **Unslop** and **Frontend Design** plugins: not installed in this cloud session (`ListPlugins`
  returned none; only the 21st skill is synced). Their guidance was not invoked here. The
  "avoid generic AI UI" rules above come from your brief. Installed locally, they can review the
  implementation in Phase 6.
- **Motion:** already in `apps/web/package.json`. No install needed.

## Landing page (marketing) exception

The public landing page (`app/(public)/page.tsx`, `components/landing/*`, `app/(public)/landing.css`)
may use what the product UI does not: soft accent glows, a 32 px grid and trace motif, film
grain, a display serif (Instrument Serif, self-hosted) and entrance animations (motion, with
`MotionConfig reducedMotion="user"`; the scan line and marching dashes stop under reduced
motion). Every colour still derives from the theme tokens, so the light theme follows. The
signed-in app stays flat and dense.
