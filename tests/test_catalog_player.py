from database import db
from models.learning import Assignment


def test_catalog_search_filters_by_keyword(client, make_course):
    algebra = make_course(published=True)
    history = make_course(published=True)
    algebra.course.title = 'Algebra Basics'
    history.course.title = 'World History'
    db.session.commit()

    response = client.get('/courses?q=Algebra')

    assert response.status_code == 200
    assert b'Algebra Basics' in response.data
    assert b'World History' not in response.data


def test_catalog_paginates_and_keeps_filters(client, make_course):
    for _ in range(10):
        make_course(published=True)

    response = client.get('/courses?sort=title')

    assert response.status_code == 200
    assert b'Showing 1' in response.data
    assert b'page=2' in response.data
    assert b'sort=title' in response.data


def test_catalog_empty_state_for_unknown_search(client):
    response = client.get('/courses?q=does-not-exist')

    assert response.status_code == 200
    assert b'No courses found' in response.data


def test_player_shows_previous_and_next_lesson_links(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course(lessons=2)
    enroll(student, data.course)
    auth.login(student)

    response = client.get(
        f'/courses/{data.course.slug}/player?lesson_id={data.lessons[0].id}'
    )

    assert response.status_code == 200
    assert b'Next:' in response.data
    assert data.lessons[1].title.encode() in response.data


def test_player_rejects_lesson_from_another_course(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    enrolled = make_course(lessons=1)
    other = make_course(lessons=1)
    enroll(student, enrolled.course)
    auth.login(student)

    response = client.get(
        f'/courses/{enrolled.course.slug}/player'
        f'?lesson_id={other.lessons[0].id}'
    )

    assert response.status_code == 404


def test_player_certificate_tab_uses_real_progress_not_fake_button(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course(lessons=1)
    enroll(student, data.course)
    auth.login(student)

    response = client.get(
        f'/courses/{data.course.slug}/player?lesson_id={data.lessons[0].id}'
    )

    assert response.status_code == 200
    assert b'Current progress' in response.data
    assert b'Refresh & Claim Certificate' not in response.data


def test_create_assignment_saves_late_submission_setting(
    client, auth, make_course
):
    data = make_course()
    auth.login(data.teacher)

    response = client.post(
        f'/courses/{data.course.id}/assignment/create',
        data={
            'title': 'Essay',
            'description': 'Write an essay.',
            'max_marks': '50',
            'due_date': '2027-01-01T12:00',
            # checkbox omitted => late submissions disabled
        },
    )

    assert response.status_code == 302
    assignment = Assignment.query.filter_by(title='Essay').one()
    assert assignment.max_marks == 50
    assert assignment.allow_late_submission is False


def test_create_assignment_rejects_invalid_marks(
    client, auth, make_course
):
    data = make_course()
    auth.login(data.teacher)

    response = client.post(
        f'/courses/{data.course.id}/assignment/create',
        data={
            'title': 'Bad marks',
            'description': 'Invalid.',
            'max_marks': 'abc',
            'due_date': '2027-01-01T12:00',
        },
    )

    assert response.status_code == 302
    assert Assignment.query.filter_by(title='Bad marks').first() is None


def test_create_assignment_rejects_invalid_due_date(
    client, auth, make_course
):
    data = make_course()
    auth.login(data.teacher)

    response = client.post(
        f'/courses/{data.course.id}/assignment/create',
        data={
            'title': 'Bad date',
            'description': 'Invalid.',
            'max_marks': '10',
            'due_date': 'not-a-date',
        },
    )

    assert response.status_code == 302
    assert Assignment.query.filter_by(title='Bad date').first() is None
