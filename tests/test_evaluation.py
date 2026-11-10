from database import db
from models.evaluation import Evaluation, EvaluationSubmission


def _make_evaluation(course, teacher, **overrides):
    data = {
        'course_id': course.id,
        'title': 'Midterm Evaluation',
        'eval_type': 'test_paper',
        'max_score': 100.0,
        'created_by': teacher.id,
    }
    data.update(overrides)
    evaluation = Evaluation(**data)
    db.session.add(evaluation)
    db.session.commit()
    return evaluation


def _make_submission(evaluation, student, **overrides):
    data = {
        'evaluation_id': evaluation.id,
        'student_id': student.id,
        'file_url': 'https://example.com/answer.pdf',
        'notes': 'My submission',
    }
    data.update(overrides)
    submission = EvaluationSubmission(**data)
    db.session.add(submission)
    db.session.commit()
    return submission


def test_student_cannot_list_evaluations_for_unenrolled_course(
    client, auth, make_user, make_course
):
    student = make_user()
    data = make_course()
    evaluation = _make_evaluation(data.course, data.teacher)
    auth.login(student)

    response = client.get(f'/courses/{data.course.id}/evaluations')

    assert response.status_code == 403
    assert evaluation.title.encode() not in response.data


def test_enrolled_student_can_list_evaluations(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course()
    evaluation = _make_evaluation(data.course, data.teacher)
    enroll(student, data.course)
    auth.login(student)

    response = client.get(f'/courses/{data.course.id}/evaluations')

    assert response.status_code == 200
    assert evaluation.title.encode() in response.data


def test_teacher_cannot_grade_submission_from_another_evaluation(
    client, auth, make_user, make_course
):
    first_student = make_user()
    first_course = make_course()
    first_evaluation = _make_evaluation(first_course.course, first_course.teacher)
    first_submission = _make_submission(first_evaluation, first_student)

    second_student = make_user()
    second_course = make_course()
    second_evaluation = _make_evaluation(second_course.course, second_course.teacher)
    second_submission = _make_submission(second_evaluation, second_student)

    auth.login(first_course.teacher)
    response = client.post(
        f'/evaluations/{first_evaluation.id}/grade',
        data={'submission_id': second_submission.id, 'score': '100'},
    )

    assert response.status_code == 404
    assert db.session.get(EvaluationSubmission, second_submission.id).score is None
    assert db.session.get(EvaluationSubmission, first_submission.id).score is None


def test_evaluation_score_is_clamped_to_valid_range(
    client, auth, make_user, make_course
):
    student = make_user()
    data = make_course()
    evaluation = _make_evaluation(data.course, data.teacher, max_score=50.0)
    submission = _make_submission(evaluation, student)
    auth.login(data.teacher)

    below = client.post(
        f'/evaluations/{evaluation.id}/grade',
        data={'submission_id': submission.id, 'score': '-25'},
    )
    assert below.status_code == 302
    assert db.session.get(EvaluationSubmission, submission.id).score == 0.0

    above = client.post(
        f'/evaluations/{evaluation.id}/grade',
        data={'submission_id': submission.id, 'score': '500'},
    )
    assert above.status_code == 302
    assert db.session.get(EvaluationSubmission, submission.id).score == 50.0
