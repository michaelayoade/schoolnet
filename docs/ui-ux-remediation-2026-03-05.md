# UI/UX Remediation Plan — 2026-03-05

## Scope & objective
Align SchoolNet web UX to the actual product objective:
- Clear school-domain positioning (not generic ERP)
- Trust and usability for school admins/parents
- Fast navigation and readable data density
- Accessibility-first defaults

## Route inventory (existing routes only)
Validated from `app/main.py` + `app/web/*`:

### Public
- `/`
- `/schools`
- `/schools/{slug}`
- `/register`
- `/login`
- `/admin/login`

### Platform admin
- `/admin`
- `/admin/people`
- `/admin/roles`
- `/admin/permissions`
- `/admin/settings`
- `/admin/scheduler`
- `/admin/audit`
- `/admin/notifications`
- `/admin/file-uploads`
- `/admin/schools`
- `/admin/billing/*`

### School admin / parent
- `/school`, `/school/profile`, `/school/forms`, `/school/applications`, `/school/payments`, `/school/notifications`
- `/parent`, `/parent/applications`, `/parent/wards`, `/parent/notifications`

## P0 (must fix)
- [ ] Replace generic "Dotmac ERP" value messaging on public pages with SchoolNet domain language.
- [ ] Update hero copy on `/` to school outcomes (enrollment, admissions, fees, compliance, parent visibility).
- [ ] Ensure login and onboarding copy clearly states school context and tenant identity.
- [ ] Fix authenticated capture workflow so route audits are based on real authenticated views.

## P1 (high value)
- [ ] Improve module discoverability on landing/admin nav with school-centric IA labels.
- [ ] Improve contrast and text size for secondary icon/text rows.
- [ ] Normalize CTA language (e.g., "Set up your school", "Open school dashboard").
- [ ] Improve metric card readability (formatting, labels, time windows).

## P2 (polish)
- [ ] Sentence case labels for readability where ALL-CAPS is used unnecessarily.
- [ ] Footer links and copy tailored to school workflows/support.
- [ ] Visual polish pass (spacing rhythm, card depth consistency, focus styling).

## Out of scope / invalid routes removed
These were previously assumed but are not registered SchoolNet web routes:
- `/finance/dashboard`
- `/finance/gl/trial-balance`
- `/inventory/items`
- `/people/hr/employees`
- `/dashboard` (platform dashboard route is `/admin`)

## Acceptance criteria
- Authenticated capture script logs in successfully and captures non-redirect screenshots for admin routes.
- Public pages use SchoolNet-specific language, not generic ERP wording.
- Route-based UI audits only reference registered routes from `app/main.py` router registration.
- Accessibility basics validated (contrast, focus visibility, touch target size for controls).
