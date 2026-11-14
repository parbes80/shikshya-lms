# Shikshya LMS — UI/UX Modernization Log

**Phase:** 2 (design system), first Phase 3 slice (public homepage) and Phase 4 (dashboards)
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

---

## 6. Phase 4 — dashboard refresh

**Status:** implemented in the working tree (see commit that follows this log).

### 6.1 Route data

`routes/dashboard.py` now supplies real, role-scoped context without changing
existing behaviour:

- **Student** — `continue_enrollment`, `next_lesson`, `upcoming_assignments`,
  `upcoming_evaluations`, `announcements`, `recommended_courses` and
  `pending_submissions_count`. Upcoming work is limited to the student's own
  enrolled courses and excludes items already submitted.
- **Teacher** — `pending_submissions_count`, `published_courses_count`,
  `upcoming_evaluations`, `upcoming_live_classes`, `recent_submissions`,
  `recent_activity`, `attendance_stats`, `total_assignments`, `total_quizzes`
  and `course_stats`. Everything is filtered to courses owned by the teacher.
- **Admin** — role counts, total enrollments, total certificates, published
  course count, active users in the last 7 days, pending counts, recent notices
  and a server-side `q` search over name, username and email. Pagination keeps
  the search term.

All values come from the database. No mock or invented dashboard data was
added.

### 6.2 Student dashboard

`templates/student_dashboard.html` now has:

- A four-card snapshot (enrolled, completed, awaiting feedback, certificates).
- A **Continue learning** card that resumes the most recently updated lesson
  and links directly to the next unfinished lesson.
- **Upcoming assignments** and **upcoming evaluations** with meaningful empty
  states.
- Recent announcements, enrolled courses with progress, pending payments,
  submission history with feedback, badges, attendance, certificates, quiz
  results and recommended courses.
- Empty states for every section when the student has no data.

### 6.3 Teacher dashboard

`templates/teacher_dashboard.html` now has:

- A four-card snapshot (assigned, published, enrolled, submissions to grade).
- Quick actions for creating a course, publishing an announcement, reviewing
  submissions and jumping to curriculum management.
- **Upcoming evaluations** and **upcoming live classes** with safe external
  meeting links via `safe_url`.
- **Course completion statistics** table with enrollment, completion and
  average progress per course.
- **Attendance overview** and **recent student submissions**.
- The existing curriculum builder, quiz list, assignment list, enrolled-student
  table, quiz-attempt table and grading form are preserved.

### 6.4 Admin dashboard

`templates/admin_dashboard.html` now has:

- Eight snapshot metrics: total users, students, teachers, published/total
  courses, enrollments, active users (7 days), certificates and recorded
  revenue.
- A **Platform health** card with pending approvals/payments and role counts.
- Recent announcements and recent registrations.
- A **Management** grid that links only to existing screens. Institution
  management, role/permission editing, system settings, security monitoring
  and cross-platform analytics are explicitly labelled as planned and are not
  linked.
- A server-side user search with pagination, a client-side course filter, and
  the preserved user, teacher-approval, course-approval, payment, membership,
  lab and category management sections.

### 6.5 Verification

```text
python -m compileall -q app.py config.py extensions.py routes utils tests
python -m pytest -q
126 passed
```

New regressions in `tests/test_dashboard.py`:

- Student dashboard exposes continue-learning and upcoming assignment data.
- Student dashboard renders meaningful empty states without enrolments.
- Teacher dashboard shows the pending-submission count and course statistics.
- Admin dashboard renders role counts, platform health and filters users by
  the `q` search term.

### 6.6 Database changes

None. No schema changes or migrations are required.

### 6.7 Remaining work after Phase 4

- Phase 3 leftovers: searchable catalogue, richer course detail page and player
  navigation.
- Phase 5: assignment/examination depth, late-submission policy, question banks
  and reporting.
- Phase 6: notifications, analytics, discussions and certificates.
- Phase 7: central authorization, audit logging, versioned migrations and CSP
  enforcement.

---

## 7. Phase 3 completion + assignment depth (2026-11-14)

### 7.1 Searchable course catalogue

`routes/course.py::index` and `templates/courses.html` now support:

- Keyword search across course title and description.
- Category and difficulty filters.
- Sort options: newest, oldest, title, price low/high.
- Server-side pagination (9 per page) that preserves active filters.
- A result count, active-filter badges, responsive filter sidebar, and a real
  empty state with a reset action.

### 7.2 Course detail page

`routes/course.py::details` now computes `total_lessons` and `total_minutes`.
`templates/course_details.html` shows module/lesson/duration metadata and a
sticky purchase card with a truthful “Course includes” checklist driven by the
course’s actual modules, lessons, assignments and quizzes.

### 7.3 Lesson player

`routes/course.py::player` now:

- Rejects lesson IDs that belong to another course with `404`.
- Computes `prev_lesson` / `next_lesson` across visible lessons.
- Passes the real `certificate` record and `enrollment` to the template.

`templates/course_player.html` adds a sidebar progress bar, previous/next lesson
navigation, and replaces the fake “Refresh & Claim Certificate” `alert()` with
real certificate state or honest progress guidance.

### 7.4 Assignment and submission depth

- `Assignment.allow_late_submission` (default `True`).
- `Submission.text_content` for written responses; `Submission.file_url` is now
  nullable and text-only submissions store an empty value.
- `routes/course.py::create_assignment` validates marks (1–10000), parses the
  due date safely and persists the late-submission setting.
- `routes/api.py::submit_assignment` accepts text responses, requires at least
  one of file/URL/text, rejects late submissions when the policy is disabled,
  and flags late submissions.
- `routes/api.py::grade_submission` validates numeric marks and clamps them to
  `[0, max_marks]`.
- The player assignment tab, student dashboard and teacher dashboard show
  written responses and late flags.

### 7.5 Verification

```text
python -m compileall -q app.py config.py extensions.py routes utils tests
python -m pytest -q
140 passed
```

New regressions:

- `tests/test_catalog_player.py`: catalogue search, pagination/filter
  preservation, empty state, player prev/next links, cross-course lesson
  rejection, real certificate state, assignment creation validation and
  late-submission persistence.
- `tests/test_api.py`: text-only submission, late rejection, late flagging and
  grade clamping/non-numeric rejection.

### 7.6 Database changes

`app.py` startup migrations add:

- `assignments.allow_late_submission BOOLEAN DEFAULT TRUE`
- `submissions.text_content TEXT`

Both are additive and safe for existing rows.

---

## 8. Examination depth (2026-11-14)

### 8.1 Quiz scheduling and result visibility

- `Quiz.opens_at`, `Quiz.closes_at` and `Quiz.results_published`.
- `Quiz.is_open(at)` centralises the window check.
- `routes/course.py::create_quiz` and `edit_quiz` validate numeric fields,
  parse opening/closing times, reject a closing time before the opening time
  and persist result visibility.
- `routes/api.py::take_quiz_view` blocks students outside the window with a
  clear message; teachers can still preview.
- `routes/api.py::submit_quiz` re-checks the window server-side so a stale page
  cannot submit late.

### 8.2 Per-question attempt records

- New `QuizAttemptAnswer` model stores the selected choice, correctness and
  points awarded for every question in an attempt.
- Choice IDs from another question/quiz are rejected and stored as no answer.
- Editing a quiz deletes its old questions, so existing attempt-answer rows for
  those questions are removed first to avoid integrity errors.

### 8.3 Result gating

- When `results_published` is false, submission responses omit the score,
  pass/fail and correct answers, and the notification says results are pending.
- The quiz page and student dashboard show an “Awaiting results” state instead
  of revealing scores.

### 8.4 Verification

```text
python -m compileall -q app.py models routes tests
python -m pytest -q
147 passed
```

New regressions:

- `tests/test_api.py`: per-question answers stored, submissions rejected before
  opening/after closing, hidden results, and cross-question choice rejection.
- `tests/test_catalog_player.py`: quiz schedule/result visibility saved and
  invalid windows rejected.

### 8.5 Database changes

`app.py` startup migrations add:

- `quizzes.opens_at TIMESTAMP`
- `quizzes.closes_at TIMESTAMP`
- `quizzes.results_published BOOLEAN DEFAULT TRUE`
- `quiz_attempt_answers` table (created via `db.create_all()`)

All additive and safe for existing rows.

---

## 9. Notifications centre + question analytics (2026-11-14)

### 9.1 Notifications centre

- New `/notifications` page (`routes/notice.py::notifications`) listing the
  signed-in user's notifications with All/Unread filters and pagination.
- `POST /notifications/<id>/read` marks one notification read and is scoped to
  the current user (other users' notifications return `404`).
- `POST /notifications/read-all` marks only the current user's unread
  notifications.
- The header dropdown now links to the full page, and the sidebar has a
  Notifications entry for every role.
- `templates/notifications.html` uses the design-system cards, badges and
  empty states.

### 9.2 Question-level analytics

- `routes/dashboard.py::teacher_analytics` now aggregates `QuizAttemptAnswer`
  rows per question (answered, correct, correct rate).
- `templates/teacher_analytics.html` exposes a collapsible
  “Question-level accuracy” breakdown under each quiz.
- Access remains restricted to the course owner and admins.

### 9.3 Verification

```text
python -m compileall -q app.py models routes tests
python -m pytest -q
153 passed
```

New regressions:

- `tests/test_notifications.py`: login required, own-notifications scoping,
  mark-all scoping, single-read ownership and the unread filter.
- `tests/test_dashboard.py`: question-level accuracy renders for the course
  owner.

### 9.4 Database changes

None. This increment reuses existing tables and the `quiz_attempt_answers`
table added in section 8.
