from database import db
from models.interaction import (
    DiscussionTopic,
    Notification,
)
from models.learning import QuizAttempt, Submission


def test_api_requires_login(client):
    for url in ('/api/ai/chat', '/api/notifications'):
        response = client.get(url) if url == '/api/notifications' else client.post(url, json={})
        assert response.status_code == 302
        assert '/login' in response.headers['Location']


def test_ai_chat_replies_to_greeting(client, auth, make_user):
    user = make_user()
    auth.login(user)

    response = client.post('/api/ai/chat', json={'message': 'hello there'})

    assert response.status_code == 200
    assert user.username in response.get_json()['reply']


def test_ai_chat_handles_empty_and_topic_messages(client, auth, make_user):
    auth.login(make_user())

    empty = client.post('/api/ai/chat', json={}).get_json()['reply']
    python = client.post('/api/ai/chat', json={'message': 'python'}).get_json()['reply']

    assert 'AI Assistant' in empty
    assert 'Flask' in python


def test_notifications_only_returns_current_users_unread_items(
    client, auth, make_user
):
    student = make_user()
    other = make_user()
    db.session.add_all([
        Notification(user_id=student.id, title='Unread', message='Pay attention'),
        Notification(user_id=student.id, title='Read', message='Old', is_read=True),
        Notification(user_id=other.id, title='Other', message='Not yours'),
    ])
    db.session.commit()
    auth.login(student)

    response = client.get('/api/notifications')
    payload = response.get_json()

    assert response.status_code == 200
    assert [item['title'] for item in payload] == ['Unread']


def test_notification_can_be_marked_read(client, auth, make_user):
    student = make_user()
    notification = Notification(
        user_id=student.id, title='Unread', message='Read me'
    )
    db.session.add(notification)
    db.session.commit()
    auth.login(student)

    response = client.post(f'/api/notifications/{notification.id}/read')

    assert response.status_code == 200
    assert response.get_json()['success'] is True
    assert db.session.get(Notification, notification.id).is_read is True


def test_cannot_mark_another_users_notification_read(client, auth, make_user):
    student = make_user()
    other = make_user()
    notification = Notification(
        user_id=other.id, title='Other', message='Not yours'
    )
    db.session.add(notification)
    db.session.commit()
    auth.login(student)

    response = client.post(f'/api/notifications/{notification.id}/read')

    assert response.status_code == 404


def test_video_progress_requires_lesson_id(client, auth, make_user):
    auth.login(make_user())

    response = client.post('/api/progress/video', json={})

    assert response.status_code == 400
    assert response.get_json()['error'] == 'lesson_id required'


def test_video_progress_requires_enrollment(client, auth, make_user, make_course):
    student = make_user()
    data = make_course()
    auth.login(student)

    response = client.post(
        '/api/progress/video',
        json={'lesson_id': data.lessons[0].id, 'seconds': 10},
    )

    assert response.status_code == 404


def test_video_progress_completes_single_lesson_course(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course(lessons=1)
    enrollment = enroll(student, data.course)
    auth.login(student)

    response = client.post(
        '/api/progress/video',
        json={
            'lesson_id': data.lessons[0].id,
            'seconds': 120,
            'is_completed': True,
        },
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload['success'] is True
    assert payload['progress_percent'] == 100.0
    assert payload['is_completed'] is True
    assert db.session.get(type(enrollment), enrollment.id).is_completed is True


def test_quiz_submission_scores_answers_and_records_attempt(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course(quiz=True)
    enroll(student, data.course)
    auth.login(student)

    correct_choice = next(choice for choice in data.choices if choice.is_correct)
    response = client.post('/api/quiz/submit', json={
        'quiz_id': data.quiz.id,
        'answers': {str(data.question.id): correct_choice.id},
    })

    payload = response.get_json()
    assert response.status_code == 200
    assert payload['score'] == 100.0
    assert payload['is_passed'] is True
    assert payload['correct_count'] == 1

    attempt = QuizAttempt.query.filter_by(
        quiz_id=data.quiz.id, student_id=student.id
    ).first()
    assert attempt is not None
    assert attempt.score == 100.0
    assert attempt.is_passed is True
    assert Notification.query.filter_by(
        user_id=student.id, title='Quiz Completed!'
    ).count() == 1


def test_quiz_submission_marks_wrong_answers_as_failed(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course(quiz=True)
    enroll(student, data.course)
    auth.login(student)

    wrong_choice = next(choice for choice in data.choices if not choice.is_correct)
    response = client.post('/api/quiz/submit', json={
        'quiz_id': data.quiz.id,
        'answers': {str(data.question.id): wrong_choice.id},
    })

    payload = response.get_json()
    assert response.status_code == 200
    assert payload['score'] == 0.0
    assert payload['is_passed'] is False


def test_quiz_submission_requires_quiz_id(client, auth, make_user):
    auth.login(make_user())

    response = client.post('/api/quiz/submit', json={})

    assert response.status_code == 400


def test_quiz_submission_requires_enrollment(client, auth, make_user, make_course):
    student = make_user()
    data = make_course(quiz=True)
    auth.login(student)

    response = client.post('/api/quiz/submit', json={
        'quiz_id': data.quiz.id,
        'answers': {str(data.question.id): data.choices[0].id},
    })

    assert response.status_code == 403
    assert 'not enrolled' in response.get_json()['error']
    assert QuizAttempt.query.filter_by(
        quiz_id=data.quiz.id, student_id=student.id
    ).count() == 0


def test_quiz_submission_rejects_other_courses_quiz(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    enrolled_course = make_course(quiz=True)
    other_course = make_course(quiz=True)
    enroll(student, enrolled_course.course)
    auth.login(student)

    response = client.post('/api/quiz/submit', json={
        'quiz_id': other_course.quiz.id,
        'answers': {str(other_course.question.id): other_course.choices[0].id},
    })

    assert response.status_code == 403
    assert 'correct_choice_text' not in response.get_json()
    assert QuizAttempt.query.filter_by(
        quiz_id=other_course.quiz.id, student_id=student.id
    ).count() == 0


def test_quiz_submission_rejects_teacher_attempts(
    client, auth, make_user, make_course
):
    data = make_course(quiz=True)
    teacher = make_user(role='Teacher')
    auth.login(teacher)

    response = client.post('/api/quiz/submit', json={
        'quiz_id': data.quiz.id,
        'answers': {},
    })

    assert response.status_code == 403
    assert QuizAttempt.query.filter_by(
        quiz_id=data.quiz.id, student_id=teacher.id
    ).count() == 0


def test_quiz_submission_ignores_malformed_answer_ids(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course(quiz=True)
    enroll(student, data.course)
    auth.login(student)

    response = client.post('/api/quiz/submit', json={
        'quiz_id': data.quiz.id,
        'answers': {str(data.question.id): 'not-a-choice-id'},
    })

    assert response.status_code == 200
    assert response.get_json()['score'] == 0.0


def test_quiz_retry_limit_is_enforced(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course(quiz=True)
    data.quiz.max_attempts = 1
    enroll(student, data.course)
    db.session.add(QuizAttempt(
        quiz_id=data.quiz.id,
        student_id=student.id,
        score=50.0,
        is_passed=False,
    ))
    db.session.commit()
    auth.login(student)

    response = client.post('/api/quiz/submit', json={
        'quiz_id': data.quiz.id,
        'answers': {},
    })

    assert response.status_code == 403
    assert 'Maximum 1 attempt' in response.get_json()['error']


def test_lesson_gated_quiz_requires_completed_lesson(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course(quiz=True)
    data.quiz.lesson_id = data.lessons[0].id
    enroll(student, data.course)
    db.session.commit()
    auth.login(student)

    response = client.post('/api/quiz/submit', json={
        'quiz_id': data.quiz.id,
        'answers': {},
    })

    assert response.status_code == 403
    assert 'Complete the lesson first' in response.get_json()['error']


def test_enrolled_student_can_create_discussion_topic(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course()
    enroll(student, data.course)
    auth.login(student)

    response = client.post('/api/discussions/create', data={
        'course_id': data.course.id,
        'title': 'Help with lesson one',
        'content': 'I am stuck on the first exercise.',
    })

    payload = response.get_json()
    assert response.status_code == 200
    assert payload['success'] is True
    assert payload['author'] == student.username
    assert DiscussionTopic.query.filter_by(course_id=data.course.id).count() == 1


def test_discussion_creation_requires_enrollment_or_teaching(
    client, auth, make_user, make_course
):
    student = make_user()
    data = make_course()
    auth.login(student)

    response = client.post('/api/discussions/create', data={
        'course_id': data.course.id,
        'title': 'Not enrolled',
        'content': 'Should fail',
    })

    assert response.status_code == 403


def test_discussion_creation_requires_fields(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course()
    enroll(student, data.course)
    auth.login(student)

    response = client.post('/api/discussions/create', data={'course_id': data.course.id})

    assert response.status_code == 400


def test_reply_notifies_topic_author(
    client, auth, make_user, make_course, enroll
):
    author = make_user()
    responder = make_user()
    data = make_course()
    enroll(author, data.course)
    enroll(responder, data.course)
    topic = DiscussionTopic(
        course_id=data.course.id,
        user_id=author.id,
        title='A question',
        content='Explain this please',
    )
    db.session.add(topic)
    db.session.commit()
    auth.login(responder)

    response = client.post(f'/api/discussions/{topic.id}/reply', data={
        'content': 'Here is an explanation.'
    })

    assert response.status_code == 200
    assert response.get_json()['author'] == responder.username
    assert Notification.query.filter_by(user_id=author.id).count() == 1


def test_reply_requires_enrollment_or_course_ownership(
    client, auth, make_user, make_course
):
    author = make_user()
    outsider = make_user()
    data = make_course()
    topic = DiscussionTopic(
        course_id=data.course.id,
        user_id=author.id,
        title='A question',
        content='Explain this please',
    )
    db.session.add(topic)
    db.session.commit()
    auth.login(outsider)

    response = client.post(f'/api/discussions/{topic.id}/reply', data={
        'content': 'Trying to post from another course.'
    })

    assert response.status_code == 403
    assert db.session.get(DiscussionTopic, topic.id).replies == []
    assert Notification.query.filter_by(user_id=author.id).count() == 0


def test_course_teacher_can_reply_without_enrollment(
    client, auth, make_user, make_course
):
    author = make_user()
    data = make_course()
    topic = DiscussionTopic(
        course_id=data.course.id,
        user_id=author.id,
        title='A question',
        content='Explain this please',
    )
    db.session.add(topic)
    db.session.commit()
    auth.login(data.teacher)

    response = client.post(f'/api/discussions/{topic.id}/reply', data={
        'content': 'Teacher response.'
    })

    assert response.status_code == 200
    assert response.get_json()['author'] == data.teacher.username


def test_assignment_submission_requires_enrollment(
    client, auth, make_user, make_course
):
    student = make_user()
    data = make_course(assignment=True)
    auth.login(student)

    response = client.post(
        f'/api/assignments/{data.assignment.id}/submit',
        data={'file_url': 'https://example.com/solution.py'},
    )

    assert response.status_code == 403


def test_assignment_submission_requires_file_or_url(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course(assignment=True)
    enroll(student, data.course)
    auth.login(student)

    response = client.post(
        f'/api/assignments/{data.assignment.id}/submit', data={}
    )

    assert response.status_code == 400


def test_assignment_submission_creates_record_and_notifies_teacher(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course(assignment=True)
    enroll(student, data.course)
    auth.login(student)

    response = client.post(
        f'/api/assignments/{data.assignment.id}/submit',
        data={'file_url': 'https://example.com/solution.py'},
    )

    assert response.status_code == 200
    assert response.get_json()['success'] is True

    submission = Submission.query.filter_by(
        assignment_id=data.assignment.id, student_id=student.id
    ).first()
    assert submission is not None
    assert submission.file_url == 'https://example.com/solution.py'
    assert Notification.query.filter_by(user_id=data.teacher.id).count() == 1


def test_teacher_can_grade_submission(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course(assignment=True)
    enroll(student, data.course)
    submission = Submission(
        assignment_id=data.assignment.id,
        student_id=student.id,
        file_url='https://example.com/solution.py',
    )
    db.session.add(submission)
    db.session.commit()
    auth.login(data.teacher)

    response = client.post(
        f'/submissions/{submission.id}/grade',
        data={'marks': '92', 'feedback': 'Well done'},
    )

    assert response.status_code == 302
    refreshed = db.session.get(Submission, submission.id)
    assert refreshed.is_graded is True
    assert refreshed.marks_obtained == 92.0
    assert refreshed.feedback == 'Well done'


def test_other_teacher_and_students_cannot_grade_submission(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course(assignment=True)
    enroll(student, data.course)
    submission = Submission(
        assignment_id=data.assignment.id,
        student_id=student.id,
        file_url='https://example.com/solution.py',
    )
    db.session.add(submission)
    db.session.commit()

    other_teacher = make_user(role='Teacher')
    auth.login(other_teacher)
    other_teacher_response = client.post(
        f'/submissions/{submission.id}/grade', data={'marks': '10'}
    )

    auth.login(student)
    student_response = client.post(
        f'/submissions/{submission.id}/grade', data={'marks': '10'}
    )

    assert other_teacher_response.status_code == 403
    assert student_response.status_code == 403
    assert db.session.get(Submission, submission.id).is_graded is False


def test_assignment_text_only_submission_stores_content(
    client, auth, make_user, make_course, enroll
):
    from datetime import datetime, timedelta

    student = make_user()
    data = make_course(assignment=True)
    data.assignment.due_date = datetime.utcnow() + timedelta(days=2)
    db.session.commit()
    enroll(student, data.course)
    auth.login(student)

    response = client.post(
        f'/api/assignments/{data.assignment.id}/submit',
        data={'text_content': 'My written answer.'},
    )

    assert response.status_code == 200
    submission = Submission.query.filter_by(
        assignment_id=data.assignment.id, student_id=student.id
    ).first()
    assert submission is not None
    assert submission.text_content == 'My written answer.'
    assert not submission.file_url
    assert submission.is_late is False


def test_assignment_late_submission_rejected_when_disabled(
    client, auth, make_user, make_course, enroll
):
    from datetime import datetime, timedelta

    student = make_user()
    data = make_course(assignment=True)
    data.assignment.due_date = datetime.utcnow() - timedelta(days=1)
    data.assignment.allow_late_submission = False
    db.session.commit()
    enroll(student, data.course)
    auth.login(student)

    response = client.post(
        f'/api/assignments/{data.assignment.id}/submit',
        data={'text_content': 'Too late.'},
    )

    assert response.status_code == 400
    assert Submission.query.filter_by(
        assignment_id=data.assignment.id, student_id=student.id
    ).first() is None


def test_assignment_late_submission_allowed_and_flagged(
    client, auth, make_user, make_course, enroll
):
    from datetime import datetime, timedelta

    student = make_user()
    data = make_course(assignment=True)
    data.assignment.due_date = datetime.utcnow() - timedelta(days=1)
    data.assignment.allow_late_submission = True
    db.session.commit()
    enroll(student, data.course)
    auth.login(student)

    response = client.post(
        f'/api/assignments/{data.assignment.id}/submit',
        data={'text_content': 'Late but allowed.'},
    )

    assert response.status_code == 200
    submission = Submission.query.filter_by(
        assignment_id=data.assignment.id, student_id=student.id
    ).first()
    assert submission is not None
    assert submission.is_late is True


def test_grade_submission_clamps_marks_to_max(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course(assignment=True)
    enroll(student, data.course)
    submission = Submission(
        assignment_id=data.assignment.id,
        student_id=student.id,
        text_content='Answer',
    )
    db.session.add(submission)
    db.session.commit()
    auth.login(data.teacher)

    response = client.post(
        f'/submissions/{submission.id}/grade',
        data={'marks': '999', 'feedback': 'Too generous'},
    )

    assert response.status_code == 302
    refreshed = db.session.get(Submission, submission.id)
    assert refreshed.is_graded is True
    assert refreshed.marks_obtained == float(data.assignment.max_marks)


def test_grade_submission_rejects_non_numeric_marks(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course(assignment=True)
    enroll(student, data.course)
    submission = Submission(
        assignment_id=data.assignment.id,
        student_id=student.id,
        text_content='Answer',
    )
    db.session.add(submission)
    db.session.commit()
    auth.login(data.teacher)

    response = client.post(
        f'/submissions/{submission.id}/grade',
        data={'marks': 'not-a-number'},
    )

    assert response.status_code == 302
    assert db.session.get(Submission, submission.id).is_graded is False
