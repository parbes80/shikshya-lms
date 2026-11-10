# Shikshya LMS — Security Remediation Log

**Sprint:** Phase 0, Sprint 1
**Date:** 2026-11-10
**Companion documents:** `docs/TECHNICAL_ASSESSMENT.md`, `docs/IMPLEMENTATION_ROADMAP.md`
**Status:** Implemented and verified locally; not yet deployed to staging.

---

## 1. Scope

This sprint addressed the highest-impact findings that could be fixed without a
schema migration:

| Finding | Status | Regression tests |
|---|---|---|
| SEC-01 — Admin self-registration | Fixed | `tests/test_auth.py` |
| SEC-02 — Quiz IDOR + answer-key disclosure | Fixed | `tests/test_api.py` |
| SEC-03 — Password-reset token leakage + enumeration | Fixed | `tests/test_auth.py` |
| SEC-06 — Public exposure of user locations | Fixed | `tests/test_branch.py` |
| SEC-08 — Default demo credentials auto-seeded | Fixed | `tests/test_seed.py` |
| SEC-10 — Evaluation grading IDOR + unclamped scores | Fixed | `tests/test_evaluation.py` |
| SEC-11 — Discussion reply IDOR | Fixed | `tests/test_api.py` |
| SEC-12 — Evaluation listing leak | Fixed | `tests/test_evaluation.py` |

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

## 8. Test results

```text
python -m pytest -q
98 passed
```

The suite covers the original 79 tests plus 19 new security regressions. Tests
use an isolated SQLite database, disable CSRF and rate limiting, and never touch
the development or production database.

Additional manual checks:
- Isolated production-style boot with `SEED_DEMO_DATA=False`: roles created,
  zero users.
- CLI bootstrap: `create-admin` created an approved Admin and printed no
  password or token.

---

## 9. Next sprint (not part of this change set)

Sprint 2 remains:
- SEC-04 rich-content sanitization (`bleach`).
- SEC-05 lesson-document SSRF/IDOR hardening.
- SEC-07 upload type/storage/serving hardening.
- SEC-09 state-changing GET → POST + CSRF.
- SEC-13/14 session, proxy, HTTPS, and security headers.
- SEC-15 auth throttling and lockout.

Phase 1 then starts with a central authorization policy, audit logging, and
versioned Alembic migrations.
