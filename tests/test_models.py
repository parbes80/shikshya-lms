from datetime import datetime, timedelta

from database import db
from models.interaction import Certificate, Notification, PasswordResetToken
from models.learning import QuizAttempt, Submission
from routes.api import _update_course_progress


def test_password_is_hashed(app, make_user):
    user = make_user(password='plain-text-secret')

    assert user.password_hash != 'plain-text-secret'
    assert user.check_password('plain-text-secret')
    assert not user.check_password('wrong-password')


def test_password_reset_token_expiry(app, make_user):
    user = make_user()
    expired = PasswordResetToken(
        user_id=user.id,
        token='expired-token',
        expires_at=datetime.utcnow() - timedelta(minutes=1),
    )
    valid = PasswordResetToken(
        user_id=user.id,
        token='valid-token',
        expires_at=datetime.utcnow() + timedelta(minutes=1),
    )

    assert expired.is_expired()
    assert not valid.is_expired()


def test_course_progress_counts_all_item_types(app, make_user, make_course, enroll):
    student = make_user()
    data = make_course(lessons=2, quiz=True, assignment=True)
    enrollment = enroll(student, data.course)

    # Complete both lessons, pass the quiz and submit the assignment.
    for progress in enrollment.lesson_progresses:
        progress.is_completed = True

    db.session.add(QuizAttempt(
        quiz_id=data.quiz.id,
        student_id=student.id,
        score=100.0,
        is_passed=True,
    ))
    db.session.add(Submission(
        assignment_id=data.assignment.id,
        student_id=student.id,
        file_url='uploads/assignments/solution.pdf',
    ))
    db.session.commit()

    _update_course_progress(enrollment)

    assert enrollment.progress_percent == 100.0
    assert enrollment.is_completed is True
    assert enrollment.completed_at is not None

    certificate = Certificate.query.filter_by(
        student_id=student.id, course_id=data.course.id
    ).first()
    assert certificate is not None
    assert certificate.unique_code

    notification = Notification.query.filter_by(
        user_id=student.id, title='Course Completed! 🎓'
    ).first()
    assert notification is not None


def test_course_progress_partial_completion(app, make_user, make_course, enroll):
    student = make_user()
    data = make_course(lessons=2, quiz=True, assignment=True)
    enrollment = enroll(student, data.course, completed=[data.lessons[0]])

    _update_course_progress(enrollment)

    # 1 of 4 items (2 lessons, 1 quiz, 1 assignment) is complete.
    assert enrollment.progress_percent == 25.0
    assert enrollment.is_completed is False
    assert Certificate.query.count() == 0


def test_course_progress_without_items_is_zero(app, make_user, make_course, enroll):
    student = make_user()
    data = make_course(lessons=0)
    enrollment = enroll(student, data.course)

    _update_course_progress(enrollment)

    assert enrollment.progress_percent == 0.0
    assert enrollment.is_completed is False
