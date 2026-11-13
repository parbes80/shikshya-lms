from database import db
from models.interaction import Certificate


def test_home_page_lists_published_courses(client, make_course):
    data = make_course(published=True)

    response = client.get('/')

    assert response.status_code == 200
    assert b'Shikshya' in response.data
    assert data.course.title.encode() in response.data


def test_home_page_includes_inclusive_sections_and_real_data(client, make_course):
    data = make_course(published=True)

    response = client.get('/')
    body = response.data

    assert response.status_code == 200
    assert b'Who Shikshya is for' in body
    assert b'How it works' in body
    assert b'Frequently asked questions' in body
    assert b'School students' in body
    assert b'College students' in body
    assert b'Independent educators' in body
    assert data.course.title.encode() in body
    # The old hero contained invented activity data.
    assert b'Completed by 85%' not in body


def test_base_layout_has_skip_link_and_footer(client):
    response = client.get('/about')
    body = response.data

    assert response.status_code == 200
    assert b'Skip to main content' in body
    assert b'id="main-content"' in body
    assert b'site-footer' in body


def test_home_page_redirects_authenticated_users_to_their_dashboard(
    client, auth, make_user
):
    student = make_user(role='Student')
    auth.login(student)

    response = client.get('/')

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/dashboard/student')


def test_about_and_contact_pages(client):
    assert client.get('/about').status_code == 200
    assert client.get('/contact').status_code == 200


def test_contact_form_flashes_success(client):
    response = client.post(
        '/contact',
        data={'name': 'Ada', 'subject': 'Courses', 'message': 'Hello!'},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'Thank you, Ada' in response.data


def test_unknown_page_returns_custom_404(client):
    response = client.get('/this-page-does-not-exist')

    assert response.status_code == 404
    assert b'404' in response.data


def test_verify_certificate_endpoint_handles_invalid_code(client):
    response = client.get('/verify/DOES-NOT-EXIST')

    assert response.status_code == 200


def test_verify_certificate_endpoint_accepts_valid_code(client, make_user, make_course):
    student = make_user()
    data = make_course()
    certificate = Certificate(
        unique_code='CERT-TEST-0001',
        student_id=student.id,
        course_id=data.course.id,
        qr_code_data='http://localhost/verify/CERT-TEST-0001',
    )
    db.session.add(certificate)
    db.session.commit()

    response = client.get('/verify/CERT-TEST-0001')

    assert response.status_code == 200
    assert b'CERT-TEST-0001' in response.data
