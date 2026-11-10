# Shikshya LMS — Technical Assessment

**Date:** 2026-11-10
**Scope:** full repository audit (`app.py`, `config.py`, `models/`, `routes/`, `templates/`, `static/`, `tests/`, deployment files)
**Method:** static review + route/model tracing + existing test inventory. No exploitation was performed against production.
**Status:** Stage 1 of the modernization programme. No production code changed in this stage.

---

## 1. Executive summary

Shikshya is a working, feature-rich Flask LMS with 79 passing tests and a live deployment. The architecture is coherent and worth preserving: server-rendered Jinja pages, SQLAlchemy models, blueprints per domain, vanilla CSS/JS, CSRF protection, and role-based dashboards.

The audit also found **eight critical security defects**, several of which are exploitable by an unauthenticated or ordinary student user:

| ID | Issue | Impact |
|---|---|---|
| SEC-01 | Anyone can register as **Admin** by tampering the `role` form field | Full platform takeover |
| SEC-02 | Quiz submission accepts any `quiz_id` and returns the **correct answers** | Answer-key theft + fake attempts |
| SEC-03 | Password-reset links are echoed in the UI/logs when SMTP is unconfigured | Account takeover |
| SEC-04 | Teacher/lab HTML is rendered with `\|safe` and unsanitized Markdown | Stored XSS → session theft |
| SEC-05 | Lesson-document download is an authenticated **SSRF** proxy with no enrollment check | Internal network access + content leak |
| SEC-06 | Public `/branches/api/data` exposes every user's username, city, and GPS coordinates | Privacy breach |
| SEC-07 | Uploads allow `.html`/`.js` and are served from the app origin | Stored XSS / malware hosting |
| SEC-08 | Demo `admin/admin123` account is auto-seeded and documented publicly | Default-credential takeover |

**Recommendation:** pause feature work and ship the Phase 0 security batch first (§ roadmap). Everything else in the master brief (UI redesign, advanced assessments, multi-tenancy) builds on a platform that must first be safe to expose.

---

## 2. Architecture (as discovered)

```
Browser (Jinja HTML + vanilla JS)
   │  HTML forms (CSRF token)         fetch() JSON (X-CSRFToken)
   ▼
Flask 3 app factory  (app.py::create_app)
   ├─ Flask-Login        session auth, remember-me
   ├─ Flask-WTF          global CSRF on POST/PUT/PATCH/DELETE
   ├─ Flask-Limiter      global default 10/min per IP, memory://
   ├─ Flask-Migrate      installed but no migrations/ directory
   ├─ SQLAlchemy         SQLite (dev) / PostgreSQL (prod)
   ├─ Cloudinary         optional media uploads
   └─ WeasyPrint         PDF reports / certificates
   ▼
Blueprints: main, auth, dashboard, course, api, branch, notice, payment, lab, eval
   ▼
Templates: base.html + 4 role/page families, 4 CSS files, 4 JS files
```

**Deployment:** Docker → Gunicorn, `1` sync worker, `timeout 120`, health check on `/`. Render-compatible. No reverse-proxy awareness (`ProxyFix` missing).

**Configuration:** all secrets via environment (`SECRET_KEY` is mandatory). Good baseline. Gaps are in defaults, not in secret management.

---

## 3. Functional inventory

| Domain | Implemented | Notes |
|---|---|---|
| Auth | register, login, logout, profile, password change, admin-approved reset flow | No email verification, MFA, lockout, or session management UI |
| Roles | Admin, Teacher, Student | No Parent role; ad-hoc checks, no central policy |
| Courses | CRUD, categories, modules, lessons, publish, scheduling (`publish_at`), enrollment | Prerequisites, sections/classes, prerequisites absent |
| Learning | video/text/document lessons, resume seconds, progress %, bookmarks absent, notes localStorage-only | Progress formula mixes lessons/quizzes/submissions |
| Assessments | MCQ quizzes (timed, shuffled, attempt limit, instant score), evaluations (test paper/presentation/lab) with manual grading | Only MCQ is truly supported despite `question_type`; no question bank, rubrics, per-question randomization, or result scheduling |
| Assignments | single file/URL submission, late flag, manual grade + feedback | Overwrites previous submission; no history, rubric, or multiple files |
| Attendance | per-course daily attendance form + history | No monthly report export, no subject/class model |
| Communication | in-app notifications, notices, discussion threads | No email reminders, no scheduled jobs, no parent channel |
| Certificates | auto-issued at 100%, QR, public verification | Predictable code component; public page may over-share |
| Payments | manual eSewa/Khalti-style submission + admin approval, coupons, memberships | No gateway integration; float money; coupon race |
| Analytics | teacher per-lesson/per-quiz stats, admin totals, student gradebook | No charts beyond template markup; N+1 queries |
| AI | rule-based canned chatbot | Not an LLM; must be labelled or replaced modularly |
| Labs | CRUD labs + lab manuals with images/PDF | Uploads unvalidated |

---

## 4. Data model assessment

### 4.1 Strengths
- Clear entities with explicit FKs and mostly sane cascades.
- `LessonProgress.updated_at` and `video_progress_seconds` already support resume.
- `PasswordResetToken` has `expires_at` and `is_used`.
- Relationship backrefs keep templates readable.

### 4.2 Structural gaps

| Area | Finding | Consequence |
|---|---|---|
| Uniqueness | No unique constraints on `(student_id, course_id)` in `enrollments`, `(course_id, student_id)` in `reviews`, `(evaluation_id, student_id)` in `evaluation_submissions`, `(course_id, student_id, date)` in `attendance`, `(assignment_id, student_id)` in `submissions`, `(student_id, course_id)` in `certificates` | Duplicate enrollments/certificates; ambiguous progress |
| Indexes | FKs and hot filters unindexed (`notifications(user_id,is_read)`, `lesson_progress(enrollment_id)`, `quiz_attempts(quiz_id,student_id)`, `submissions(assignment_id,student_id)`, `payments(status)`, `discussion_topics(course_id)`, `attendance(course_id,date)`) | Slow dashboards and player as data grows |
| Money | `Float` for `Course.price`, `Payment.amount`, `discount_amount`, `Coupon.min_amount` | Rounding drift; unsafe for billing |
| Time | Naive `datetime.utcnow` everywhere, compared to local `datetime.now()` in course/evaluation scheduling | Off-by-hours bugs for Nepal (+05:45), DST, and "opens at" checks |
| Migrations | `Flask-Migrate` installed, **no `migrations/` directory**; startup performs raw `ALTER TABLE` in `app.py:126-181` | No versioned schema; multi-instance race; no rollback |
| Soft delete | Hard deletes plus a hand-written cascade list in `delete_user` | New tables are silently missed; audit trail lost |
| Attempts | `QuizAttempt` stores only score/pass, not answers | Cannot review past attempts, audit disputes, or compute question-level analytics |
| Submissions | One row overwritten on resubmit | Contradicts "submission history" requirement |
| Multi-tenant | No `institution_id` anywhere | Every query is global; SaaS isolation not possible without schema work |

---

## 5. Security assessment

> Severity: **Critical** = unauthenticated or low-privilege user can take over data/accounts or execute code. **High** = serious data exposure or privilege boundary failure. **Medium** = requires specific conditions or has limited blast radius.

### 5.1 Critical findings

#### SEC-01 — Admin self-registration (privilege escalation)
`routes/auth.py:19` allows `Admin` in `VALID_ROLES`; `routes/auth.py:32-58` trusts the posted `role` and sets `is_approved = role_name != 'Teacher'`, so an Admin account is created **already approved**. The template hides Admin from the dropdown (`templates/login.html:48-51`), but the server accepts it.

**Exploit:** `POST /register` with `role=Admin` → approved administrator.
**Impact:** full control of users, courses, payments, and data.
**Fix:** server-side allowlist `{Student, Teacher}` only; never accept `Admin` from public registration; create admins only via CLI/seed/admin action. Add a regression test.

#### SEC-02 — Quiz answer-key disclosure and attempt forgery (IDOR)
`routes/api.py:111-193`. `submit_quiz` loads the quiz by ID and scores it without verifying that the caller is enrolled in `quiz.course_id`. The JSON response includes `results[qid].correct_choice_text` for every question.

**Exploit:** any authenticated user posts `{"quiz_id": N, "answers": {}}` for any quiz N and receives the full answer key; attempts are persisted for courses they are not in.
**Impact:** assessment integrity destroyed; unauthorized writes.
**Fix:** require `Enrollment(student_id=current_user.id, course_id=quiz.course_id)` for students; deny teachers/admins from creating attempts; only return correctness + own selected choice (and correct answer per product policy) after an authorized attempt. Add tests for unenrolled and other-course access.

#### SEC-03 — Password-reset token leaked to the browser/logs
`routes/auth.py:274-279` and `314-321`: when SMTP is not configured (the default), the full reset link is `print()`ed and placed in a flash message. `forgot_password` (`auth.py:218-238`) also reveals whether an account exists.

**Exploit:** request a reset for any known email → read the link in the response/logs → set a new password.
**Impact:** account takeover, including Admin.
**Fix:** never surface tokens; log only a non-sensitive event. Return a generic response for forgot-password. Configure SMTP (or a free transactional tier) and, if unavailable, disable self-service reset rather than leaking. Hash reset tokens at rest and add a `used_at`/IP/UA audit record.

#### SEC-04 — Stored XSS through lesson/lab content
`templates/course_player.html:179,181,183,220,222,224`, `templates/lesson_print.html:30,32`, `templates/lab_detail.html:43` render teacher/admin HTML with `|safe`. The `markdown` filter (`app.py:66-70`) passes raw HTML through, and `process_lesson_headings` only rewrites headings. `bleach` is already in `requirements.txt` but unused.

**Exploit:** a Teacher writes `<img src=x onerror=fetch('/api/...')>` in a lesson → executes in every enrolled student's session, including an Admin previewing the course.
**Impact:** session theft, CSRF-token exfiltration, wormable content.
**Fix:** sanitize on write and on render with a strict `bleach` allowlist (headings, p, lists, tables, code, links with `rel="noopener noreferrer"`, no `style`, no `on*`, no `script/iframe/object`). Keep `|safe` only for sanitized output. Add XSS tests with a payload corpus.

#### SEC-05 — SSRF + missing authorization in lesson document download
`routes/api.py:504-536`. Any logged-in user can request `/api/lessons/<id>/download` for any lesson. If `document_url` starts with `http(s)`, the server fetches it with `requests.get` and returns the body.

**Exploit:** teacher sets `document_url=http://169.254.169.254/latest/meta-data/...` (or an internal admin URL) → student downloads internal data. Also an IDOR for paid-course documents.
**Impact:** internal network reconnaissance/exfiltration, paid-content bypass.
**Fix:** require enrollment (or teacher owner/admin); only permit URLs on an allowlist of trusted hosts (Cloudinary/`SITE_URL`/static); block private/link-local IPs after DNS resolution; stream with a size cap; never follow redirects to non-allowlisted hosts.

#### SEC-06 — Public exposure of user geolocation
`routes/branch.py:33-56` and the public branches map return every `UserProfile` with non-null coordinates, including `username`, `city`, `latitude`, `longitude`. No authentication.

**Impact:** privacy breach (home/work location inference), stalking risk, likely GDPR/privacy-law non-compliance.
**Fix:** remove user coordinates from public APIs; aggregate by city only if needed; require explicit opt-in and authenticated access for any precise location; delete precise coordinates that are not needed.

#### SEC-07 — Dangerous upload types served from the app origin
- `routes/api.py:457-466` allows `html`, `js`, `css`, `txt`, `py` and stores under `static/uploads/assignments/` which is publicly served.
- `routes/lab.py:39-47` and `81-87` save **any** extension with no allowlist under `static/uploads/labs/`.
- `utils/cloudinary_upload.py:26-34` builds a temp path from the raw client filename (path traversal) and silently returns `None` on failure.

**Exploit:** upload `payload.html` (or `.js`) and share `/static/uploads/...` → same-origin XSS; host malware; overwrite files via `../` in the cloudinary temp path.
**Impact:** stored XSS, malware distribution, storage abuse.
**Fix:** strict extension + MIME + magic-byte allowlists per feature; generate names server-side; store outside `static/` in `instance/uploads`; serve via authenticated `send_file` with `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`; use `secure_filename` in temp paths; cap size per type; add antivirus hook later if needed.

#### SEC-08 — Default admin credentials
`seed.py:52-59` creates `admin@shikshya.edu / admin123`, `teacher123`, `student123`; `README.md:73-79` publishes them; `app.py:182-184` runs the seeder automatically when the roles table is empty.

**Impact:** if a production database is ever initialized without a manual seed change, the platform is open.
**Fix:** make seeding development-only (`FLASK_ENV != production`), require `SEED_DEMO_DATA=true`, generate random passwords and print once, force password change on first login, and remove credentials from the README or label them dev-only. Rotate any existing production demo credentials.

### 5.2 High findings

#### SEC-09 — State-changing GET endpoints (CSRF)
`GET /dashboard/admin/approve-teacher/<id>`, `/approve-course/<id>`, `/approve-payment/<id>` (`routes/dashboard.py:285-364`), `GET /admin/approve-reset-request/<id>` (`routes/auth.py:286-322`), `GET /evaluations/<id>/publish|unpublish` (`routes/evaluation.py:264-286`), and `GET /logout`.

A crafted link/image on any page an admin visits can approve payments/courses or reset flows. The global CSRF protector only checks unsafe methods.
**Fix:** convert to `POST` with `csrf_token`, add confirmation UI, and make logout `POST` (or keep GET but document the low risk).

#### SEC-10 — Evaluation grading IDOR
`routes/evaluation.py:243-261`. The route validates that the teacher owns `evaluation.course`, then loads `EvaluationSubmission` by `submission_id` from the form without checking `sub.evaluation_id == eval_id`. A teacher can grade submissions from other courses; `score` is unvalidated (negative or above `max_score`).

**Fix:** load with `filter_by(id=sub_id, evaluation_id=eval_id)`, clamp `0 <= score <= max_score`, record `graded_by`, and audit.

#### SEC-11 — Discussion reply IDOR
`routes/api.py:273-306`. Any authenticated user can reply to any `topic_id`; there is no enrollment or course-owner check. This also sends notifications to arbitrary topic owners.

**Fix:** resolve the topic's course, require enrollment or teacher ownership, and rate-limit posting.

#### SEC-12 — Evaluation listing leaks other courses
`routes/evaluation.py:29-40`. A Student can call `/courses/<any_id>/evaluations` and list titles, schedules, and types for courses they are not enrolled in.
**Fix:** require enrollment for students.

#### SEC-13 — Session and transport hardening gaps
`config.py:49-58`: 30-day session and remember cookie; `SESSION_COOKIE_SECURE` defaults to false; no idle timeout; `REMEMBER_COOKIE_SECURE` unset; no `ProxyFix`, so `request.is_secure`/`remote_addr` are wrong behind Render; no HTTPS redirect.

**Fix:** production defaults for `Secure`, `HttpOnly`, `SameSite=Lax`; 12-hour session, 7-day remember; sliding idle expiry; `ProxyFix(x_protocol=1, x_host=1)`; HTTPS redirect outside debug; `SESSION_PROTECTION='strong'`.

#### SEC-14 — No security headers / CSP
No `after_request` sets `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`/`frame-ancestors`, `Referrer-Policy`, `Permissions-Policy`, or HSTS. Admin actions can be framed (clickjacking).

**Fix:** add a headers middleware with a CSP that starts report-only (the app uses inline styles/scripts, so a nonce or `'unsafe-inline'` transition is required), plus `nosniff`, `SAMEORIGIN`, `strict-origin-when-cross-origin`, HSTS in production.

#### SEC-15 — Brute force and account lockout
`routes/auth.py:87-127` has no per-account throttle or lockout; the global limiter allows 10 requests/minute per IP (shared across all routes) and uses `memory://` (per process). No audit of failed logins.

**Fix:** dedicated `@limiter.limit("5 per minute;20 per hour")` on login keyed by IP + email, exponential backoff or temporary lock after N failures, generic error text, audit entries, and Redis (or a DB-backed counter) for multi-worker correctness.

#### SEC-16 — Weak password and reset-token handling
Minimum length 6 (`auth.py:42,161,336`); no breached-password check; reset tokens stored in plaintext; 24-hour validity with no single-use enforcement beyond `is_used`; no session invalidation after password change.

**Fix:** 8–12 character minimum with a breach-list check (offline k-anonymity via HaveIBeenPwned is free) or a strength meter; hash tokens (store SHA-256) and compare hashes; invalidate other sessions on password change; shorten reset validity to 1 hour.

#### SEC-17 — No audit logging
There is no record of logins, failures, role changes, grade changes, payment approvals, deletions, or admin actions. Requirement 4 cannot be met today.

**Fix:** `AuditLog` table (`actor_id, action, target_type, target_id, ip, user_agent, metadata_json, created_at`) plus a small `audit()` helper; log auth events, authz denials, admin mutations, grade/result changes, and file uploads. Never log passwords/tokens. Add an admin viewer + retention policy.

#### SEC-18 — Inconsistent authorization style
Some routes `abort(403)`, others flash and redirect to home; `role_required` only redirects; several routes re-implement ownership checks. This inconsistency is how SEC-10/SEC-11 slipped in.

**Fix:** central `utils/authz.py` policy functions (`can_view_course`, `can_manage_course`, `can_grade`, `require_enrollment`) and a `@roles_required` decorator that returns 403. Refactor route-by-route with tests.

### 5.3 Medium findings
- `AUTO_INIT_DB` performs DDL on startup (`app.py:126-181`) with no migrations; schema drift and race risk.
- `app.py:45-46` `User.query.get(int(user_id))` raises 500 on a malformed session cookie.
- `download_lesson_doc` reads the entire response into memory (`resp.content`) — memory exhaustion.
- Certificate codes contain predictable course/student IDs plus 6 hex chars (`api.py:57`); public verification can be enumerated.
- `branches_api` and `certificate_verify` are unauthenticated by design but expose more than necessary.
- No `TRUSTED_HOSTS`; Host-header attacks possible if cache/proxy misconfigured.
- `contact` form fakes success (`main.py:39-46`) — nonfunctional feature, violates the "no placeholder" rule.
- AI chatbot is hardcoded (`api.py:196-237`) but presented as an AI assistant.

### 5.4 Verified good practices
- Parameterized SQLAlchemy queries throughout; no string-built SQL with user input → no SQLi found.
- Jinja autoescaping is on by default; `nl2br` escapes before adding `<br>`.
- Global CSRF on unsafe methods; `csrfFetch` sends `X-CSRFToken`.
- `generate_password_hash` (Werkzeug scrypt) and `check_password_hash` are correct.
- `SECRET_KEY` is required at import time; no hardcoded secret in code.
- File names for assignment uploads are generated, not user-controlled.
- Login does not disclose which factor was wrong.
- Ownership checks exist on most course/lesson/quiz teacher routes (the gaps are listed above).

---

## 6. Authorization matrix (current)

| Capability | Admin | Teacher (owner) | Teacher (other) | Student (enrolled) | Student (not enrolled) | Anonymous |
|---|---|---|---|---|---|---|
| View course catalog | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Edit course content | ✅ (via admin) | ✅ | ❌ | ❌ | ❌ | ❌ |
| View player | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ |
| Submit quiz | ⚠️ can create attempts | ⚠️ can create attempts | ⚠️ | ✅ | **❌ broken (SEC-02)** | ❌ |
| Download lesson doc | ✅ | ✅ | **❌ broken (SEC-05)** | ✅ | **❌ broken** | ❌ |
| Reply to discussion | ✅ | ✅ | **❌ broken (SEC-11)** | ✅ | **❌ broken** | ❌ |
| Grade submission | ❌ | ✅ own course | ❌ | ❌ | ❌ | ❌ |
| Grade evaluation | ❌ | ✅ own course | **❌ broken (SEC-10)** | ❌ | ❌ | ❌ |
| Approve payment/course | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| View user GPS | **public (SEC-06)** | public | public | public | public | **public** |

---

## 7. UX/UI assessment

A separate, detailed plan already exists at `docs/UX_UI_IMPROVEMENT_PLAN.md`. Summary of the highest-impact issues confirmed during this audit:

1. **Navigation:** duplicate header nav + role sidebar; two mobile menu systems; no skip link; no `aria-current`/`aria-expanded`.
2. **Player:** no prev/next lesson, tabs are JS-only with no URL state, module headers are mouse-only, no resume affordance.
3. **Progress:** the percentage mixes lessons, passed quizzes, and submissions but is never explained; certificate copy contradicts it.
4. **Assessments:** answers lost on refresh, `alert()`/`confirm()`, unanswered questions only discovered after submit, unescaped review HTML.
5. **Feedback:** no loading/error/retry states for fetch actions; flash/toast have no live region.
6. **Visual system:** 4 overlapping CSS files, extensive inline styles, hard-coded light-theme colors that break dark mode, mixed emoji/Font Awesome.
7. **Contrast:** white on `#10b981` 2.56:1, on `#f59e0b` 2.15:1, on `#ef4444` 3.76:1; `--text-light` 2.56:1 — all fail WCAG AA.
8. **Motion:** no `prefers-reduced-motion`; `transition: all`; infinite flame animation.
9. **Responsive:** 9-item player bottom nav; tables rely on horizontal scroll.

---

## 8. Performance and scalability

| Area | Finding | Impact |
|---|---|---|
| Progress writes | `_update_course_progress` runs 4+ aggregate queries on every 5-second video tick (`course_player.js:51`) | Write amplification; DB load scales with watch time |
| N+1 | Dashboard loops issue per-course/per-quiz queries (`dashboard.py:120-133`, `68-99`); `course.modules` and `enrollments` use `lazy=True` | Slow role dashboards |
| Pagination | Catalog, discussions, notices, payments, gradebook return unbounded lists | Memory/latency growth |
| Email | `notify_enrolled_students` sends SMTP synchronously in the request (`course.py:18-34`) | Course creation hangs with many students |
| PDF | WeasyPrint renders synchronously in-request (`api.py:399-430`) | CPU/memory spikes; blocks the single worker |
| Downloads | `resp.content` buffers whole files | Memory exhaustion on large media |
| Static assets | Fonts via CSS `@import`, full Font Awesome CDN, no compression config | Slow first render; poor mobile LCP |
| Concurrency | 1 sync Gunicorn worker | Any slow request blocks all users |
| Caching | None (no Redis, no fragment cache) | Repeated aggregate queries |
| DB indexes | Missing on hot FKs/filters | Linear scans as data grows |

---

## 9. Deployment and operations

**Working:** Docker multi-stage build, non-root-ish install, health check, env-based config, Postgres URL normalization with SSL, psycopg2/psycopg support, one-command Render deploy, documented troubleshooting.

**Gaps:**
- No `ProxyFix`; rate limits and secure-cookie logic see the proxy IP/scheme.
- No HTTPS redirect/HSTS; `SITE_URL` defaults to `http://localhost:5000`.
- No error monitoring (Sentry/OpenTelemetry), no structured JSON logs, no request IDs.
- Reset links and stack traces can reach logs (`print` in `auth.py`).
- No documented backup/restore drill; no retention policy.
- `AUTO_INIT_DB` DDL on boot; no migration history.
- Single worker; no queue for email/PDF.
- No CI pipeline (`.github/` absent); tests are local-only.
- `README.md` publishes default credentials.

---

## 10. Testing and QA

**Current:** 79 tests across `test_auth` (20), `test_api` (23), `test_dashboard` (13), `test_main` (7), `test_models` (5), `test_config` (1). Tests use an isolated SQLite DB and disable CSRF/rate limits.

**Coverage gaps:**
- No tests for evaluation, payment, lab, notice, branch, or file-upload routes.
- No authorization matrix tests (other-course teacher, unenrolled student, cross-tenant).
- No CSRF tests, header tests, rate-limit tests, or session tests.
- No tests for the critical findings above (SEC-01…SEC-11).
- No browser/E2E, responsive, or accessibility tests.
- No CI enforcement.

**Minimum bar for Phase 0:** each fixed vulnerability gets a failing-then-passing regression test.

---

## 11. Multi-tenancy readiness

**Current:** single implicit tenant. Every model query is global. There is no `Institution` entity, no per-tenant unique constraints, no branding/settings table, and no academic-year/class/section/subject model.

**Assessment:** converting directly is high-risk because unique keys (`users.email`, `courses.slug`, `categories.slug`) are global and the existing data must be assigned to a default institution.

**Recommended phased approach:**
1. **Prepare (safe):** add `institutions` table with one `default` row; add nullable `institution_id` to `users`, `courses`, `categories`, `branches`, `notices`, `labs`, `payments`, `membership_plans`, `settings`; backfill the default; add scoped indexes. No behavior change.
2. **Scope (behavioral):** request-level tenant resolution (host/subdomain or user membership), `before_request` guard, query scoping in a repository/service layer, composite unique constraints per tenant, and isolation tests.
3. **Productize:** institution settings/branding, academic year, classes/sections/subjects, per-tenant grading schemes, admin roles scoped per institution, billing separation.

**Do not start Phase 2 until Phase 0/1 security and migrations are complete.** Multi-tenancy multiplies the impact of every authorization bug.

**Parent role:** not modeled. Adding it requires `ParentStudentLink(parent_id, student_id, relationship, verified_at)` and a strict read-only policy; treat as a Phase 4 feature, not a schema afterthought.

---

## 12. Feature gap analysis vs the master brief

| Requested | Status | Note |
|---|---|---|
| Course prerequisites / scheduling | Partial | `publish_at` exists; no prerequisites, cohorts, or class sections |
| Assignment rubric / history / late policy | Missing | Single overwritten submission, no rubric model |
| Question types (multi-select, T/F, short/long, matching, fill-blank) | Missing | Only first correct choice is scored; `question_type` is stored but unused |
| Question bank / categories / difficulty / per-question randomization | Missing | Global shuffle only |
| Exam scheduling / result publishing (quizzes) | Partial | Evaluations have schedules/publish; quizzes publish instantly |
| Question-level analytics | Partial | Per-quiz stats only; no per-question breakdown |
| Attendance reports/monthly summaries | Partial | Form + history; no exports/aggregates |
| Parent portal | Missing | No role/link model |
| Email reminders / scheduled jobs | Missing | No scheduler/queue |
| Audit logging | Missing | No model |
| MFA / email verification | Missing | Needs `pyotp` + SMTP (free) |
| Real AI features | Missing | Current chat is `if/else`; needs provider adapter + privacy controls |
| Multi-institution SaaS | Missing | See §11 |
| Backups/restore verification | Undocumented | Operational task |
| CI/CD + security scans | Missing | No `.github/` |

---

## 13. Risk register

| Risk | Likelihood | Impact | Priority |
|---|---|---|---|
| Admin account created by attacker (SEC-01) | High | Catastrophic | P0 |
| Answer keys harvested (SEC-02) | High | High | P0 |
| Password reset takeover (SEC-03) | High (SMTP unset) | Catastrophic | P0 |
| Stored XSS via lesson (SEC-04) | Medium | High | P0 |
| SSRF via document URL (SEC-05) | Medium | High | P0 |
| GPS leak (SEC-06) | Certain | High (legal) | P0 |
| HTML upload XSS (SEC-07) | Medium | High | P0 |
| Default admin creds (SEC-08) | Medium | Catastrophic | P0 |
| CSRF via GET admin actions (SEC-09) | Medium | High | P1 |
| Grading/reply IDOR (SEC-10/11) | Medium | Medium | P1 |
| No audit trail (SEC-17) | Certain | Medium (compliance) | P1 |
| Schema drift from startup DDL | Medium | High | P1 |
| N+1/slow dashboards at scale | High | Medium | P2 |
| Single worker outage under load | Medium | High | P2 |

---

## 14. Conclusion

The product surface is strong for a project of this size, and the stack is appropriate. The platform is **not yet safe to market as multi-institution SaaS** until the Phase 0 issues are closed. The correct order is:

1. Close the eight critical defects and add regression tests.
2. Centralize authorization and add audit logging.
3. Add versioned migrations and data-integrity constraints.
4. Modernize UX on a stable, tested base.
5. Add advanced assessment/attendance/communication features.
6. Only then introduce tenancy, parent accounts, and AI providers.

The accompanying `docs/IMPLEMENTATION_ROADMAP.md` turns this into sequenced, verifiable work.
