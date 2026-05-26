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

# Initialize and seed database
python seed.py

# Run development server
python app.py
```

Visit **http://localhost:5000**

### Using Docker

```bash
docker-compose up --build
```

## Test Credentials

| Role | Username | Email | Password |
|------|----------|-------|----------|
| Admin | admin | admin@shikshya.edu | admin123 |
| Teacher | teacher_sandesh | teacher@shikshya.edu | teacher123 |
| Student | student_pradeep | student@shikshya.edu | student123 |

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

- CSRF protection on all forms (Flask-WTF)
- Rate limiting on all routes (Flask-Limiter)
- Password hashing with Werkzeug scrypt
- HTTP-only, SameSite cookies
- Input validation and sanitization
- Parameterized queries via SQLAlchemy ORM
- No hardcoded secrets in production code

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | Yes | — | Flask session signing key (use `openssl rand -hex 32`) |
| `DATABASE_URL` | No | SQLite | Database connection string (PostgreSQL in prod) |
| `SESSION_COOKIE_SECURE` | No | False | Set `True` when using HTTPS |
| `FLASK_ENV` | No | development | Set `production` for deployment |
| `SITE_URL` | No | http://localhost:5000 | Public site URL (used in emails) |
| `MAIL_SERVER` | No | smtp.gmail.com | SMTP server hostname |
| `MAIL_PORT` | No | 587 | SMTP port |
| `MAIL_USE_TLS` | No | true | Enable TLS for SMTP |
| `MAIL_USERNAME` | No | — | SMTP login username (full email) |
| `MAIL_PASSWORD` | No | — | SMTP App Password |
| `MAIL_DEFAULT_SENDER` | No | — | Sender address in emails |
| `RATELIMIT_STORAGE_URL` | No | memory:// | Redis URL for production rate limiting |

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
