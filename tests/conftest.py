"""Shared pytest fixtures for the Shikshya test suite.

The suite runs against a throw-away SQLite database and never touches the
development database (``shikshya.db``).
"""

import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from itertools import count
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Must be set before importing the app/config modules.
os.environ.setdefault('SECRET_KEY', 'test-secret-key')

from app import create_app  # noqa: E402
from database import db  # noqa: E402
from models.course import Category, Course, Lesson, Module  # noqa: E402
from models.learning import (  # noqa: E402
    Assignment,
    Choice,
    Enrollment,
    LessonProgress,
    Question,
    Quiz,
)
from models.user import Role, User, UserProfile  # noqa: E402

_TMP_DIR = Path(tempfile.mkdtemp(prefix='shikshya-tests-'))
_TEST_DB_PATH = _TMP_DIR / 'test.db'


class TestConfig:
    TESTING = True
    SECRET_KEY = 'test-secret-key'
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{_TEST_DB_PATH.as_posix()}"
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Keep tests isolated from startup bootstrap, CSRF and rate limiting.
    AUTO_INIT_DB = False
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False

    # Needed so url_for(..., _external=True) works outside a request.
    SERVER_NAME = 'localhost'

    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False

    MAIL_SERVER = ''
    MAIL_USERNAME = ''
    UPLOAD_FOLDER = str(_TMP_DIR / 'uploads')


def _seed_roles():
    db.session.add_all([
        Role(name='Admin', description='Administrator'),
        Role(name='Teacher', description='Instructor'),
        Role(name='Student', description='Learner'),
    ])
    db.session.commit()


@pytest.fixture(scope='session')
def _app():
    application = create_app(TestConfig)
    with application.app_context():
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()
    shutil.rmtree(_TMP_DIR, ignore_errors=True)


@pytest.fixture()
def app(_app):
    with _app.app_context():
        db.session.rollback()
        db.session.remove()
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()
        _seed_roles()
        yield _app
        db.session.rollback()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def make_user(app):
    sequence = count(1)

    def _make(role='Student', *, username=None, email=None, password='secret123',
              approved=True, with_profile=True, full_name=None):
        number = next(sequence)
        role_obj = Role.query.filter_by(name=role).first()
        assert role_obj is not None, f'Unknown role: {role}'

        user = User(
            username=username or f'user{number}',
            full_name=full_name or f'Test User {number}',
            email=(email or f'user{number}@example.com').lower(),
            role_id=role_obj.id,
            is_approved=approved,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        if with_profile:
            db.session.add(UserProfile(user_id=user.id))

        db.session.commit()
        return user

    return _make


@pytest.fixture()
def auth(client):
    class Auth:
        def login(self, user, password='secret123'):
            # Make sure a previously logged-in user is signed out first.
            client.post('/logout')
            response = client.post(
                '/login',
                data={'email': user.email, 'password': password},
            )
            assert response.status_code == 302, 'Login failed'
            return response

        def logout(self):
            return client.post('/logout')

    return Auth()


@pytest.fixture()
def make_course(app, make_user):
    sequence = count(1)

    def _make(teacher=None, *, published=True, price=0.0, lessons=1,
              quiz=False, assignment=False, category='Programming'):
        number = next(sequence)
        teacher = teacher or make_user(role='Teacher')

        category_obj = Category.query.filter_by(name=category).first()
        if category_obj is None:
            category_obj = Category(name=category, slug=f'category-{number}')
            db.session.add(category_obj)
            db.session.flush()

        course = Course(
            title=f'Test Course {number}',
            slug=f'test-course-{number}',
            description='A course created by the test suite.',
            teacher_id=teacher.id,
            category_id=category_obj.id,
            price=price,
            is_published=published,
            difficulty_level='Beginner',
        )

        module = Module(title=f'Module {number}', sort_order=1)
        course.modules.append(module)

        lesson_objects = []
        for index in range(1, lessons + 1):
            lesson_objects.append(Lesson(
                module=module,
                title=f'Lesson {index}',
                content_type='text',
                text_content=f'Content for lesson {index}',
                sort_order=index,
            ))

        data = SimpleNamespace(
            course=course,
            teacher=teacher,
            module=module,
            lessons=lesson_objects,
            quiz=None,
            question=None,
            choices=[],
            assignment=None,
        )

        if quiz:
            quiz_obj = Quiz(course=course, title=f'Quiz {number}', passing_score=60)
            question = Question(
                quiz=quiz_obj,
                text='What is 2 + 2?',
                question_type='MCQ',
                points=10,
            )
            correct = Choice(question=question, text='4', is_correct=True)
            wrong = Choice(question=question, text='5', is_correct=False)
            data.quiz = quiz_obj
            data.question = question
            data.choices = [correct, wrong]

        if assignment:
            data.assignment = Assignment(
                course=course,
                title=f'Assignment {number}',
                description='Complete the exercise.',
                max_marks=100,
                due_date=datetime.utcnow() + timedelta(days=7),
            )

        db.session.add(course)
        db.session.commit()
        return data

    return _make


@pytest.fixture()
def enroll(app):
    def _enroll(student, course, completed=()):
        completed_ids = {getattr(item, 'id', item) for item in completed}

        enrollment = Enrollment(student_id=student.id, course_id=course.id)
        db.session.add(enrollment)
        db.session.flush()

        for module in course.modules:
            for lesson in module.lessons:
                db.session.add(LessonProgress(
                    enrollment_id=enrollment.id,
                    lesson_id=lesson.id,
                    is_completed=lesson.id in completed_ids,
                ))

        db.session.commit()
        return enrollment

    return _enroll
