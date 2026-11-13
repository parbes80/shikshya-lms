# Shikshya LMS — UI/UX Modernization Log

**Phase:** 2 (design system) and first Phase 3 slice (public homepage)
**Date:** 2026-11-13
**Companion documents:** `docs/TECHNICAL_ASSESSMENT.md`, `docs/IMPLEMENTATION_ROADMAP.md`, `docs/UX_UI_IMPROVEMENT_PLAN.md`

---

## 1. What this increment changes

This is an additive, low-risk slice. No routes, models, database schema or
business logic were changed. Existing pages continue to use their current
styles; the new layer aligns the shared brand tokens and adds reusable
primitives for later phases.

### Design tokens

`static/css/design-system.css` is loaded after the legacy stylesheets and:

- Aligns the primary brand hue with indigo `#4338CA` by overriding the shared
  `--primary-h/s/l` tokens.
- Adds the master-brief palette as `--ds-*` tokens: violet `#7C3AED`,
  background `#F8FAFC`, surface `#FFFFFF`, text `#0F172A`, muted `#64748B`,
  success `#16A34A`, warning `#F59E0B`, error `#DC2626`.
- Keeps the existing green `--secondary` semantics for success states so
  existing alert/status colours remain correct.
- Defines light and dark values, focus rings, shadows and radii.

### Reusable primitives

The new layer provides `.ds-btn`, `.ds-card`, `.ds-badge`, `.ds-alert`,
`.ds-empty`, `.ds-skeleton`, `.ds-field-error`, `.ds-table-wrap`,
`.ds-check-list`, `.ds-faq` and layout helpers. These are ready for the
dashboard and course work in later phases.

### Accessibility and shell

`templates/base.html` now includes:

- A keyboard-visible **Skip to main content** link.
- `id="main-content"` and `tabindex="-1"` on the main landmark.
- `aria-label`/`aria-expanded` wiring for the mobile navigation.
- A responsive site footer with real links only.
- Inclusive meta description and keywords (no longer programming-only).
- An inclusive AI-assistant greeting.

`static/js/main.js` now keeps `aria-expanded` in sync, and defaults the theme to
the operating-system preference when the user has not chosen one.

### Public homepage

`templates/home.html` was refreshed with:

- An inclusive hero for school and college students, teachers, training centres
  and independent educators.
- A factual "platform snapshot" card driven by real database counts.
- "Who Shikshya is for", "How it works", "Why Shikshya" and FAQ sections.
- Real categories, published courses and platform statistics.
- Meaningful empty states when no categories or courses exist.
- An institution enquiry section that does **not** claim multi-tenancy.
- No invented testimonials, partnerships or activity figures. The previous
  hardcoded "Completed by 85%" mock card was removed.

## 2. Modified files

- `static/css/design-system.css` (new)
- `templates/base.html`
- `templates/home.html`
- `static/js/main.js`
- `tests/test_main.py`

## 3. Database changes

None. No migrations are required for this increment.

## 4. Verification

```text
python -m compileall -q app.py config.py extensions.py routes utils tests
python -m pytest -q
122 passed
```

New regressions:

- Homepage contains the inclusive sections and real course data.
- The old invented activity figure is absent.
- The shared layout includes the skip link, main landmark and footer.

## 5. Outstanding work

- Apply the design-system primitives to student, teacher and admin dashboards
  (Phase 4).
- Replace inline page styles with the shared component classes over time.
- Add loading skeletons and empty states to data-heavy dashboard widgets.
- Enforce CSP after inline scripts/styles are moved to static files.
- Continue the course/assignment/examination depth work in Phase 5.
