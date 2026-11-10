# Shikshya UX/UI Improvement Plan

**Audience:** product + frontend + backend maintainers
**Basis:** audit of the existing Flask/Jinja app (templates, `static/css`, `static/js`, `routes/*.py`)
**Scope:** improve the current app. No replatforming, no framework migration, no redesign-from-zero.

---

## 1. Assumptions

These are inferred from the codebase; adjust if any are wrong.

| Area | Assumption |
|---|---|
| Users | Students (find → enroll → learn → assess → certificate), Teachers (author courses, lessons, quizzes, assignments, grade), Admins (approve courses/payments, manage users). |
| Stack | Flask 3 + Jinja2 server-rendered pages, vanilla CSS/JS, SQLAlchemy, Flask-Login, CSRF-protected `fetch` via `csrfFetch`, Font Awesome CDN, Google Fonts `@import`. Keep it. |
| Devices | Desktop-first authoring; meaningful mobile learning traffic (the player already has a mobile drawer and bottom nav). |
| Content | Mostly short video + rich-text lessons, quizzes, file/URL assignments, live classes, lab manuals. |
| Accounts | Email/password. Local SQLite in dev; Postgres in production. |
| Current state | Progress is stored in `Enrollment.progress_percent` and recalculated in `routes/api.py::_update_course_progress`; per-lesson state lives in `LessonProgress` (already has `video_progress_seconds` and `updated_at`). |

Two guardrails for everything below:

1. **Server-rendered first.** Any interactivity must degrade to a working link/form. No SPA.
2. **Fix the core loop before adding novelty.** The core loop is: find course → resume lesson → consume → confirm progress → assess.

---

## 2. What the audit found (evidence)

| # | Finding | Where | Severity |
|---|---|---|---|
| 1 | No skip link, no `aria-current`, no `aria-expanded` on menu toggles; two competing mobile menus (header hamburger + sidebar toggle). | `templates/base.html`, `static/js/main.js` | High |
| 2 | Search input has no label; profile "menu" is a `div` with `onclick`; icon-only close buttons are `<i>` elements; notification panel has no dialog semantics. | `base.html` | High |
| 3 | Flash and toast containers have no `role`/`aria-live`, so status changes are silent to screen readers. | `base.html`, `course_player.js`, `quiz.js` | High |
| 4 | White text on `#10b981` (2.56:1), `#f59e0b` (2.15:1), `#ef4444` (3.76:1) fails WCAG AA; `--text-light: #94a3b8` on white is 2.56:1. | `main.css`, inline badge styles | High |
| 5 | No `prefers-reduced-motion` handling; `html { scroll-behavior: smooth }`, `--transition: all .25s`, an infinite flame bounce. | `main.css`, `dashboard.css` | High |
| 6 | Player tabs are `href="#"` + JS `display` toggles: no URL state, back button doesn't restore a tab, no tab ARIA, no focus move. | `course_player.html`, `course_player.js` | High |
| 7 | Module headers are `<h4 onclick>` — not keyboard-operable; scheduled lessons render as `<a>` with no `href`, which is invalid and unfocusable. | `course_player.html` | High |
| 8 | No resume affordance. `video_progress_seconds` and `updated_at` exist, but the dashboard/course page never uses them. | `student_dashboard.html`, `routes/dashboard.py`, `routes/course.py` | High |
| 9 | Quiz uses `alert()`/`confirm()`, loses answers on refresh, does not flag unanswered questions, and renders review text through `innerHTML`. | `quiz.js` | High |
| 10 | Notes are per-lesson `localStorage` only: no sync, no "saved" indicator, lost in private mode or on device switch. | `course_player.js` | Medium |
| 11 | Catalog filters reload the whole page on every radio change; no result count, sort, or active-filter summary; card is only clickable on its title. | `courses.html` | Medium |
| 12 | Course details lists a static curriculum with no per-lesson state, no expand/collapse, and no sticky enroll CTA. | `course_details.html` | Medium |
| 13 | Hard-coded light-theme hex values inside templates break dark mode (`#fefce8`, `#f1f5f9`, `#92400e`). | `course_player.html`, `student_dashboard.html`, `course_details.html` | Medium |
| 14 | Discussion/reply rendering inserts user text with `innerHTML`; assignment errors are `console.error` only. | `course_player.js` | Medium (safety + trust) |
| 15 | "Mark complete" fetches `check-${lessonId}` where `lessonId` is `null` for text lessons, then reloads the page (wiping tab state). | `course_player.js:100-127` | Medium |
| 16 | Progress math (lessons + passed quizzes + submissions) is not explained anywhere; the certificate copy says "complete all lessons", which contradicts it. | `api.py`, `course_player.html` | Medium |

---

## 3. Priority model

- **P0** — blocks access, trust, or the core learning loop. Ship in the next 1–2 weeks.
- **P1** — removes repeated friction in browsing/learning/teaching. Next 3–6 weeks.
- **P2** — motivation, polish, performance, consistency. After P0/P1 are stable.

Effort: **S** ≤ 1 day, **M** 2–4 days, **L** 1–2 weeks (one engineer).

---

## 4. P0 — trust and access

### P0-1. Make the app shell keyboard- and screen-reader-correct

**Problem.** Keyboard users cannot skip the 7-item header + role sidebar, cannot tell which page they are on, and get no announcement when a flash/toast appears. Mobile users face two different menu systems that behave differently.

**Change.**
- Add a skip link as the first focusable element in `base.html`:
  ```html
  <a class="skip-link" href="#main-content">Skip to content</a>
  ```
  and give `<main>` `id="main-content"` + `tabindex="-1"`.
- Add `aria-current="page"` to the active header/sidebar link (compute from `request.endpoint`).
- Give `#hamburger-btn`, `#sidebar-toggle-btn`, `#sidebar-close-btn`, `#ai-chat-close-btn`, `#notif-dropdown-btn` real `aria-label`s, `aria-expanded`, and `aria-controls`.
- Convert the profile `div` to `<a href="{{ url_for('auth.profile') }}">`.
- Convert close icons (`<i class="fas fa-times close-alert">`) to `<button type="button" aria-label="Dismiss">`.
- Flash container: `role="status" aria-live="polite"`; error flashes `role="alert"`. Same for the toast helper, but throttle so repeated saves don't spam.
- Label the header search: visually hidden `<label for="global-search">Search courses</label>`.
- Unify mobile navigation: keep the header hamburger as the only global menu; inside the drawer, render the role sidebar links instead of duplicating them. The player keeps its own curriculum drawer.
- Manage focus on open/close: move focus into the drawer, trap Tab, return focus to the trigger on close, close on `Escape`.

**Verify.**
- Keyboard-only pass: Tab from page load reaches "Skip to content" first; every control is reachable in a logical order; Escape closes overlays; focus returns to the trigger.
- Screen reader spot check (NVDA + Firefox, VoiceOver + Safari): page title announced, current nav item announced, flash messages read once.
- Automated: axe DevTools and Lighthouse a11y ≥ 95 on `/`, `/courses`, `/courses/<slug>`, `/dashboard/student`, player, quiz.
- Usability: 5 learners attempt "start the next lesson" on mobile; success without opening the wrong menu (target 5/5).

**Effort:** M.

---

### P0-2. Fix contrast and make semantic colors theme-safe

**Problem.** Success/warning/danger badges use white text on mid-tone green/amber/red, which is unreadable for low-vision users and in bright classrooms. Hard-coded hex values also break dark mode.

**Change.**
- Introduce paired tokens in `main.css` and use them everywhere:
  ```css
  --success-bg: #ecfdf5; --success-fg: #065f46; --success-solid: #047857;
  --warning-bg: #fffbeb; --warning-fg: #92400e; --warning-solid: #b45309;
  --danger-bg:  #fef2f2; --danger-fg:  #991b1b; --danger-solid:  #b91c1c;
  ```
  Use `*-bg` + `*-fg` for badges/alerts, `*-solid` only for large icons or ≥ 18.66px bold text.
- Raise `--text-light` in light theme from `#94a3b8` to `#64748b` (4.76:1), or restrict it to non-text decoration.
- Replace inline hex in `course_player.html`, `student_dashboard.html`, `course_details.html` with tokens.
- Verify focus rings on `--bg-card` and `--bg-app` in both themes; keep the existing `:focus-visible` rules but remove `outline: none` in `components.css` (`.form-control:focus`).
- Add a dark-mode pass to the player's inline `<style>` (table borders/headers currently light-only).

**Verify.**
- Contrast checker: every text/background pair ≥ 4.5:1 (normal) and ≥ 3:1 (large/UI). Record results in the PR.
- Toggle dark mode on `/courses`, course details, player, quiz, dashboard; no light-only panels or invisible text.
- Automated: axe color-contrast rule returns zero violations on the pages above.

**Effort:** S–M.

---

### P0-3. Resume where you left off (new feature)

**Problem.** Learners land on a dashboard of courses and must re-open a course, scan the curriculum, and guess which lesson they were on. Video position is saved but only applied if they happen to open the exact same lesson.

**Change.**
- **Data:** no migration needed. `LessonProgress.updated_at` + `video_progress_seconds` + `is_completed` are sufficient. If you want an explicit signal, add `last_accessed_at` later.
- **Dashboard:** replace the per-course card's "View Course" with a primary **Continue** action that deep-links to the last incomplete lesson:
  `/courses/<slug>/player?lesson_id=<id>` (optionally `#t=<seconds>`).
  Show: course title, lesson title, `x of y lessons`, percent, and "Resume at 12:34" when `video_progress_seconds > 30`.
- **Course details:** if enrolled, the primary CTA becomes **Continue learning** and names the next lesson.
- **Player:** on load, if the saved position is > 30s and < 95% of duration, show a small non-blocking banner: "Resuming at 12:34 — Start over". Respect the user's choice for the session.
- **Global:** expose a "Continue" item in the student sidebar/dashboard header that resolves the most recently updated enrollment.

Helper (conceptual, in `routes/dashboard.py`):
```python
last = (LessonProgress.query
        .join(Enrollment)
        .filter(Enrollment.student_id == current_user.id,
                LessonProgress.is_completed.is_(False))
        .order_by(LessonProgress.updated_at.desc())
        .first())
```

**Verify.**
- Task test: "Continue the course you were doing yesterday." Measure time-to-video and wrong-lesson opens; target < 10s and 0 wrong opens for 5/5 learners.
- Metric: `continue_click` → `video_play` conversion; median clicks from dashboard to playing video (target ≤ 2).
- Edge cases: completed course (CTA becomes "Review"/"Certificate"), no enrollment (CTA = Browse), lesson unpublished (fall back to next visible lesson), saved position > 95% (start at 0).

**Effort:** M.

---

### P0-4. Give the player a real navigation model

**Problem.** The player is a dead end. Tabs are JS-only, there is no next/previous lesson, module headers only work with a mouse, and a text-lesson completion reloads and loses the open tab.

**Change.**
- **Lesson paging:** add a persistent footer inside the player content: `← Previous lesson` / `Next lesson →`, plus "Next: <title>" when the current lesson is completed. Keep the fixed bottom tab bar for sections, but separate "sections" from "lessons" visually.
- **Tabs as links:** change `.player-bottom-nav a[data-tab]` to `?tab=quizzes` (server reads `request.args.get('tab')` and renders the active pane). Enhances to in-page switching with `history.pushState`; back/forward and refresh preserve state.
- **ARIA:** wrap sections in `role="tablist"`, each link `role="tab"` + `aria-selected` + `aria-controls`; panes `role="tabpanel"` + `tabindex="0"`. Follow the tabs pattern with arrow-key support, or simplify to navigation links with `aria-current="true"` — links are the lower-risk option here.
- **Curriculum:** replace `<h4 onclick>` with `<button class="module-toggle" aria-expanded="true|false" aria-controls="module-N">`; wrap lessons in `<ul id="module-N">`. Scheduled lessons become `<span aria-disabled="true">` with a text label, not an empty anchor.
- **Context:** add a compact breadcrumb `My courses / <course> / <lesson>` and a course progress meter at the top of the player (the sidebar only shows per-lesson ticks today).
- **Fix the completion bug:** read `data-lesson-id` from the button, not the video closure, and update the sidebar tick + progress without `location.reload()`.

**Verify.**
- Keyboard: Tab to a module header, Enter/Space collapses it, `aria-expanded` flips; Arrow keys move between tabs if you implement the tabs pattern.
- Browser: open `?tab=notes`, refresh, press Back twice — state is preserved.
- Task test: "Finish this lesson and go to the next one." Count clicks; target ≤ 2 from the lesson content.
- Regression: completion updates the tick and progress bar with no full reload; check the text-lesson path specifically.

**Effort:** M–L.

---

### P0-5. Make quizzes recoverable and honest

**Problem.** A refresh or accidental navigation destroys all answers. Unanswered questions are only discovered after submission. The timer is a color-only cue, and submission errors are `alert()` or silent `console.error`. Review text is injected with `innerHTML`.

**Change.**
- **Autosave:** persist answers to `sessionStorage` keyed by `quiz_id` on every change; restore on load with a "Restored your answers" notice. On submit success, clear it. (A server-side draft is a later upgrade; `sessionStorage` fixes refresh immediately.)
- **Pre-submit check:** when answers are missing, show an inline summary — "3 of 10 unanswered" with a "Review unanswered" list — instead of `confirm()`.
- **Accessible timer:** add `role="timer"` + `aria-live="off"`, announce only at 5 min / 1 min / expiry via the polite live region. Keep the color change but add an icon/text ("Time is running low").
- **Errors:** replace `alert()` with an inline alert region above the question card, with a Retry button. Never discard local answers on failure.
- **Safe rendering:** build review rows with `textContent`/`createElement`, not template `innerHTML`. Same for discussion threads in `course_player.js`.
- **Submit feedback:** keep the button in a loading state (`aria-busy`, disabled, spinner) and announce "Submitting…" then "Submitted".
- **Results:** announce the score in a live region and move focus to the results heading; keep the current review layout.

**Verify.**
- Refresh mid-quiz → answers restored; submit → storage cleared.
- Submit with blanks → inline list of unanswered questions, no native dialog.
- Screen reader: score and pass/fail announced once; timer warnings announced without reading every second.
- Automated: axe on quiz page; no `alert`/`confirm` in `quiz.js` (lint/grep check).
- Usability: 5 learners complete a 10-question quiz; zero "I lost my answers" reports; time-to-recover after refresh < 5s.

**Effort:** M.

---

## 5. P1 — remove repeated friction

### P1-1. Turn the catalog into a search tool, not a page reload

**Problem.** Every filter click submits the form and reloads; the result count is only shown when a text query exists; there is no sort; and only the card title is a link.

**Change.**
- Debounced `fetch` of `/courses?...` with the existing server route, swapping only the results grid; fall back to normal form submit if JS fails. Update the URL with `replaceState`.
- Add a result header: "24 courses · Beginner · Design" with removable filter chips and a **Clear all** action.
- Add sort: Newest, Price, Rating (add `?sort=` to `routes/course.py`).
- Make the whole card clickable with a single stretched link (`.course-card a::after { position:absolute; inset:0 }`), keeping the title as the accessible name.
- Add useful card metadata: lesson count, total duration, rating, and an "Enrolled · 42%" state.
- Mobile filter drawer: `aria-expanded`, focus trap, close button, and a visible "Show 24 results" button instead of auto-submitting each radio.
- Keep the current empty state, but add "Reset filters" as a button and suggest adjacent categories.

**Verify.**
- Task test: "Find a free beginner design course and open it." Measure time and filter actions; target < 30s, ≤ 3 actions.
- Keyboard: tab through cards — one stop per card, visible focus, Enter opens.
- Network: filtering does not reload the page (JS path); disabling JS still filters correctly.
- Metric: catalog → course-detail CTR; zero-result rate; filter usage.

**Effort:** M.

---

### P1-2. Make course details answer "what will I get?"

**Problem.** The curriculum is a flat list of titles with no state, no expansion, and no preview. The enroll CTA is duplicated for mobile/desktop and is not sticky. There is no statement of outcomes, time commitment, or what "progress" means.

**Change.**
- Add a "What you'll learn" block (3–6 outcomes) and a facts row: lessons, total time, level, certificate, language.
- Curriculum: collapsible modules (first open), lesson counts, durations, and — for enrolled users — a status icon + direct "Continue" link per lesson.
- Sticky enroll/continue panel on desktop; keep the mobile inline CTA but make it one shared partial to avoid drift.
- Show the honest progress definition next to any percentage ("lessons + passed quizzes + submitted assignments").
- Reviews: render empty stars for missing ratings; add a distribution summary.

**Verify.**
- Task test: "Decide whether this course fits you and start it." Ask participants to state time commitment and outcomes; target 5/5 can answer from the page alone.
- Enroll → continue conversion; bounce rate on course details.
- Visual check at 360/768/1280 with the sticky panel; no CTA overlap.

**Effort:** M.

---

### P1-3. Make progress explainable and actionable

**Problem.** `progress_percent` mixes lessons, passed quizzes, and submissions, but the UI shows a bare bar. Learners cannot tell what remains, and the certificate copy contradicts the math. Instructors see "stuck" counts but cannot act on them.

**Change.**
- Dashboard course card: show `x/y lessons · a/b quizzes · c/d assignments`, the next incomplete item, and an estimated time remaining using `Lesson.duration_minutes`.
- Add a milestone line: "3 lessons to your certificate."
- Player header: same compact breakdown + "Next up" link.
- Certificate tab: replace the `alert()` placeholder with a real completion check and a checklist of unmet requirements (lessons / quizzes / assignments), each linking to the item.
- Instructor analytics: make each "stuck: N" row expandable to the list of students and their last activity (`LessonProgress.updated_at`), with a "Send reminder" action reusing `Notification`.
- Teacher course cards: add a publish-status badge and "N lessons pending publish".

**Verify.**
- Comprehension test: show a dashboard screenshot and ask "what do you still need to do to finish?" Target 5/5 correct.
- Metric: certificate claims per completed enrollment; support questions about progress.
- Instructor task: "Find the 5 students stuck on Lesson 3 and message them." Target < 2 minutes.

**Effort:** M.

---

### P1-4. Notes 2.0 — save, find, and export

**Problem.** `localStorage` notes are invisible outside one browser, have no save state, and are lost in private mode. Learners taking notes next to video have no way to jump back to a timestamp.

**Change.**
- New `LessonNote` model: `id, student_id, lesson_id, body, timestamp_seconds (nullable), created_at, updated_at`. One note per lesson by default; allow multiple if you want timestamped notes.
- Keep local-first behavior: write to `localStorage` immediately, sync to `/api/notes/<lesson_id>` with debounce, show "Saving… / Saved" (text, not color only). On conflict, keep the newest `updated_at`.
- Add "Add note at current time" on video lessons; notes list shows `12:34` chips that seek the video.
- Add a per-course notes view and Markdown/plain-text export; include notes in the lesson PDF export if feasible.
- Empty state explains the feature in one sentence.

**Verify.**
- Offline → type → reconnect → note persists after reload and appears on another device.
- Keyboard/SR: save-state changes announced politely; textarea has a visible label.
- Migration: `flask db migrate/upgrade` reviewed; existing `localStorage` notes imported once on first load.
- Metric: notes created per active learner; return rate to the notes tab.

**Effort:** M–L.

---

### P1-5. Lesson bookmarks and "My list"

**Problem.** Learners cannot mark "come back to this" without completing it, and there is no cross-course list of saved items. The curriculum only communicates done/not-done.

**Change.**
- `LessonBookmark` model (`student_id, lesson_id, created_at`, unique pair).
- Bookmark toggle in the player top bar and on each curriculum row; state exposed with `aria-pressed`.
- "Bookmarked" filter in the course curriculum and a "Saved" section on the student dashboard.
- Add `?bookmarked=1` support in the player route so the sidebar can filter server-side.
- Do not conflate bookmarks with completion; keep separate icons and labels.

**Verify.**
- Toggle from player and sidebar stays in sync after reload; screen reader announces pressed state.
- Task test: "Save this lesson and find it again tomorrow." Target < 20s, 5/5.
- Metric: bookmarks per active learner; bookmarked-lesson completion rate vs baseline.

**Effort:** M.

---

### P1-6. Reduce instructor authoring confusion

**Problem.** Teachers land on a dense dashboard with many inline-styled panels. Course/lesson/quiz creation uses separate full-page forms with no draft state, no preview, and destructive actions without confirmation. Publishing is implicit.

**Change.**
- Add a clear status model per course: Draft → Pending review → Published → Archived, with one primary action per state.
- Lesson form: live preview of rendered Markdown/HTML, character/word count, and a "Preview as student" link.
- Warn on unsaved changes (`beforeunload`) and preserve form data on validation failure (currently redirects lose input).
- Confirm destructive actions with a modal that names the object; require typing the title only for course deletion.
- Add reorder controls (up/down is enough; no drag-and-drop dependency) and "duplicate lesson".
- Group the dashboard into "Needs attention" (submissions to grade, pending publish, upcoming live classes) and "All courses".

**Verify.**
- Task test with 3 instructors: create a module + lesson, publish it, and find the grading queue. Measure errors and time; target no dead ends.
- Metric: abandoned create flows; validation-error rate; time from course creation to publish.
- Regression: existing routes/tests still pass; CSRF preserved on all new forms.

**Effort:** L.

---

## 6. P2 — motivation, motion, and polish

### P2-1. Completion celebrations that respect the user

**Problem.** Completion is a toast plus a reload. The emotional payoff is weak, and the streak flame is decorative rather than explained.

**Change.**
- Lesson complete: inline check animation + progress bar fill + a short "Lesson complete · 3 of 12" toast.
- Module complete: a compact banner with the module name and next module CTA.
- Course complete: a one-time celebration panel on the dashboard (confetti canvas or CSS-only, ≤ 2.5s), certificate CTA, and a dismiss action. Persist "seen" so it doesn't repeat.
- Streak: explain the rule in a tooltip/popover ("a lesson or quiz on consecutive days"), show the week as 7 dots, and never rely on the flame emoji alone.

**Verify.**
- Task test: complete a lesson; ask "what changed?" Target 5/5 can state progress and next step.
- Metric: next-lesson click-through within 60s of completion; 7-day return rate.
- Accessibility: celebration is announced via `role="status"`, does not steal focus, and is dismissible by keyboard. With reduced motion, show a static success card.

**Effort:** M.

---

### P2-2. A small, consistent motion system

**Problem.** Motion is ad hoc: `transition: all`, smooth scroll everywhere, an infinite flame bounce, and no reduced-motion path. It feels inconsistent and costs frames on low-end phones.

**Change.**
- Define tokens: `--dur-fast: 120ms`, `--dur-base: 200ms`, `--dur-slow: 320ms`, `--ease-out: cubic-bezier(.2,.8,.2,1)`. Replace `all` with explicit properties (`opacity`, `transform`, `background-color`, `border-color`, `width`).
- Scope motion to feedback and orientation only: hover/press, drawer/panel slide, tab cross-fade, progress fill, completion check. No looping decorative motion except the streak (and make it subtle).
- Add the global reduced-motion block (see §7).
- Avoid animating layout properties; prefer `transform`/`opacity`. Progress width is acceptable because it is a single small element, but keep it ≤ 600ms and skip it under reduced motion.

**Verify.**
- `prefers-reduced-motion: reduce` in DevTools: no transforms, no smooth scroll, no looping animation; all state changes still legible.
- Performance: Chrome Performance panel on a 4× CPU-throttled mid-range Android emulation — no long task > 50ms attributable to animation; INP < 200ms; no layout thrash in the drawer/tab transitions.
- Visual regression: screenshots before/after at 360/768/1280 in both themes.

**Effort:** S–M.

---

### P2-3. A states kit: empty, loading, error, success

**Problem.** Empty states are inconsistent; async actions often fail silently or via `console.error`; there is no loading treatment for submissions, chat, or filtering.

**Change.**
- Standardize four components in `components.css`: `.state-empty`, `.state-error`, `.state-loading`, `.state-success` — icon, title, one sentence, one primary action.
- Use them for: no courses, no search results, no quizzes, no discussions, no notes, failed assignment upload, failed quiz submit, AI chat failure.
- Buttons get a loading state (`aria-busy`, disabled, spinner) for all `fetch` submissions.
- Add inline field errors (message + `aria-describedby`) instead of only flash messages.
- Add a retry path to every failed `fetch`; never leave the user at a dead end.

**Verify.**
- Fault injection: block `/api/*` in DevTools and confirm every action shows an error with Retry.
- Screen reader: error text is announced and associated with the field.
- Consistency review: all empty states use the same structure and tone.

**Effort:** M.

---

### P2-4. Asset and rendering performance

**Problem.** Google Fonts is loaded via CSS `@import` (serial request chain) and Font Awesome loads the full icon CSS from a CDN, both blocking first render. Templates carry large inline `<style>` blocks and repeated inline styles.

**Change.**
- Replace the `@import` with `<link rel="preconnect">` + `<link rel="stylesheet">` and `display=swap`; self-host the two font families if possible.
- Replace the full Font Awesome CSS with a subset/SVG sprite of the ~40 icons actually used, or self-host the webfont with `font-display: swap`.
- Move inline `<style>` from `course_player.html`/`quiz.html` into the relevant CSS file.
- Defer non-critical JS (`defer` on `main.js`, `course_player.js`, `quiz.js`), and load `ai_chat.js` only when the drawer opens.
- Add `loading="lazy"` + explicit `width`/`height` to course thumbnails to protect CLS.

**Verify.**
- Lighthouse mobile on `/`, `/courses`, player: LCP < 2.5s, CLS < 0.1, INP < 200ms (lab).
- WebPageTest on a slow 4G profile: confirm fonts/icons no longer block first paint.
- Bundle check: report KB of CSS/JS before/after; no visual regressions.

**Effort:** M.

---

### P2-5. Visual consistency pass

**Problem.** Four CSS files overlap, templates are heavy with inline styles, emoji mix with Font Awesome, and component names collide (`.course-card` means different things in catalog vs teacher dashboard).

**Change.**
- Audit and namespace: `.catalog-card` vs `.teacher-course-card`; document each component in a short `docs/ui-components.md`.
- Replace hard-coded colors/spacing with tokens; add spacing scale usage.
- Pick one icon family (Font Awesome) and remove emoji from UI labels (keep them out of `aria-label`s).
- Standardize card padding, border radius, badge shapes, and table styles.
- Move remaining inline styles into CSS; keep only dynamic values (e.g., progress width) inline.
- Add a `/styleguide` dev-only route rendering buttons, badges, alerts, cards, forms, and states in both themes.

**Verify.**
- Visual QA across 6 key screens × 2 themes × 3 widths against the styleguide.
- CSS lint: no new hard-coded hex outside tokens; no `transition: all`.
- Onboarding test: a new contributor can find the right component class in < 1 minute using the styleguide.

**Effort:** M–L.

---

## 7. Motion specification

| Interaction | Motion | Duration / easing | Reduced-motion behavior | Performance check |
|---|---|---|---|---|
| Button hover/press | background + 1px lift (`translateY(-1px)`) | 120ms / ease-out | Color change only, no lift | Composite-only; check no layout shift |
| Sidebar / player drawer | `translateX` | 220ms / ease-out | Appear instantly; no slide | Animate `transform` only; verify no jank in Performance panel |
| Modal / notification panel | `opacity` + `scale(.98→1)` | 160ms / ease-out | Instant, no scale | No long tasks; `will-change` only while open |
| Tab switch | `opacity` cross-fade | 120ms / linear | Instant swap | Avoid animating `height`; keep panes mounted |
| Progress bar update | `width` transition | 400–600ms / ease-out | Jump to final width | Single element; check paint time; no transition on scroll |
| Lesson complete check | scale-in + stroke draw (CSS) | 300ms / ease-out | Static check icon | CSS transform/opacity only; no JS loop |
| Course completion | confetti or badge pop, ≤ 2.5s, one-time | 2.5s max | Static success card | Canvas only if needed; stop after 2.5s; verify no frame drops on 4× throttle |
| Streak flame | subtle 2s alternate scale (1→1.03) | 2s / ease-in-out | None | Confirm it doesn't run off-screen; pause when tab hidden |
| Page/route transition | none by default; optional 150ms content fade | 150ms / ease-out | None | Avoid delaying navigation; measure INP |

Global CSS to add in `main.css`:

```css
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

Performance method for every animation:
1. Chrome DevTools → Performance, 4× CPU throttle, record the interaction.
2. Confirm no long task > 50ms caused by the animation and no layout/paint storms.
3. Check `transform`/`opacity` only in the Layers panel; avoid `top/left/width/height` where possible.
4. Re-test with reduced motion enabled; the interaction must still be understandable.
5. If an animation runs > 2.5s or loops, justify it or remove it.

---

## 8. Verification playbook

### 8.1 Usability tests (run after P0, again after P1)

**Learners (5 per round, mix of mobile/desktop):**
1. "Find a beginner course and start it." → success, time, wrong turns.
2. "Continue the lesson you were watching yesterday." → time to video, wrong-lesson opens.
3. "Finish this lesson and start the next one." → clicks, confusion moments.
4. "Take the quiz, lose connection, come back." → answer retention, recovery time.
5. "Find out what you still need to do to get your certificate." → correctness of answer.

**Instructors (3 per round):**
1. "Create a module and a lesson, then publish it." → completion, validation errors.
2. "Find students stuck on a lesson and message them." → time, path.
3. "Grade a submission and leave feedback." → completion, clarity.

Success bar: 5/5 (learners) and 3/3 (instructors) complete without facilitator help; any task > 2× target time is a defect.

### 8.2 Metrics to instrument

Add lightweight events (server logs or a `/api/events` endpoint; no third-party analytics required):

- `course_view`, `enroll_click`, `enroll_success`
- `continue_click`, `video_play`, `video_complete`
- `lesson_complete`, `next_lesson_click`
- `quiz_start`, `quiz_submit`, `quiz_abandon`, `quiz_answer_restored`
- `note_save`, `bookmark_toggle`
- `search_query`, `filter_apply`, `zero_results`
- `certificate_claim`, `certificate_blocked_reason`

Key ratios: dashboard → video play, lesson complete → next lesson, quiz start → submit, zero-result searches, certificate claims per completion.

### 8.3 Accessibility acceptance checklist (per PR)

- [ ] Keyboard-only path works for the changed flow; focus visible and in a logical order.
- [ ] No new `div`/`span` click handlers; use `a`/`button`.
- [ ] Icon-only controls have accessible names.
- [ ] Dynamic status uses `role="status"`/`aria-live` and is not announced repeatedly.
- [ ] `aria-expanded`/`aria-selected`/`aria-current` reflect state.
- [ ] Contrast ≥ 4.5:1 for text, ≥ 3:1 for UI/large text, in both themes.
- [ ] Reduced motion respected; no information conveyed by color alone.
- [ ] axe DevTools: zero critical/serious violations on the page.
- [ ] Zoom 200% and 320px width: no horizontal scroll, no clipped controls.

### 8.4 Automated checks

- Keep the existing pytest suite green (79 tests) and add tests for: resume-lesson resolution, progress explanation values, notes/bookmarks CRUD + ownership, quiz autosave payload validation, catalog sort/filter params.
- Add `pytest` route tests for the new player `?tab=` and `?lesson_id=` behavior, including unpublished-lesson fallback.
- Add a CI step running `axe` via Playwright (or `pa11y`) on 6 URLs; fail on serious violations.
- Add a CSS guard (stylelint or grep) against new `transition: all` and raw hex values in templates.

---

## 9. Sequencing

| Sprint | Work | Why first |
|---|---|---|
| 1 | P0-1 shell a11y, P0-2 contrast, P0-3 resume, P0-4 player nav, P0-5 quiz recovery | These unblock the core loop and remove the highest-trust failures. |
| 2 | P1-1 catalog, P1-2 course details, P1-3 progress, P1-6 instructor workflow | Improves discovery and authoring once the loop is stable. |
| 3 | P1-4 notes, P1-5 bookmarks, P2-1 celebration, P2-2 motion, P2-3 states | Adds retention features on top of a reliable base. |
| 4 | P2-4 performance, P2-5 consistency, styleguide | Pays down the visual/technical debt created by fast iteration. |

Dependencies:
- P0-3 depends on P0-4's `?lesson_id=` deep link.
- P1-4/P1-5 require migrations; batch them into one migration and review rollback.
- P2-2 should land before P2-1 so celebrations use the agreed motion tokens and reduced-motion rules.

Risks:
- Tab-to-URL refactor touches the player's core JS; ship behind a small feature flag or page variant and test the text/document lesson paths.
- `localStorage` note migration must be idempotent; back up existing keys and never delete until the server save succeeds.
- Contrast token changes can alter brand perception; review with stakeholders using the styleguide before rollout.

---

## 10. Quick wins (< 1 day each)

1. Skip link + `aria-current` + labels on icon buttons (P0-1 subset).
2. `role="status"` on flash/toast containers.
3. Replace white-on-green/amber/red badges with tinted bg + dark text (P0-2 subset).
4. Add the reduced-motion block.
5. Fix `check-${lessonId}` for text lessons and remove the reload.
6. Replace `alert()`/`confirm()` in the quiz with inline messages.
7. Make the whole course card a link.
8. Add `defer` to `main.js` and `loading="lazy"` to thumbnails.

---

## 11. Explicit non-goals

- No React/Vue/Next migration. Jinja + vanilla JS is sufficient for this surface area and keeps the existing auth/CSRF/server-rendering model intact.
- No full visual rebrand. The token system and component consistency work are enough.
- No generic gamification expansion (points shops, leaderboards) until completion and resume metrics plateau.
- No native mobile app. Fix the responsive player and shell first.
