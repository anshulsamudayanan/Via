# VIA design system

Status: **implemented** (tokens in `packages/ui/src/styles.css`, primitives in `packages/ui`). Approved
choices: self-hosted IBM Plex, purple accent, unbuilt navigation shown disabled with "Soon".

## Principles

VIA is a tool engineers keep open all day next to KiCad. Every decision follows from that:

1. **Density over decoration.** Rows, not cards of cards. A 32 px row height is the default unit.
2. **Precision.** Hairline borders, a 4 px grid, restrained radii (2–6 px), tabular numbers,
   monospace for engineering identifiers.
3. **One accent.** Purple is VIA's identity colour. It marks primary actions, active navigation,
   selection and focus, and nothing else. It never fills a background or a gradient.
4. **Honest states.** Loading, empty, error, unavailable and coming soon each look different and say
   what is true. Nothing is shown that the API didn't return.
5. **Quiet motion.** Motion only explains a change of state (something opened, moved or arrived).
   It is short (120–200 ms) and turns off under `prefers-reduced-motion`.

Not allowed: gradients, glows, glass effects, decorative orbs or patterns, illustrations, pill-shaped
cards, oversized headings, and statistics that exist only to fill space.

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

### State conventions

| State | Treatment |
|---|---|
| Loading | Skeleton bars at the real row height (no spinners for lists) |
| Empty | One line of what this is, one action. Icon at 16 px, `subtle`. No illustration |
| Error | `danger` text with the API's message and a **Retry** button |
| Unavailable | The section header stays; the body says why (for example "Requires analysis data, not exposed by the API yet") |
| Coming soon | Nav items are disabled, `subtle`, with a "Soon" badge, `aria-disabled`, and not focusable as a link |

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
