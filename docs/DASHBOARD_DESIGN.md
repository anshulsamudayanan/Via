# Dashboard and shell redesign

Status: **Phase 1 (audit) and Phase 2 (proposal), awaiting approval.** No application code has
changed. Screenshots of the current UI are in `docs/design/current/`, captured from the running
Compose stack with a fresh account and two projects, each with one uploaded board.

---

## Part 1: Audit

### 1. Frontend architecture

- **Framework:** Next.js 16.4.5 with the App Router, React 19.3, TypeScript 5.9, Tailwind 4.3
  (CSS-first `@theme`, no `tailwind.config`).
- **Route groups:**
  - `(public)`: landing page and `/status`.
  - `(auth)`: login, register, forgot and reset password.
  - `(app)`: `/dashboard`, `/projects`, `/projects/[id]`, `/projects/[id]/designs/[id]` (with
    `?tab=` workspace tabs) and its `/viewer`, plus `/activity` and `/settings`.
- **Auth:** cookie session. `SessionProvider` (client) loads `/api/v1/auth/me` and redirects when
  signed out; `proxy.ts` guards routes at the edge. Unsafe requests carry the `X-VIA-Request` CSRF
  header (in `@via/api-client`).
- **Data:** `@via/api-client` provides a typed fetch client with the error envelope mapped to
  `ApiError`. Components use `useAsync(fn, deps)`, which handles abort, loading, error and reload.
  There is no SWR or React Query cache, so the same data is refetched per mount.
- **Rendering:** the whole `(app)` group is a client component (`"use client"` on its layout,
  needed for the session context). Pages are client-rendered after the session resolves.

### 2. Design and component system

- **`@via/ui`:** Badge, Button, Card, Dialog, DropdownMenu, Field/Input/Select/Textarea,
  EmptyState/ErrorState/Skeleton/Spinner, StatusDot, Table, Tooltip. Built on Radix, CVA and
  tailwind-merge.
- **Tokens:** semantic CSS variables in `packages/ui/src/styles.css`, with dark (default) and light
  palettes, switched by `data-theme` on `<html>`. A pre-hydration script prevents theme flash. The
  accent is blue `#5b9cff`. Radii are 4/6/8 px.
- **Fonts:** system stack only (`system-ui`, `ui-monospace`).
- **Icons:** `lucide-react` 1.70.
- **Motion:** `motion` 14.12.0 is installed but unused. A global CSS rule honours reduced motion.
- **Good foundations to keep:** semantic tokens only (enforced in CLAUDE.md), skip link,
  `aria-current` on nav, honest empty and error states, `tabular-nums` on numbers.

### 3. Visual problems (see screenshots)

1. **Dead space:** content is capped at `max-w-6xl` (1152 px). At 1535 px that leaves about 330 px
   of empty canvas on the right and 100 px on the left of the content
   (`dashboard-1535.png`).
2. **Half-empty stat row:** a 4-column grid holds two tiles, so half the row is blank. "Archived
   projects: 0" is not useful on a dashboard.
3. **Unbalanced columns:** the projects panel stretches to the activity panel's height, leaving a
   tall empty block under two rows.
4. **Weak hierarchy:** "Welcome back, Audit" is a greeting, not information. Every panel looks the
   same, so nothing leads.
5. **Generic identity:** blue accent, system font, rounded cards. It reads as a default template,
   not an engineering tool.
6. **Theme toggle placement:** it sits in the logo row, competing with the brand.

### 4. Usability problems

1. **Raw event keys in activity:** the feed shows `design.parsed` and `design.uploaded` literally.
   `lib/activity.ts` only describes account and project events; every Stage 2 event
   (`design.*`, `analysis.*`, `change_set.*`, `optimization.*`, `ai.*`) falls through to the raw key.
2. **Noise in the dashboard feed:** sign-ins and "created their VIA account" sit between
   engineering events.
3. **Project rows say little:** name, description, role and time only. The API already returns
   `design_count`, and the designs endpoint returns each design's latest import status; neither is shown.
4. **Mobile nav overflows:** at 390 px the nav is a horizontally scrolling strip and "Settings" is
   cut off (`dashboard-390.png`). The account menu is hidden on mobile entirely.
5. **No global search, no sorting on the dashboard, no keyboard shortcuts.**
6. **The sidebar can't collapse.** The account email truncates to "audit17957…".

### 5. Missing functionality (relative to the brief)

| Brief item | State |
|---|---|
| Collapsible sidebar with tooltips | Missing |
| Global search | Missing (projects page has its own search box) |
| Dashboard sorting and filtering | Missing (the projects page has it) |
| Design count and import status per project | Data available, not shown |
| Latest analysis status per project | Needs data; see section 6 |
| Global "Designs", "Analysis", "Components" pages | No cross-project API exists; these are per design today |
| Readable Stage 2 activity | Missing describers |
| Mobile drawer navigation | Missing |

### 6. API data actually available

| Endpoint | Gives | Dashboard use |
|---|---|---|
| `GET /projects/summary` | `{active, archived}` | Project counts |
| `GET /projects?q&status&sort=updated\|created\|name&limit≤100&offset` | `ProjectOut`: name, description, visibility, owner, `my_role`, `design_count`, archived, created and updated | Project table, search, sort, total designs (sum) |
| `GET /projects/{id}/designs` | `DesignOut`: `revision_count`, `current_revision`, `latest_revision` (status: processing, ready or failed) | Latest import status per project |
| `GET /designs/{id}/analysis-runs?limit=1` | Latest run: status, finding counts by severity | Latest analysis per design |
| `GET /activity?project_id&limit&offset` | All events on accessible projects, plus your own account events | Activity feed |
| `GET /auth/me` | User and organizations | Account menu |

There is **no** endpoint for global designs, global analysis runs, cross-project components,
activity filtered by type, or board thumbnails. There is no rendered preview image; the viewer
renders the board client-side from the full model, too heavy for a dashboard row. So the dashboard
shows **no PCB previews**.

### 7. Technical limitations

- **Per-project status needs a fan-out:** one `designs` request per visible project row. Analysis
  status per project would need one more request per design.
- **Totals can be partial:** "Total designs" from summing `design_count` is exact only up to 100
  active projects (one page). Beyond that it must say "100+" or page through.
- **Activity type filter is client-side:** the server can't filter by type, so the dashboard
  fetches a page (25) and hides `auth.*` and `user.*` events. A page can therefore show fewer than 8
  rows; it says so and links to the full feed.
- **No query cache:** navigating back refetches. Acceptable at this scale.

### 8. Recommended approach

Restyle through tokens first (every existing screen benefits). Rebuild only the shell (sidebar,
mobile sheet, command menu) and the dashboard page. Keep `@via/ui` and Radix. Add no UI
framework. All data comes from the endpoints above. One optional, additive backend change
(decision 2 below) would make the overview exact without fan-out.

---

## Part 2: Proposal

### Design direction

An **engineering workstation**:

- a dark graphite canvas, flat panels with hairline borders and dense rows;
- one restrained purple accent used only for action, selection and focus;
- IBM Plex type, with mono for engineering identifiers.

The structure borrows Linear's information hierarchy and GitHub's project and activity model.
The precision is KiCad and Altium's. The look borrows none of them: no gradients, no glow, no
glass, no illustrations. Full tokens are in [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md).

### Sidebar

```
Expanded (232 px)                    Collapsed (52 px)
┌──────────────────────────┐         ┌──────┐
│ ◉ VIA              [«]   │         │  ◉   │
│ ┌──────────────────────┐ │         │  ⌕   │  ← opens ⌘K
│ │ ⌕ Search…        ⌘K  │ │         │      │
│ └──────────────────────┘ │         │  ▦   │  ← tooltip "Dashboard"
│ WORKSPACE                │         │  ▤   │
│ ▌▦ Dashboard             │ ← 2 px  │  ∿   │
│  ▤ Projects              │  purple │  ─   │
│  ∿ Activity              │  marker │  ◫·  │  ← disabled, tooltip
│ ENGINEERING              │         │  ◇·  │    "Designs: coming soon"
│  ◫ Designs        Soon   │         │  ⊞·  │
│  ◇ Analysis       Soon   │         │      │
│  ⊞ Components     Soon   │         │      │
│ PLATFORM                 │         │  ⚙   │
│  ⚙ Settings              │         │      │
│                          │         │      │
├──────────────────────────┤         ├──────┤
│ (AU) Audit User   ☾  ⌃   │         │ (AU) │
└──────────────────────────┘         └──────┘
```

- **Designs, Analysis and Components are shown disabled with "Soon"**, because there is no
  cross-project API. They are not links, so they are not fake destinations. Their tooltip says
  "Open a project to see its designs". *Alternative: omit them until they exist* (decision 3).
- Collapse state persists in `localStorage` (wrapped in try/catch) and toggles with `[`.
- The theme toggle moves into the account row.
- The account menu shows the full email in the menu label rather than truncating it in the bar.
- Accessibility:
  - `<nav aria-label="Main">`, `aria-current="page"`, and group headings as list labels;
  - collapse button with `aria-expanded`;
  - tooltips only when collapsed.
- **Tablet (768–1279 px):** starts collapsed. **Mobile (<768 px):** a 48 px top bar (logo,
  search, menu) opens the sidebar as a left `Sheet` with focus trap and Esc to close.

### Dashboard (1535 × 812)

```
┌────────┬──────────────────────────────────────────────────────────────────────────────────┐
│        │ Dashboard                                         [⌕ Search ⌘K] [↑ Upload PCB] [+ New project] │
│        │ Projects, designs and engineering activity you have access to.                    │
│        ├──────────────────────────────────────────────────────────────────────────────────┤
│ side   │ Active projects 2 │ PCB designs 2 │ Imports, last 7 days 2 │ Analyses, last 7 days 0 │ ← one 56 px strip,
│ bar    ├──────────────────────────────────────────────────────┬───────────────────────────┤   dividers, no cards
│        │ Projects                    [Filter…] [Updated ▾] →  │ Activity            All → │
│        │ ─────────────────────────────────────────────────────│───────────────────────────│
│        │ NAME              DESIGNS  LAST IMPORT   ROLE  UPDATED│ ● Parsed via_ref….kicad_pcb│
│        │ Sensor hub rev B     1     ● Ready r1   Owner  2m    │   Sensor hub rev B · 2m   │
│        │   Audit fixture project                              │ ↑ Uploaded via_ref…       │
│        │ Motor controller     1     ● Ready r1   Owner  3m    │   Motor controller · 3m   │
│        │   Audit fixture project                              │ ✓ Analysis: 15 findings   │
│        │ …up to 8 rows                                        │ + Created project         │
│        │                                                      │   …                       │
│        │ Showing 2 of 2 active projects        View all →     │                           │
│        └──────────────────────────────────────────────────────┴───────────────────────────┘
```

- **Grid:** content `max-w-[1440px]`, 24 px gutters; main row `grid-cols-[minmax(0,1fr)_360px]`.
  The two columns size to their content (`items-start`), so neither stretches into an empty block.
- **Header:** a 16 px title plus a one-line description. The greeting goes away. Actions are
  search (opens ⌘K), Upload PCB (the existing `UploadShortcut`) and New project (the existing
  `NewProjectDialog`, the only purple button).
- **Overview strip:** four real numbers in one bordered strip, not four cards.
  - **Active projects:** `summary.active`.
  - **PCB designs:** the sum of `design_count` over the active projects page. Shows "100+" if
    truncated.
  - **Imports and analyses, last 7 days:** counted from activity (`design.uploaded`,
    `analysis.completed`). Needs decision 2 to be exact; otherwise these two cells are dropped,
    not estimated.
  - Each cell links to the relevant list. "Archived projects" moves to the Projects page filter.
- **Projects table** (`Table` primitive, 40 px rows, description as a muted second line):
  - Columns: Name, Designs (mono), Last import, Role, Updated.
  - **Last import** = status dot plus label of the most recently updated design's
    `latest_revision` (Ready, Processing or Failed), plus the revision number in mono. It is fetched
    lazily per visible row; a skeleton shows while it loads.
  - **Latest analysis** column only with decision 2. Without it, the per-row fan-out is too costly,
    and the column is not shown rather than left half-empty.
  - Filter box (debounced 250 ms, server `q`) and a sort menu (Updated, Created, Name; server
    `sort`), with `aria-sort` on headers.
  - Whole-row link to the project, so the table is keyboard navigable.
  - Footer: "Showing n of total" plus View all.
- **Activity:** compact 2-line entries: icon, verb plus object, then project and relative time
  (absolute time on hover).
  - Describers are added for every Stage 2 event, for example "Parsed `board.kicad_pcb` (r2)",
    "Analysis completed: 15 findings", "Applied change set", "Rolled back to r1".
  - `auth.*` and `user.*` are hidden on the dashboard (still on `/activity`).
  - Analysis and design events link to the design workspace when `target_id` resolves to a design.
- **Empty account:** the overview strip and table are replaced by one panel: "Create a project,
  then upload a KiCad board (`.kicad_pcb` or a zipped project)", with New project as the action.
  Activity stays.
- **Not added:** PCB previews (no render endpoint), "projects requiring attention" (needs
  analysis data per project), and charts.

### Responsive

| Width | Sidebar | Dashboard |
|---|---|---|
| ≥ 1280 | Expanded (user can collapse) | 2 columns (table and 360 px activity) |
| 768–1279 | Collapsed rail | Table full width; activity below; overview strip 4 → 2×2 |
| < 768 | Top bar plus Sheet | Stacked; project rows become 2-line list items (name and status / designs · updated); actions in the header wrap; no horizontal scroll (verified at 390 px) |

### Component hierarchy

```
(app)/layout.tsx
└─ SessionProvider
   └─ AppShell                         (rewritten)
      ├─ MotionConfig reducedMotion="user" + LazyMotion
      ├─ Sidebar                       (new)  ← NavGroup / NavItem / AccountMenu / ThemeToggle
      ├─ MobileTopBar + Sheet          (new, < md)
      ├─ CommandMenu                   (new, ⌘K, mounted once)
      └─ main
         └─ dashboard/page.tsx         (rewritten)
            ├─ PageHeader              (restyled)
            ├─ OverviewStrip           (new)    ← summary, projects page, activity
            ├─ ProjectsPanel           (new)    ← Panel, Table, ProjectRow, LastImportCell
            └─ ActivityPanel           (new)    ← ActivityEntry (shared with /activity)
```

### Files to modify or create

| File | Change |
|---|---|
| `packages/ui/src/styles.css` | New tokens (purple accent, graphite, radii, fonts, `surface-sunken`, `accent-border`), keyframes for `data-state` |
| `packages/ui/src/components/{button,badge,card,table,dialog,dropdown-menu,tooltip,form,states}.tsx` | Restyle to the system; Table gains sortable header |
| `packages/ui/src/components/{kbd,mono,panel,sheet,command-menu}.tsx` (new) and `index.ts` | New primitives |
| `apps/web/components/app-shell.tsx` | Rewritten shell |
| `apps/web/components/shell/{sidebar,nav-item,mobile-nav,account-menu}.tsx` (new) | Shell parts |
| `apps/web/app/(app)/dashboard/page.tsx` | Rewritten dashboard |
| `apps/web/components/dashboard/{overview-strip,projects-panel,activity-panel}.tsx` (new) | Dashboard sections |
| `apps/web/components/activity-list.tsx`, `apps/web/lib/activity.ts` | Shared entry component; Stage 2 describers |
| `apps/web/app/layout.tsx` | Font imports (if option A), `themeColor` values |
| `apps/web/package.json` | `@fontsource/ibm-plex-sans`, `@fontsource/ibm-plex-mono` (option A only) |
| Tests | Unit: nav states, command menu, describers, sorting and filtering, empty, error and loading. e2e: update selectors in existing specs, add a dashboard spec. Screenshots at 1535, 1280, 768 and 390 in both themes |
| *(decision 2 only)* `apps/api/.../schemas/projects.py`, `routes/projects.py` | Additive fields on `ProjectSummary`, with tests |

### Implementation plan (after approval)

1. **Phase 4:** tokens, fonts and primitive restyles. Run the full web test suite and e2e (existing
   screens must still pass) and take screenshots of every existing page in both themes.
2. **Phase 5:** shell (sidebar, mobile sheet, command menu), then the dashboard and activity describers.
3. **Phases 6–7:** QA matrix (themes × 4 viewports × empty, populated, loading and error states),
   keyboard pass, contrast check, bundle size before and after, screenshots in
   `docs/design/after/`. Commit and push.

### Decisions needed

1. **Font:** A, self-hosted IBM Plex (recommended), or B, the system stack.
2. **Exact overview counts:** add read-only fields to `GET /projects/summary` (`design_count`,
   `imports_7d`, `analyses_7d`, and a latest-analysis status per project). This is an additive
   API change: no existing field changes, it ships with tests and the contracts stay compatible.
   Otherwise the dashboard shows only what the current endpoints give and drops the cells and
   column it can't fill.
3. **Engineering nav items** (Designs, Analysis, Components): show them disabled with "Soon"
   (recommended), or hide them until cross-project views exist.
