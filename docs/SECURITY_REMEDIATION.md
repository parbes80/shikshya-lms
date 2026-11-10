# Shikshya LMS — Security Remediation Log

**Sprints:** Phase 0, Sprint 1 and Sprint 2
**Date:** 2026-11-10
**Companion documents:** `docs/TECHNICAL_ASSESSMENT.md`, `docs/IMPLEMENTATION_ROADMAP.md`
**Status:** Implemented and verified locally; not yet deployed to staging.

---

## 1. Scope

Sprint 1 addressed the highest-impact findings that could be fixed without a
schema migration. Sprint 2 closed the remaining Phase 0 application-security
findings: rich-content XSS, document SSRF/IDOR, upload abuse, CSRF-unsafe GET
actions, session/proxy/header hardening, and auth throttling.

| Finding | Status | Regression tests |
|---|---|---|
| SEC-01 — Admin self-registration | Fixed | `tests/test_auth.py` |
| SEC-02 — Quiz IDOR + answer-key disclosure | Fixed | `tests/test_api.py` |
| SEC-03 — Password-reset token leakage + enumeration | Fixed | `tests/test_auth.py` |
| SEC-04 — Stored XSS in lessons/labs/Markdown | Fixed | `tests/test_security.py` |
| SEC-05 — Lesson-document SSRF/IDOR | Fixed | `tests/test_security.py` |
| SEC-06 — Public exposure of user locations | Fixed | `tests/test_branch.py` |
| SEC-07 — Unrestricted upload types/filenames | Fixed | `tests/test_security.py` |
| SEC-08 — Default demo credentials auto-seeded | Fixed | `tests/test_seed.py` |
| SEC-09 — State-changing GET actions | Fixed | `tests/test_security.py`, `tests/test_dashboard.py` |
| SEC-10 — Evaluation grading IDOR + unclamped scores | Fixed | `tests/test_evaluation.py` |
| SEC-11 — Discussion reply IDOR | Fixed | `tests/test_api.py` |
| SEC-12 — Evaluation listing leak | Fixed | `tests/test_evaluation.py` |
| SEC-13/14 — Proxy, HTTPS, headers, session cookies | Fixed | `tests/test_security.py` |
| SEC-15 — Login/forgot-password throttling | Fixed | Config/route review; limiter disabled in tests |

No existing functionality was removed. No database schema changes were made.


---

## 2. SEC-01 — Block admin self-registration

**Problem:** `POST /register` accepted `role=Admin`, created an already-approved
administrator, and allowed full platform takeover.

**Change:**
- Public registration is restricted server-side to `Student` and `Teacher`.
- Admin accounts can only be created by an operator through the new
  `create-admin` CLI command.
- The template already hid the Admin option; the server now enforces it.

**Files:** `routes/auth.py`, `app.py`, `README.md`, `DEPLOYMENT.md`

**Verification:**
- `POST /register` with `role=Admin` flashes `Invalid role` and creates no user.
- `Admin` remains a valid role for normal login and dashboard routing.

**Command:**
```bash
python manage.py create-admin
```

---

## 3. SEC-02 — Quiz authorization and answer-key protection

**Problem:** Any authenticated user could submit any `quiz_id`, create attempts
for courses they were not enrolled in, and receive every correct answer in the
JSON response.

**Change:**
- Quiz IDs are parsed safely; malformed answer IDs no longer cause a 500.
- Only users with the `Student` role may create attempts.
- Enrollment in the quiz's course is required before scoring or persisting an
  attempt.
- Lesson completion and attempt limits are enforced against the resolved
  enrollment.
- Results are returned only after an authorized attempt.

**Files:** `routes/api.py`

**Verification:**
- Unenrolled student → `403`, no `QuizAttempt`.
- Student enrolled in another course → `403`, no answer key.
- Teacher/Admin → `403`, no fake attempt.
- Enrolled student still receives score, pass/fail, and corrections.

---

## 4. SEC-03 — Password-reset leakage and account enumeration

**Problem:** When SMTP was unconfigured, the reset link was flashed to the
browser and printed to logs. Forgot-password also revealed whether an email
existed.

**Change:**
- Forgot-password always returns the same generic message, whether or not the
  account exists.
- A pending request is created only for real accounts; a duplicate request is
  silently ignored.
- Admin-triggered reset flows never flash, print, or log the reset link.
- If mail delivery fails, the administrator sees a configuration warning with
  no credential material.
- Reset links now expire after 1 hour, and the email copy matches.
- Mail logs no longer include recipient addresses.

**Files:** `routes/auth.py`, `utils/mail.py`,
`templates/emails/password_reset.html`

**Verification:**
- Known and unknown emails produce the same public response.
- Response bodies and captured logs contain no token or `/reset-password/` URL.

**Remaining limitation (Phase 1):** reset tokens are still stored in plaintext
in the database and are not yet invalidated across sessions. Token hashing and
session invalidation remain scheduled as P1-03.

---

## 5. SEC-06 — Public user-location exposure

**Problem:** `/branches/api/data` and the public branch map returned every
learner's username, city, latitude, and longitude without authentication.

**Change:**
- The public API returns only active branch records.
- The map renders branch markers only.
- No learner profile or GPS data is queried for these public views.

**Files:** `routes/branch.py`, `templates/branches_map.html`

**Verification:**
- Public JSON has no `users` key, username, or learner coordinates.
- The public map page does not contain a seeded learner's username.

---

## 6. SEC-08 — Default demo credentials

**Problem:** `seed.py` created `admin/admin123`, `teacher123`, and `student123`
and the README published them. Startup seeded automatically when roles were
missing.

**Change:**
- Demo users, courses, and categories require `SEED_DEMO_DATA=true` and are
  skipped otherwise.
- Roles are still ensured on every bootstrap so registration and the CLI work
  on an empty database without creating known-password accounts.
- `python seed.py` refuses to run unless demo seeding is explicitly enabled.
- The documented production path is `python manage.py create-admin`.
- README now labels demo credentials as development-only and documents the flag.
- `.env.example` defaults `SEED_DEMO_DATA=false`.

**Files:** `config.py`, `app.py`, `seed.py`, `README.md`, `.env.example`,
`DEPLOYMENT.md`

**Verification:**
- Empty database + demo disabled → 3 roles, 0 users.
- Demo enabled → 3 demo users; rerunning is idempotent.
- `create-admin` creates an approved Admin with a chosen password.
- Boot check with an isolated SQLite database passed.

---

## 7. SEC-10 / SEC-11 / SEC-12 — Remaining IDORs

### Evaluation grading
- Submission lookup is scoped to `(submission_id, evaluation_id)`.
- Scores are clamped to `[0, max_score]`.
- Missing or non-numeric scores return `400`.

### Discussion replies
- Replies require enrollment in the topic's course, course ownership, or Admin
  role.
- Cross-course posting and notification spam are blocked.

### Evaluation listing
- Students must be enrolled in the course before listing evaluations.

**Files:** `routes/evaluation.py`, `routes/api.py`

**Verification:**
- Teacher of course A cannot grade course B's submission (`404`, unchanged).
- Negative and over-maximum scores are clamped.
- Unenrolled students cannot list evaluations or reply to discussions.

---

## 8. SEC-04 — Rich-content sanitization

**Problem:** Lesson HTML, lab HTML and Markdown output were rendered with the
`safe` filter. A teacher or lab author could store a script payload that ran for
every learner, and legacy rows could still contain one.

**Change:**
- Added `utils/sanitize.py` with a `bleach` allowlist for formatting, tables,
  code and images.
- `script`, `style`, `iframe`, `object`, `embed`, `form` and `noscript` blocks
  are removed together with their contents.
- Event-handler attributes, `style` attributes and unsafe URL schemes are
  stripped; only `http`, `https`, `mailto` and relative URLs are accepted.
- HTML is sanitized when saved and again when rendered, covering legacy rows.
- Markdown is rendered through the sanitized `markdown` filter; Markdown source
  is not corrupted by the HTML cleaner.
- Markdown lessons now render as Markdown instead of raw source.
- Inline URL fields (video/document/lab/evaluation/live-class/submission links)
  pass through `safe_url`, which rejects `javascript:` and obfuscated variants.
- Templates render stored asset and meeting links through the `asset_url`
  filter so legacy unsafe schemes cannot become clickable. The calendar script
  also validates event URLs before assigning `href`.

**Files:** `utils/sanitize.py`, `app.py`, `routes/course.py`, `routes/lab.py`,
`routes/evaluation.py`, `routes/api.py`, content templates.

**Verification:** Stored script payloads, legacy unsafe rows and Markdown XSS
payloads are neutralised (`tests/test_security.py`).

---

## 9. SEC-05 — Lesson-document SSRF and IDOR

**Problem:** `/api/lessons/<id>/download` let any authenticated user download any
lesson document and made a server-side HTTP request to any URL stored in the
lesson, enabling SSRF against internal services and cloud metadata endpoints.

**Change:**
- Downloads require enrollment in the lesson's course, course ownership, or the
  Admin role.
- No arbitrary server-side HTTP requests are made. Local documents are served
  from `UPLOAD_FOLDER` after normalisation and traversal checks.
- External documents are only redirected when the host is
  `res.cloudinary.com` or the configured `SITE_URL` host.
- Any other scheme or host returns `400`; missing/traversal paths return `404`.

**Files:** `routes/api.py`

**Verification:** Unenrolled users get `403`; cloud-metadata URLs get `400`;
path traversal gets `404`; enrolled learners still download local files
(`tests/test_security.py`).

**Known limitation:** external document links on hosts other than Cloudinary or
`SITE_URL` are no longer proxied. Teachers should upload the file or use
Cloudinary.

---

## 10. SEC-07 — Upload hardening

**Problem:** Several upload paths accepted arbitrary extensions (including
`.html`, `.js`, `.css`, `.php`) and saved under public `static/uploads`. The
Cloudinary temp file used the client filename.

**Change:**
- Added `utils/uploads.py` with explicit allowlists:
  - images: `png jpg jpeg gif webp`
  - documents: `pdf doc docx ppt pptx xls xlsx txt csv odt rtf`
  - submissions: documents + images + `zip`
- `.html`, `.js`, `.css`, `.svg`, `.php`, `.exe` and similar formats are
  rejected everywhere.
- Stored names are generated from a safe prefix plus UUID; the client filename
  is never used on disk.
- File size is validated against `MAX_CONTENT_LENGTH`.
- Sensitive student submissions stay on local disk; other assets use
  Cloudinary when configured and fall back to local storage instead of silently
  losing the upload.
- Cloudinary temp files use `tempfile.mkstemp` with a random name.
- Lab PDFs, lesson documents, thumbnails, avatars, lab-manual images/PDFs,
  evaluation papers and submissions all use the shared validator.

**Files:** `utils/uploads.py`, `utils/cloudinary_upload.py`, `routes/auth.py`,
`routes/course.py`, `routes/lab.py`, `routes/evaluation.py`, `routes/api.py`

**Verification:** `.html` uploads are rejected for assignments, lesson documents
and labs; valid PDFs are stored with generated names (`tests/test_security.py`).

**Known limitation:** files are still served from `static/uploads` (except
lesson documents). The allowlist plus `X-Content-Type-Options: nosniff` prevents
stored HTML/JS execution. Moving all uploads outside `static` and serving them
through authenticated routes remains a Phase 1 storage task.

---

## 11. SEC-09 — State-changing GET → POST

**Problem:** Approvals, password-reset approval, evaluation publish/unpublish
and logout changed state over GET, so a link or image could trigger them.

**Change:**
- `POST` is now required for:
  - `/dashboard/admin/approve-teacher/<id>`
  - `/dashboard/admin/approve-course/<id>`
  - `/dashboard/admin/approve-payment/<id>`
  - `/admin/approve-reset-request/<id>`
  - `/evaluations/<id>/publish`
  - `/evaluations/<id>/unpublish`
  - `/logout`
- Templates use POST forms with `csrf_token()`.
- GET requests now return `405 Method Not Allowed`.

**Files:** `routes/dashboard.py`, `routes/evaluation.py`, `routes/auth.py`,
`templates/base.html`, `templates/admin_dashboard.html`,
`templates/admin_reset_password.html`, `templates/evaluation_teacher.html`

**Verification:** All affected GET routes return `405`; POST still performs the
action (`tests/test_security.py`, `tests/test_dashboard.py`).

---

## 12. SEC-13/14 — Proxy, HTTPS, headers and sessions

**Problem:** The app ignored reverse-proxy headers, did not redirect to HTTPS or
set security headers, and used 30-day sessions with insecure-cookie defaults.

**Change:**
- `ProxyFix` is enabled only when `TRUST_PROXY_HEADERS=true` (default in
  production) so client-supplied `X-Forwarded-*` cannot spoof IP/scheme on a
  directly exposed server.
- `FORCE_HTTPS=true` (default in production) redirects GET/HEAD to HTTPS and
  rejects insecure POST bodies.
- Security headers: `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Permissions-Policy`, HSTS on HTTPS, and a
  `Content-Security-Policy-Report-Only` policy.
- Sessions last 12 hours; remember-me lasts 7 days;
  `SESSION_PROTECTION='strong'`; secure cookies default to production mode;
  `HttpOnly` and `SameSite=Lax` remain set.

**Files:** `app.py`, `config.py`, `extensions.py`

**Verification:** Headers, HTTPS redirect, session/cookie settings
(`tests/test_security.py`).

**Known limitation:** CSP is report-only because existing templates use inline
scripts and styles. Tightening it to enforced mode requires moving inline
handlers into static JS files.

---

## 13. SEC-15 — Authentication throttling

**Problem:** Login and forgot-password had only the global limiter, which was
too loose for credential stuffing and reset-request abuse.

**Change:**
- Login: `10 per minute` and `60 per hour` per remote address (POST only).
- Forgot-password: `5 per minute` and `20 per hour` per remote address
  (POST only).
- The limiter lives in `extensions.py` so blueprints can use it without a
  circular import; it uses the proxy-aware remote address.

**Files:** `extensions.py`, `routes/auth.py`, `app.py`

**Verification:** Rate limiting is disabled in the automated suite. Manual
verification: set `RATELIMIT_ENABLED=true` and submit the login form repeatedly;
the 11th attempt in a minute returns the `429` page.

**Remaining limitation:** there is no persistent account lockout. Set
`RATELIMIT_STORAGE_URI` to Redis in production so limits are shared across
workers; add a failed-login counter in Phase 1.

---

## 14. Test results

```text
python -m pytest -q
120 passed
```

The suite covers the original 79 tests plus 41 security regressions. Tests use
an isolated SQLite database, disable CSRF and rate limiting, and never touch the
development or production database.

Additional manual checks:
- Isolated production-style boot with `SEED_DEMO_DATA=False`: roles created,
  zero users.
- CLI bootstrap: `create-admin` created an approved Admin and printed no
  password or token.
- Repeated login POSTs with rate limiting enabled return `429`.

---

## 15. Remaining work (Phase 1)

- Central authorization policy instead of per-route role checks.
- Audit logging for approvals, grading, uploads and admin actions.
- Hash password-reset tokens and invalidate sessions on password change.
- Versioned Alembic migrations.
- Move uploads outside `static` and serve them through authenticated routes.
- Enforce CSP after removing inline scripts/styles.
- Persistent failed-login lockout and Redis-backed rate limiting.
- Host-header allowlist and trusted proxy configuration review.
- Multi-tenancy schema seams and parent role.
