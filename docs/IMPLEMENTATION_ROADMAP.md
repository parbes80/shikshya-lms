# Shikshya LMS — Implementation Roadmap

**Companion to:** `docs/TECHNICAL_ASSESSMENT.md`
**Rule:** each phase must pass its verification gate before the next begins. No phase deletes working functionality.

---

## 0. Planning principles

1. **Security before surface.** No UI polish or new features while an unauthenticated user can become Admin.
2. **Server-side truth.** Every permission is enforced in a route/service, never only in a template.
3. **One migration path.** Replace startup DDL with Alembic; every schema change is reversible.
4. **Preserve the stack.** Flask + Jinja + vanilla JS stays. Add libraries only when they remove real risk (`bleach`, `pyotp`, `pytest-playwright` for tests).
5. **Measurable acceptance.** Every task has a test or a manual check that can fail.
6. **Small batches.** One domain per PR; run the full suite; no mixed security + feature PRs.

---

## 1. Priority matrix

| ID | Workstream | Priority | Effort | Depends on |
|---|---|---|---|---|
| P0-01 | Block Admin self-registration | Critical | S | — |
| P0-02 | Quiz authorization + answer-key protection | Critical | S | — |
| P0-03 | Stop password-reset token leakage + enumeration | Critical | S | SMTP decision |
| P0-04 | Sanitize lesson/lab HTML (bleach) | Critical | M | — |
| P0-05 | Harden lesson-doc download (SSRF + IDOR) | Critical | M | — |
| P0-06 | Remove public GPS/user leak | Critical | S | — |
| P0-07 | Upload hardening (types, storage, serving) | Critical | M | — |
| P0-08 | Remove default production credentials | Critical | S | Deploy access |
| P0-09 | Convert state-changing GET to POST + CSRF | High | M | — |
| P0-10 | Fix grading/reply/listing IDORs | High | S | — |
| P0-11 | Security headers, cookies, ProxyFix, HTTPS | High | M | — |
| P0-12 | Login throttling + generic auth errors | High | M | — |
| P1-01 | Central authorization policy layer | High | L | P0 |
| P1-02 | Audit log + admin viewer | High | M | — |
| P1-03 | Password policy + token hashing + session invalidation | High | M | — |
| P1-04 | Email verification + optional TOTP MFA | High | L | SMTP |
| P1-05 | Versioned migrations + data constraints/indexes | High | L | backup |
| P1-06 | Error handling + logging + monitoring | Medium | M | — |
| P1-07 | File serving via authenticated route | High | M | P0-07 |
| P2-01 | Query optimization + pagination + caching | Medium | L | P1-05 |
| P2-02 | Background jobs for email/PDF | Medium | M | — |
| P2-03 | Asset/performance optimization | Medium | M | — |
| P2-04 | CI + security scanning + accessibility checks | High | M | — |
| P3-01.. | UX/UI modernization (see UX plan) | High | XL | P0/P1 |
| P4-01.. | Advanced LMS features | Medium | XL | P3 |
| P5-01.. | Multi-tenancy | Future | XL | P4 |

Effort: S ≤ 1 day, M 2–4 days, L 1–2 weeks, XL multi-sprint.

---

## 2. Phase 0 — Emergency security (target: 1–2 weeks)

**Goal:** an ordinary user can no longer escalate privilege, steal answers, take over accounts, execute script, reach internal services, or read other people's locations.

### P0-01 — Block Admin self-registration
- **Change:** in `routes/auth.py`, restrict public registration to `{Student, Teacher}`; reject anything else with 400; keep Admin creation to CLI/seed only. Add a `User.is_admin`-style guard is not needed; role lookup is enough.
- **Files:** `routes/auth.py`, `tests/test_auth.py`.
- **Acceptance:** `POST /register` with `role=Admin` creates no user and returns a validation error; Student/Teacher still work.
- **Security test:** assert no Admin row exists after the attempt.

### P0-02 — Quiz authorization and answer-key protection
- **Change:** in `routes/api.py::submit_quiz`, load the quiz, resolve the enrollment, require `Enrollment(student_id=current_user.id, course_id=quiz.course_id)`; reject teachers/admins from creating attempts. Enforce the lesson gate and max attempts **before** scoring. Return `is_correct` and the student's selected choice; return `correct_choice_text` only if the course policy allows post-submission review (default: yes after submit, but only to an enrolled student).
- **Files:** `routes/api.py`, `tests/test_api.py`.
- **Acceptance:** unenrolled and other-course submissions return 403; no `QuizAttempt` row is created; an enrolled student still gets results.
- **Note:** also fix the same check in `take_quiz_view` to cover admins consistently.

### P0-03 — Password reset without leakage
- **Change:** `routes/auth.py`: always return the same generic message for forgot-password; never `print()` or flash the link. If mail is unconfigured, log a warning and disable the flow (or surface an admin-only notice). Store only a SHA-256 hash of the token; compare hashes. Reduce validity to 1 hour. Invalidate sessions on password change (see P1-03).
- **Files:** `routes/auth.py`, `models/interaction.py`, `utils/mail.py`, `templates/forgot_password.html`.
- **Acceptance:** response body/logs contain no token; unknown and known emails produce identical output; a used/expired token fails.
- **Decision needed:** configure SMTP or a free transactional provider before enabling self-service reset in production.

### P0-04 — Sanitize rich content
- **Change:** add `utils/sanitize.py` with a `bleach.clean` allowlist (`p, br, h1-h4, ul, ol, li, strong, em, code, pre, blockquote, table, thead, tbody, tr, th, td, a[href|title|rel], img[src|alt]`) and URL schemes `http, https, mailto`. Apply it:
  - when saving `Lesson.text_content`, `Lab.content`, `LabManual` fields;
  - in the `markdown` filter and `process_lesson_headings` output;
  - to `lesson_content_html` before `|safe`.
- **Files:** `utils/sanitize.py` (new), `routes/course.py`, `routes/lab.py`, `app.py`, templates.
- **Acceptance:** `<script>`, `onerror=`, `javascript:` URLs, `iframe`, `style` are removed; legitimate formatting survives. Add a payload corpus test.

### P0-05 — Lesson-document download
- **Change:** require enrollment for students (owner teacher/admin allowed). Allow only `SITE_URL`, Cloudinary hosts, and local `uploads/` paths; block redirects and private/link-local IPs; stream with a size cap instead of `resp.content`. Prefer signed Cloudinary URLs, which already exist in `utils/cloudinary_upload.py`.
- **Files:** `routes/api.py`, `utils/cloudinary_upload.py`, tests.
- **Acceptance:** unenrolled user gets 403; `http://169.254.169.254/...` is rejected; a legitimate Cloudinary/static document downloads.

### P0-06 — Remove public geolocation exposure
- **Change:** delete user coordinates from `/branches/api/data` and the public map; return only branch data. If a learner directory is a product requirement, make it authenticated, opt-in, city-level, and role-scoped.
- **Files:** `routes/branch.py`, `templates/branches_map.html`, `templates/branches_list.html`.
- **Acceptance:** the public JSON contains no `username`, `lat`, or `lng`; the map still renders branches.

### P0-07 — Upload hardening
- **Change:** per-feature allowlists and magic-byte checks; generate names; store under `instance/uploads/` (never `static/`); serve via an authenticated `send_file` route with `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`; reject `html, svg, js, php, exe`; use `secure_filename` in Cloudinary temp paths. Add per-type size limits (e.g. 10 MB docs, 200 MB video if applicable).
- **Files:** `utils/uploads.py` (new), `routes/api.py`, `routes/lab.py`, `routes/evaluation.py`, `utils/cloudinary_upload.py`, templates that link to files.
- **Acceptance:** `.html` upload is rejected; a stored file is not reachable at `/static/...`; downloads require the correct role/enrollment.

### P0-08 — Default credentials
- **Change:** gate seeding behind `FLASK_ENV != production` **and** `SEED_DEMO_DATA=true`; generate random passwords or require env-provided ones; force a password change flag on first login; remove/relabel credentials in `README.md`; rotate any live demo accounts.
- **Files:** `seed.py`, `app.py`, `README.md`, `.env.example`, `config.py`.
- **Acceptance:** a production boot with an empty DB creates no Admin with a known password; the app still boots; tests use explicit fixtures.

### P0-09 — CSRF on state changes
- **Change:** convert approvals/publish/unpublish to `POST`, add `csrf_token()` forms and confirmation dialogs; make logout `POST` (or a form button). Update links in dashboards to forms.
- **Files:** `routes/dashboard.py`, `routes/auth.py`, `routes/evaluation.py`, templates.
- **Acceptance:** GET on those routes returns 405; POST without a token returns 400; the UI still works.

### P0-10 — Remaining IDORs
- **Change:** evaluation grade (`filter_by(id=sub_id, evaluation_id=eval_id)`, clamp score), discussion reply (course enrollment/ownership), evaluation index (student enrollment).
- **Files:** `routes/evaluation.py`, `routes/api.py`, tests.

### P0-11 — Transport/session/headers
- **Change:** add `ProxyFix`; `SESSION_COOKIE_SECURE=True` in production; `REMEMBER_COOKIE_SECURE`; session lifetime 12h, remember 7d; `SESSION_PROTECTION='strong'`; HTTPS redirect; `after_request` with CSP (report-only first), `X-Content-Type-Options`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy`, `Permissions-Policy`, HSTS in production.
- **Files:** `app.py`, `config.py`.
- **Acceptance:** headers present on `/`, `/login`, `/dashboard/*`; no CSP violations in the browser console on 6 key pages; cookies carry `Secure` in production.

### P0-12 — Auth throttling
- **Change:** `@limiter.limit("5 per minute;20 per hour", key_func=ip+email)` on login and forgot-password; generic errors; temporary lock after 5 failures in 15 minutes; audit each failure.
- **Files:** `routes/auth.py`, `app.py`, tests.
- **Acceptance:** the 6th rapid attempt returns 429; a valid login after the window succeeds; no account enumeration.

### Phase 0 gate
- [ ] All new security tests pass; existing 79 still pass.
- [ ] Manual exploit checks documented and fail (admin registration, quiz harvest, reset leak, SSRF, GPS, HTML upload).
- [ ] No secrets or tokens in logs.
- [ ] Deployed to staging and re-tested.

---

## 3. Phase 1 — Auth, authorization, audit, data integrity (2–3 weeks)

### P1-01 — Central authorization layer
Create `utils/authz.py`:
```python
def is_enrolled(user, course) -> bool
def can_view_course(user, course) -> bool      # enrolled | owner teacher | admin
def can_manage_course(user, course) -> bool    # owner teacher | admin
def can_grade(user, course) -> bool
def require_enrollment(...)                    # raises 403
```
Add `@roles_required('Admin')` returning 403 (not redirect). Refactor all blueprints to call these helpers. Add an authorization matrix test that iterates roles × resources.

### P1-02 — Audit logging
`AuditLog` model + `audit(action, target_type, target_id, metadata)` helper. Log: login success/failure, logout, registration, password reset request/completion, role changes, user create/delete, course publish/unpublish, grade/result changes, payment approvals, file uploads, admin deletions. Add an admin filterable viewer with pagination and export. Redact secrets. Retention: 180 days default, configurable.

### P1-03 — Password/session hardening
- Minimum 8–12 chars; strength meter; optional HaveIBeenPwned k-anonymity check (free, no key).
- Hash reset tokens (SHA-256) and enforce single use + 1-hour expiry.
- On password change: rotate the session, invalidate remember tokens, notify by email.
- Add "active sessions" is a later enhancement; start with global logout-all.

### P1-04 — Email verification + optional MFA
- `EmailVerificationToken` model; verify on registration for Students, on approval for Teachers.
- `pyotp` TOTP with QR generated by the existing `qrcode` dependency; recovery codes hashed.
- MFA optional, enforced for Admin.
- Free SMTP alternatives: Gmail app password, Brevo/SendGrid free tier, or Amazon SES sandbox. Document the choice.

### P1-05 — Migrations and data integrity
- Initialise `migrations/`; generate a baseline from the current models; remove `AUTO_INIT_DB` DDL from `create_app`.
- Add unique constraints: `enrollments(student_id, course_id)`, `reviews(course_id, student_id)`, `evaluation_submissions(evaluation_id, student_id)`, `attendance(course_id, student_id, date)`, `certificates(student_id, course_id)`; decide on `submissions` history first (see P4).
- Add indexes: `notifications(user_id, is_read)`, `lesson_progress(enrollment_id, lesson_id)`, `quiz_attempts(quiz_id, student_id)`, `submissions(assignment_id, student_id)`, `payments(status)`, `discussion_topics(course_id)`, `attendance(course_id, date)`.
- Money → `Numeric(10,2)`; migrate values.
- Standardise timestamps to timezone-aware UTC; convert display at the edge.
- **Gate:** backup → migrate → verify row counts → rollback drill on staging.

### P1-06 — Error handling and observability
- Global handlers for 400/403/404/429/500 that log a request ID and never expose stack traces.
- Structured logging with secret redaction; request duration; slow-query logging.
- Optional free monitoring: Sentry free tier or a `/healthz` + uptime monitor.
- Add `/healthz` (DB check) and `/readyz`.

### P1-07 — Authenticated file serving
Route `/files/<kind>/<name>` validating ownership/enrollment and streaming from `instance/uploads` with `send_file` and safe headers. Update all templates and Cloudinary fallbacks.

### Phase 1 gate
- [ ] Authorization matrix tests cover every blueprint.
- [ ] Audit log records the 20 required event types; no secrets.
- [ ] Migration up/down verified on a copy of production data.
- [ ] MFA optional, Admin-enforced; email verification works with a real SMTP sandbox.

---

## 4. Phase 2 — Performance and scalability (2–3 weeks)

| Task | Change | Verification |
|---|---|---|
| P2-01a | Eager-load dashboard relations (`selectinload`/`joinedload`); replace per-course loops with aggregate queries | Query count per dashboard < 15; response < 300 ms on seeded data |
| P2-01b | Paginate catalog, discussions, notices, payments, gradebook (20/page); add `?page=` | No unbounded list endpoints |
| P2-01c | Cache home stats + role dashboard counters for 60 s (Flask-Caching simple cache, or a small `cache` table) | Hit ratio and TTL behavior |
| P2-02 | Move email and PDF generation to a DB-backed job queue processed by a worker thread or Render cron | Course creation returns < 1 s with 500 students |
| P2-03 | Replace font `@import` with preconnect + `display=swap`; subset/self-host Font Awesome; defer JS; lazy-load images; enable gzip/brotli | Lighthouse mobile LCP < 2.5 s, CLS < 0.1 |
| P2-04 | CI: pytest + ruff + `pip-audit` + axe/pa11y on 6 URLs; block merges on failure | Green pipeline on PR |
| P2-05 | Add `?sort=` and indexed search to catalog; full-text later if needed | p95 < 300 ms at 10k courses |

**Note:** increasing Gunicorn workers is a deployment decision tied to RAM. With 512 MB, keep 1–2 workers and move slow work off-request rather than scaling blindly.

---

## 5. Phase 3 - UI/UX modernization (4-6 weeks)

**Status:** design-system foundation, public homepage refresh, student/teacher/admin
dashboard refresh, searchable catalogue, richer course-detail page and player
navigation implemented (`docs/UI_MODERNIZATION_LOG.md`). Remaining Phase 3 work:
server-synced notes, bookmarks, styleguide route and full WCAG gate.

Execute `docs/UX_UI_IMPROVEMENT_PLAN.md` in this order:

1. **P0 UX** — accessible shell (skip link, landmarks, `aria-current`, focus management, single mobile menu), contrast tokens, resume-where-left-off, player navigation (prev/next, URL tabs, keyboard modules), quiz recovery.
2. **P1 UX** — catalog as a search tool, course-details curriculum + sticky CTA, explainable progress, server-synced notes, bookmarks, instructor authoring workflow.
3. **P2 UX** — completion celebrations, motion system with `prefers-reduced-motion`, state kit, asset performance, visual consistency + styleguide.

**Design system deliverables:** `static/css/tokens.css`, `components.css` namespaced, `docs/ui-components.md`, dev-only `/styleguide`.

**Gate:** WCAG 2.1 AA checks (axe zero serious issues, keyboard paths, 200% zoom, both themes); usability tests (5 learners, 3 instructors) at target success rates.

---

## 6. Phase 4 — Feature depth (6–10 weeks)

### 4A. Assessments
- `QuestionBank`, `QuestionCategory`, `Question.difficulty`, `Question.explanation`.
- Types: multiple-select (`QuestionChoiceMap`), true/false, short answer (accepted answers/normalization), long answer (manual), matching pairs, fill-in-the-blank.
- Per-quiz randomization flags, question pools, per-question points.
- `QuizAttemptAnswer` (attempt_id, question_id, answer_json, is_correct, points_awarded) → enables review, disputes, question-level analytics.
- Quiz scheduling (`opens_at`, `closes_at`), result publishing (`results_published`), manual grading queue for long answers.
- **Security:** answers never sent to the client before submission; server-side scoring; attempt ownership checks; audit every grade override.

### 4B. Assignments
- `SubmissionVersion` history, multiple files (`SubmissionFile`), rubric + criteria + levels, late policy (penalty/closed), resubmission rules, annotations.
- Bulk download and CSV export for teachers.

**Implemented in this increment:** per-assignment `allow_late_submission` policy,
late flags on submissions, text-only responses (`Submission.text_content`),
server-side numeric validation and score clamping on grading, and teacher/student
surfaces for written responses and late indicators. Rubrics, version history,
multi-file uploads and exports remain.

### 4C. Attendance
- Class/section/subject model, monthly matrix, CSV/PDF export, absence notifications, teacher attendance if required.

### 4D. Analytics
- Student: progress trend, time-on-task, quiz mastery by topic.
- Teacher: completion funnel, stuck learners (drill-down from `teacher_analytics`), question difficulty, grading SLA.
- Admin: enrollment, revenue, completion, engagement; exportable.
- Use a lightweight chart library (Chart.js, free) or server-rendered SVG; no heavy dashboard framework.

### 4E. Communication
- Scheduled reminders (assignment due, exam opens, inactivity) via the job queue.
- Email templates + preferences; digest option.
- Teacher ↔ student messaging scoped to enrolled courses; moderation/reporting.
- Parent portal only after `ParentStudentLink` + consent model exists.

### 4F. Certificates
- Template model (HTML/CSS variants), institution branding, revocation, verification rate limiting, unpredictable codes (UUID4 or HMAC), audit issuance.

### 4G. AI (modular, opt-in)
- `AIProvider` interface with a `NullProvider` (current canned behavior, clearly labelled "Study Assistant") and an adapter for a low-cost provider.
- Features: summarize lesson, generate draft quiz from teacher-uploaded material, draft feedback (teacher must approve), recommendations from progress data.
- **Privacy:** no student PII sent without consent; redact names/emails; per-institution opt-in; log prompts/responses for audit; never auto-publish AI grades.

---

## 7. Phase 5 — Multi-institution SaaS (future)

1. **Schema seams (safe):** `Institution` + nullable `institution_id` on tenant-owned tables + default row + backfill; no behavior change.
2. **Scoping:** tenant resolution (subdomain/custom domain or membership), `before_request` guard, composite unique keys, repository scoping, and a mandatory isolation test suite (every query filtered by tenant).
3. **Settings:** name/logo/colors, academic year, classes/sections/subjects, grading scheme, calendar, per-tenant roles.
4. **Operations:** per-tenant backups/export, data retention, billing separation, admin impersonation with audit.
5. **Migration:** assign existing rows to the default institution; run dual-read verification; only then enable a second tenant in staging.

**Do not begin Phase 5 with unresolved Phase 0/1 findings.** Tenancy amplifies authorization mistakes.

---

## 8. Cross-cutting engineering standards

### 8.1 Definition of done (every task)
- [ ] Server-side authorization for every new route.
- [ ] Input validation and output encoding.
- [ ] CSRF on unsafe methods; POST for state changes.
- [ ] Audit event for sensitive mutations.
- [ ] Tests: happy path, unauthorized, invalid input, regression.
- [ ] No new inline secrets, no `print()` of sensitive data.
- [ ] Responsive + keyboard + contrast check.
- [ ] Docs updated.

### 8.2 Security checklist (OWASP ASVS Level 1 target)
- Auth: lockout, MFA for Admin, reset token hashing, session timeout, secure cookies.
- Access control: central policy, deny-by-default, ownership checks, 403 not redirect.
- Input/output: allowlist validation, Jinja escaping, bleach for rich text, no `innerHTML` with user data.
- Files: allowlist, magic bytes, private storage, authenticated serving, size limits.
- Transport: HTTPS, HSTS, secure cookies, ProxyFix, trusted hosts.
- Headers: CSP, nosniff, frame-ancestors, referrer policy.
- Data: least privilege DB user, encrypted connection, backups, retention.
- Logging: audit trail, no secrets, alerting on repeated failures.

### 8.3 Testing pyramid
- Unit: policy helpers, sanitizers, scoring, validators.
- Integration: route × role matrix, CSRF, file upload, migrations.
- E2E (Playwright): 11 core workflows from the brief + 3 abuse cases (admin registration, cross-course quiz, cross-course grading).
- Accessibility: axe on 6 URLs; keyboard scripts.
- Security: `pip-audit`, `bandit`, header assertions, payload corpus for XSS/SSRF.

### 8.4 Deployment checklist
- [ ] `SECRET_KEY`, `DATABASE_URL`, `SITE_URL`, `SESSION_COOKIE_SECURE=True`, `FLASK_ENV=production`.
- [ ] `SEED_DEMO_DATA=false`.
- [ ] SMTP configured and verified.
- [ ] `ProxyFix` enabled; HTTPS redirect on.
- [ ] `/healthz` monitored; logs shipped; alert on 5xx and auth failures.
- [ ] Backup taken before migration; restore tested.
- [ ] Rollback image/tag recorded.

---

## 9. Decisions required from the product owner

1. **Email provider:** configure SMTP now, or disable self-service password reset until it exists? (Blocks P0-03/P1-04.)
2. **Admin bootstrap:** keep seed-generated admins only in development, and create production admins via a CLI command? (Recommended.)
3. **Demo data in production:** remove or keep behind an explicit flag? (Recommended: remove.)
4. **Parent role:** required for v1 SaaS, or defer to Phase 4? (Affects data model.)
5. **Multi-tenancy:** commit to a target date, or prepare schema seams now and defer scoping? (Recommended: seams now, scoping after Phase 2.)
6. **AI:** keep the current rule-based assistant labelled honestly, or budget a provider + privacy review? (Recommended: label now, integrate in Phase 4.)
7. **Payments:** stay manual, or integrate eSewa/Khalti later? (Affects money type and audit.)
8. **File storage:** Cloudinary-only, or local `instance/uploads` with authenticated serving? (Recommended: Cloudinary when configured, local fallback hardened.)

---

## 10. Suggested first two sprints

### Sprint 1 (security-critical)
P0-01, P0-02, P0-03, P0-06, P0-08, P0-10 + regression tests + deploy to staging.
**Status:** implemented and verified locally (`docs/SECURITY_REMEDIATION.md`, 98 tests at the time).

### Sprint 2 (security-hardening)
P0-04, P0-05, P0-07, P0-09, P0-11, P0-12 + header/upload/CSRF tests + staging verification + Phase 0 gate.
**Status:** implemented and verified locally (`docs/SECURITY_REMEDIATION.md`, 120 tests). Staging deployment and the Phase 0 gate review remain.

Only after the Phase 0 gate: start P1-01 (authorization layer) and P1-05 (migrations) in parallel with the first UX shell work.

---

## 11. Explicit non-goals (for now)

- No framework migration (React/Next/Django). The stack is adequate and the risk/benefit is negative.
- No Kubernetes/microservices. One container + managed Postgres is correct at this stage.
- No paid SaaS dependencies (Sentry/Redis) as hard requirements; use free tiers or DB-backed equivalents.
- No full visual rebrand before security and accessibility are stable.
- No multi-tenant scoping before Phase 0/1 and migrations.
- No AI grade automation without teacher approval and privacy controls.
