# SchoolNet UI/UX Audit — Wave 2

**Date:** 2026-03-04
**Auditor:** Claude (automated)
**Scope:** Public pages, parent portal, school dashboard, admin dashboard, base templates
**Branch:** `feat/ui-ux-wave1-schoolnet`

---

## P0 — Critical (Blocks usability)

### P0-1: School search cards have no visual hierarchy
- **Page:** `/schools` (search results)
- **Issue:** All text uses `text-xs` — school name, type, location, and fees all blend together. Users cannot scan results quickly. Fee information (the primary decision factor) is visually buried.
- **Fix:** Increase name to `text-base font-semibold`, add location icon, make fee prominent with color + weight, add rating stars inline.

### P0-2: No active filter indicators on school search
- **Page:** `/schools`
- **Issue:** When a user applies filters (state, type, category, etc.), there is no visible indication of which filters are active. Users cannot tell what's filtering results or clear individual filters.
- **Fix:** Add filter pill badges below the search form showing active filters with individual clear buttons.

### P0-3: Parent dashboard missing key quick action cards
- **Page:** `/parent`
- **Issue:** Dashboard only shows "Find Schools" and "My Applications" — missing "My Wards" and "Payments" which are primary workflows. Stat cards lack iconography for quick scanning.
- **Fix:** Add ward + payment quick action cards, add icons to stat cards.

---

## P1 — High Impact (Degrades experience)

### P1-1: "How It Works" section lacks visual flow on desktop
- **Page:** `/` (public homepage)
- **Issue:** The three steps appear as isolated columns on desktop with no visual connection. Users don't perceive a sequential flow.
- **Fix:** Add connecting arrow/line elements between steps on `md:` breakpoint and above.

### P1-2: School profile page header CTA is buried
- **Page:** `/schools/<slug>`
- **Issue:** The "Apply Now" button(s) only appear in the admission forms section below the fold. The profile header has no primary action button.
- **Fix:** Add a floating "Apply" CTA or prominent action button in the school header area.

### P1-3: Footer links are dead
- **Page:** All public pages
- **Issue:** "Privacy" and "Terms" footer links point to `#` — dead links that erode trust.
- **Fix:** Either create placeholder pages or remove the links until content is ready.

### P1-4: School cards on homepage vs search are inconsistent
- **Page:** `/` vs `/schools`
- **Issue:** Homepage featured school cards use `rounded-2xl`, `p-5`, larger logos. Search result cards use `rounded-xl`, `p-4`, smaller logos. Inconsistent visual language.
- **Fix:** Unify card component treatment across both pages.

### P1-5: Search form doesn't indicate "searching" state
- **Page:** `/schools`
- **Issue:** Submitting the search form does a full page reload with no loading indicator. Users may think nothing happened on slow connections.
- **Fix:** Add HTMX `hx-get` with loading state, or at minimum add a spinner to the submit button.

---

## P2 — Nice to Have (Polish)

### P2-1: Homepage stats are hardcoded
- **Page:** `/`
- **Issue:** "100+", "1K+", "36" stats in the trust section are hardcoded in the template rather than pulled from platform data.
- **Impact:** Low — acceptable for MVP, but should eventually be dynamic.

### P2-2: Admin dashboard quick action buttons lack visual differentiation
- **Page:** `/admin`
- **Issue:** Secondary action buttons (Add Role, Upload File, Branding) are visually identical — all use the same border style with no iconographic differentiation beyond the SVG.
- **Impact:** Low — functional but could benefit from color-coded categories.

### P2-3: School dashboard "no school registered" empty state is plain
- **Page:** `/school`
- **Issue:** The empty state for unregistered schools uses a generic building SVG. Could be more welcoming with an illustration and clearer onboarding steps.
- **Impact:** Low — only seen once per school during onboarding.

### P2-4: Dark mode toggle not visible on public pages
- **Page:** All public pages
- **Issue:** The dark mode toggle is only in the admin/school/parent portal topbar. Public-facing pages (homepage, search, login) have no way for users to switch themes.
- **Impact:** Low — system preference detection exists, but manual override is missing.

### P2-5: Pagination component lacks keyboard focus indicators
- **Page:** All list pages with pagination
- **Issue:** Pagination links don't have visible `:focus` ring styles, only hover styles. Keyboard users can't see which page link is focused.
- **Impact:** Low — most users navigate via mouse/touch, but affects accessibility compliance.

---

## Implementation Plan (This Wave)

| # | Finding | Files Changed | Effort |
|---|---------|---------------|--------|
| 1 | P0-1: Enhanced school search cards | `templates/public/schools/search.html` | S |
| 2 | P0-2: Active filter indicators | `templates/public/schools/search.html` | M |
| 3 | P1-1: How It Works connectors | `templates/public/index.html` | S |
| 4 | P0-3: Parent dashboard improvements | `templates/parent/dashboard.html` | M |
| 5 | P1-2: School profile header CTA | `templates/public/schools/profile.html` | S |

**Not in scope this wave:** P1-3 (requires content), P1-5 (requires route changes), P2-* items.
