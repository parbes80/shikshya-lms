# Shikshya (शिक्षा) - Modern Learning Management System

A production-ready Learning Management System built with Flask, featuring role-based dashboards, video course player, timed assessments, gamification, and AI chatbot.

## Features

- **Role-Based Access Control**: Admin, Teacher, Student dashboards with granular permissions
- **Course Management**: Create courses with modular lessons, videos, documents, and quizzes
- **Video Player**: Split-screen player with syllabus navigation, progress tracking, and playback speed control
- **Interactive Assessments**: Timed quizzes with live countdown, instant scoring, and corrections review
- **Gamification**: Learning streaks, achievement badges, progress tracking
- **QR-Certificates**: Auto-generated completion certificates with unique QR verification codes
- **AI Mentor Chatbot**: Context-aware educational assistant with inline code formatting
- **Discussion Forums**: Course-specific Q&A threads with real-time reply notifications
- **Dark/Light Theme**: System-persistent theme toggle with glassmorphism design
- **Simulated Payments**: Sandbox eSewa/Khalti wallet checkout for paid courses

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, Flask 3.0 |
| ORM | SQLAlchemy 3.1 with Flask-Migrate |
| Auth | Flask-Login, Werkzeug scrypt hashing |
| Frontend | Vanilla CSS (HSL tokens) + Vanilla JS |
| Templates | Jinja2 with modular inheritance |
| Security | Flask-WTF CSRF, Flask-Limiter rate limiting |
| Database | PostgreSQL 15 (production), SQLite (dev) |
| Deployment | Docker Compose (Nginx + Gunicorn + PostgreSQL) or manual VPS |

## Quick Start

### Prerequisites
- Python 3.10+
- pip

### Setup

```bash
# Clone and enter directory
cd Shikshya

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate
# Activate (Linux/macOS)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create environment config
cp .env.example .env
# Edit .env with your SECRET_KEY
# For local demo data also set SEED_DEMO_DATA=true

# Initialize the database and, only if SEED_DEMO_DATA=true, add demo data
python seed.py

# Run development server
python app.py
```

Visit **http://localhost:5000**

> Demo accounts are created only when `SEED_DEMO_DATA=true` **and** you run
> `python seed.py` (or boot with an empty database). Never enable this flag in
> production.

### Using Docker

```bash
docker-compose up --build
```

## Development Demo Credentials

These accounts exist **only** in a development database seeded with
`SEED_DEMO_DATA=true`. They are not created in production, and the passwords
below must never be used on a deployed instance.

| Role | Username | Email | Password |
|------|----------|-------|----------|
| Admin | admin | admin@shikshya.edu | admin123 (dev only) |
| Teacher | teacher_sandesh | teacher@shikshya.edu | teacher123 (dev only) |
| Student | student_pradeep | student@shikshya.edu | student123 (dev only) |

### Create a production administrator

Do not reuse demo credentials in production. Create an administrator with the
CLI, choosing a strong unique password:

```bash
python manage.py create-admin
```

The command creates the built-in roles if needed, then creates or promotes the
given account to Admin. Passwords are prompted for and never printed.

## Project Structure

```
Shikshya/
├── app.py                  # App factory, blueprints, error handlers
├── config.py               # Environment-based configuration
├── database.py             # SQLAlchemy + Flask-Migrate init
├── manage.py               # CLI manager for migrations
├── seed.py                 # Database seeder (idempotent)
├── models/
│   ├── user.py             # User, Role, UserProfile
│   ├── course.py           # Category, Course, Module, Lesson, Review
│   ├── learning.py         # Enrollment, Quiz, Question, Assignment, Submission
│   └── interaction.py      # Certificate, Discussion, Notification, Payment
├── routes/
│   ├── auth.py             # Registration, login, profile management
│   ├── main.py             # Home, about, contact, certificate verification
│   ├── dashboard.py        # Role-based dashboards with analytics
│   ├── course.py           # Course catalog, enrollment, player, CRUD
│   └── api.py              # REST API: progress, quizzes, AI chat, forums
├── templates/
│   ├── base.html           # Root template with nav, sidebar, AI drawer
│   ├── home.html           # Landing page with stats and featured courses
│   ├── courses.html        # Searchable course catalog with filters
│   ├── course_player.html  # Split-screen video player with tabs
│   ├── quiz.html           # Timed quiz interface with live scoring
│   └── errors/             # Error pages (403, 404, 429, 500)
├── static/
│   ├── css/                # Design tokens, components, layouts
│   └── js/                 # Theme, player, quiz, AI chat controllers
└── Dockerfile              # Multi-stage production build
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/progress/video` | POST | Track video watch progress |
| `/api/quiz/submit` | POST | Submit quiz answers |
| `/api/ai/chat` | POST | AI chatbot conversation |
| `/api/discussions/create` | POST | Create forum topic |
| `/api/discussions/<id>/reply` | POST | Reply to topic |
| `/api/notifications` | GET | Fetch unread notifications |
| `/api/notifications/<id>/read` | POST | Mark notification read |
| `/api/assignments/<id>/submit` | POST | Submit assignment |
| `/api/certificates/<code>/qrcode` | GET | Generate QR code |

## Security

- CSRF protection on all state-changing forms (Flask-WTF)
- POST-only approvals, publishing, password-reset approval and logout
- Rate limiting on all routes, with stricter login and forgot-password limits
- Password hashing with Werkzeug scrypt
- HTTP-only, SameSite cookies; secure cookies and HSTS in production
- 12-hour sessions and 7-day remember-me tokens
- `SESSION_PROTECTION='strong'` session fingerprinting
- Server-side authorization on quizzes, evaluations, discussions, documents
  and uploads
- HTML sanitization for lesson/lab rich text and Markdown (`bleach`)
- Upload extension allowlists and generated filenames
- No server-side fetching of user-supplied document URLs (SSRF protection)
- Security headers, including a report-only Content Security Policy
- Parameterized queries via SQLAlchemy ORM
- No hardcoded secrets in production code

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | Yes | — | Flask session signing key (use `openssl rand -hex 32`) |
| `DATABASE_URL` | No | SQLite | Database connection string (PostgreSQL in prod) |
| `SESSION_COOKIE_SECURE` | No | production: True | Send cookies only over HTTPS |
| `FLASK_ENV` | No | development | Set `production` for deployment |
| `TRUST_PROXY_HEADERS` | No | production: True | Trust `X-Forwarded-*` from a reverse proxy |
| `FORCE_HTTPS` | No | production: True | Redirect HTTP to HTTPS and reject insecure POSTs |
| `SEED_DEMO_DATA` | No | False | Create demo users/courses on seed/boot. Development only; keep `False` in production |
| `SITE_URL` | No | http://localhost:5000 | Public site URL (used in emails and trusted document links) |
| `MAIL_SERVER` | No | smtp.gmail.com | SMTP server hostname |
| `MAIL_PORT` | No | 587 | SMTP port |
| `MAIL_USE_TLS` | No | true | Enable TLS for SMTP |
| `MAIL_USERNAME` | No | — | SMTP login username (full email) |
| `MAIL_PASSWORD` | No | — | SMTP App Password |
| `MAIL_DEFAULT_SENDER` | No | — | Sender address in emails |
| `RATELIMIT_STORAGE_URI` | No | memory:// | Redis URI for production rate limiting (`RATELIMIT_STORAGE_URL` is also accepted) |

## Database Migrations

```bash
# Initialize migrations
flask db init

# Create a migration
flask db migrate -m "Description"

# Apply migrations
flask db upgrade
```

## License

MIT
