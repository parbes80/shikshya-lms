import io
from pathlib import Path

from database import db
from models.course import Lesson
from models.evaluation import Evaluation
from models.interaction import Lab, PasswordResetRequest
from models.learning import LiveClass, Submission


def _upload(name, content=b'data'):
    return io.BytesIO(content), name


def test_lesson_html_is_sanitized_before_storage(client, auth, make_course):
    data = make_course()
    auth.login(data.teacher)

    response = client.post(
        f'/modules/{data.module.id}/add-lesson',
        data={
            'lesson_title': 'Unsafe lesson',
            'content_type': 'text',
            'duration': '5',
            'text_content': (
                '<h2>Safe heading</h2>'
                '<script>alert(1337)</script>'
                '<img src="x" onerror="alert(1337)">'
            ),
        },
    )

    assert response.status_code == 302
    lesson = Lesson.query.filter_by(title='Unsafe lesson').one()
    assert '<h2' in lesson.text_content
    assert '<script' not in lesson.text_content.lower()
    assert 'onerror' not in lesson.text_content.lower()


def test_course_player_sanitizes_legacy_unsafe_html(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course()
    lesson = data.lessons[0]
    lesson.text_content = (
        '<p>Welcome</p><script>alert(1337)</script>'
        '<img src="x" onerror="alert(1337)">'
    )
    db.session.commit()
    enroll(student, data.course)
    auth.login(student)

    response = client.get(
        f'/courses/{data.course.slug}/player?lesson_id={lesson.id}'
    )

    assert response.status_code == 200
    assert b'Welcome' in response.data
    assert b'alert(1337)' not in response.data
    assert b'<script>alert(1337)</script>' not in response.data


def test_markdown_filter_escapes_scripts_and_unsafe_links(app):
    render = app.jinja_env.filters['markdown']

    rendered = render(
        'Hello <script>alert(1337)</script>\n\n'
        '[click](javascript:alert(1337))'
    )

    assert '<script' not in rendered.lower()
    assert 'javascript:' not in rendered.lower()
    assert 'alert(1337)' not in rendered


def test_markdown_lessons_keep_markdown_source():
    from utils.sanitize import sanitize_rich_content

    source = '# Heading\n\n> A quote\n\n```python\nprint("hi")\n```'
    assert sanitize_rich_content(source) == source


def test_safe_url_rejects_obfuscated_javascript_schemes():
    from utils.sanitize import safe_url

    assert safe_url('javascript:alert(1)') == ''
    assert safe_url('java\nscript:alert(1)') == ''
    assert safe_url('  JAVASCRIPT:alert(1)') == ''
    assert safe_url('data:text/html,<script>alert(1)</script>') == ''
    assert safe_url('https://example.com/file.pdf') == 'https://example.com/file.pdf'
    assert safe_url('uploads/documents/file.pdf') == 'uploads/documents/file.pdf'


def test_lab_html_is_sanitized(client, auth, make_user):
    admin = make_user(role='Admin')
    auth.login(admin)

    response = client.post(
        '/labs/create',
        data={
            'title': 'Unsafe lab',
            'content': '<p>Lab</p><script>alert(1337)</script>',
            'is_published': 'on',
        },
    )

    assert response.status_code == 302
    lab = Lab.query.filter_by(title='Unsafe lab').one()
    assert '<p>' in lab.content
    assert '<script' not in lab.content.lower()


def test_lab_html_is_sanitized_when_rendering(client, auth, make_user):
    admin = make_user(role='Admin')
    lab = Lab(
        title='Legacy unsafe lab',
        description='Legacy',
        content='<p>Safe</p><script>alert(1337)</script>',
        is_published=True,
        created_by=admin.id,
    )
    db.session.add(lab)
    db.session.commit()

    response = client.get(f'/labs/{lab.id}')

    assert response.status_code == 200
    assert b'Safe' in response.data
    assert b'alert(1337)' not in response.data


def test_lesson_document_download_requires_course_access(
    client, auth, make_user, make_course, enroll, app
):
    data = make_course()
    lesson = data.lessons[0]
    lesson.document_url = 'uploads/documents/notes.pdf'
    db.session.commit()

    directory = Path(app.config['UPLOAD_FOLDER']) / 'documents'
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'notes.pdf').write_bytes(b'%PDF-1.4 test')

    outsider = make_user()
    auth.login(outsider)
    assert client.get(f'/api/lessons/{lesson.id}/download').status_code == 403

    enroll(outsider, data.course)
    allowed = client.get(f'/api/lessons/{lesson.id}/download')
    assert allowed.status_code == 200
    assert allowed.data == b'%PDF-1.4 test'


def test_lesson_document_download_rejects_untrusted_external_url(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course()
    lesson = data.lessons[0]
    lesson.document_url = 'http://169.254.169.254/latest/meta-data/'
    db.session.commit()
    enroll(student, data.course)
    auth.login(student)

    response = client.get(f'/api/lessons/{lesson.id}/download')

    assert response.status_code == 400


def test_lesson_document_download_rejects_path_traversal(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course()
    lesson = data.lessons[0]
    lesson.document_url = 'uploads/../../config.py'
    db.session.commit()
    enroll(student, data.course)
    auth.login(student)

    response = client.get(f'/api/lessons/{lesson.id}/download')

    assert response.status_code == 404


def test_lesson_document_download_redirects_trusted_cloudinary(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course()
    lesson = data.lessons[0]
    lesson.document_url = (
        'https://res.cloudinary.com/demo/raw/upload/v1/lesson_notes.pdf'
    )
    db.session.commit()
    enroll(student, data.course)
    auth.login(student)

    response = client.get(f'/api/lessons/{lesson.id}/download')

    assert response.status_code == 302
    assert response.headers['Location'].startswith(
        'https://res.cloudinary.com/'
    )


def test_assignment_upload_rejects_html(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course(assignment=True)
    enroll(student, data.course)
    auth.login(student)

    response = client.post(
        f'/api/assignments/{data.assignment.id}/submit',
        data={'submission_file': _upload('evil.html', b'<script>alert(1)</script>')},
        content_type='multipart/form-data',
    )

    assert response.status_code == 400
    assert 'not allowed' in response.get_json()['error']
    assert Submission.query.filter_by(student_id=student.id).count() == 0


def test_assignment_upload_accepts_pdf(
    client, auth, make_user, make_course, enroll, app
):
    student = make_user()
    data = make_course(assignment=True)
    enroll(student, data.course)
    auth.login(student)

    response = client.post(
        f'/api/assignments/{data.assignment.id}/submit',
        data={'submission_file': _upload('answer.pdf', b'%PDF-1.4 answer')},
        content_type='multipart/form-data',
    )

    assert response.status_code == 200
    submission = Submission.query.filter_by(student_id=student.id).one()
    assert submission.file_url.startswith('uploads/assignments/')
    stored = Path(app.config['UPLOAD_FOLDER']) / submission.file_url[len('uploads/'):]
    assert stored.exists()


def test_lesson_document_upload_rejects_html(client, auth, make_course):
    data = make_course()
    auth.login(data.teacher)

    response = client.post(
        f'/modules/{data.module.id}/add-lesson',
        data={
            'lesson_title': 'Bad document',
            'content_type': 'document',
            'duration': '5',
            'document_file': _upload('notes.html', b'<script>alert(1)</script>'),
        },
        content_type='multipart/form-data',
    )

    assert response.status_code == 302
    assert Lesson.query.filter_by(title='Bad document').count() == 0


def test_lab_upload_rejects_html(client, auth, make_user):
    admin = make_user(role='Admin')
    auth.login(admin)

    response = client.post(
        '/labs/create',
        data={
            'title': 'Bad lab upload',
            'pdf_file': _upload('payload.html', b'<script>alert(1)</script>'),
        },
        content_type='multipart/form-data',
    )

    assert response.status_code == 302
    assert Lab.query.filter_by(title='Bad lab upload').count() == 0


def test_live_class_meet_link_is_sanitized(
    client, auth, make_user, make_course
):
    teacher = make_user(role='Teacher')
    data = make_course(teacher=teacher)
    auth.login(teacher)

    response = client.post(
        f'/courses/{data.course.id}/live-class/create',
        data={
            'title': 'Unsafe live class',
            'meet_link': 'javascript:alert(1)',
            'date': '2030-01-01',
            'time': '10:00',
            'duration_minutes': '60',
        },
    )

    assert response.status_code == 302
    live_class = LiveClass.query.filter_by(title='Unsafe live class').one()
    assert not live_class.meet_link


def test_state_changing_routes_reject_get(
    client, auth, make_user, make_course
):
    admin = make_user(role='Admin')
    teacher = make_user(role='Teacher')
    data = make_course(teacher=teacher)
    evaluation = Evaluation(
        course_id=data.course.id,
        title='Midterm',
        eval_type='test_paper',
        max_score=100,
        created_by=teacher.id,
    )
    reset_request = PasswordResetRequest(
        user_id=teacher.id, email=teacher.email
    )
    db.session.add_all([evaluation, reset_request])
    db.session.commit()

    auth.login(admin)
    assert client.get(f'/dashboard/admin/approve-teacher/{teacher.id}').status_code == 405
    assert client.get(f'/dashboard/admin/approve-course/{data.course.id}').status_code == 405
    assert client.get(
        f'/admin/approve-reset-request/{reset_request.id}'
    ).status_code == 405

    auth.login(teacher)
    assert client.get(f'/evaluations/{evaluation.id}/publish').status_code == 405
    assert client.get(f'/evaluations/{evaluation.id}/unpublish').status_code == 405


def test_publish_results_requires_post(client, auth, make_user, make_course):
    teacher = make_user(role='Teacher')
    data = make_course(teacher=teacher)
    evaluation = Evaluation(
        course_id=data.course.id,
        title='Midterm',
        eval_type='test_paper',
        max_score=100,
        created_by=teacher.id,
    )
    db.session.add(evaluation)
    db.session.commit()
    auth.login(teacher)

    response = client.post(f'/evaluations/{evaluation.id}/publish')

    assert response.status_code == 302
    assert db.session.get(Evaluation, evaluation.id).results_published is True


def test_logout_requires_post(client, auth, make_user):
    user = make_user()
    auth.login(user)

    assert client.get('/logout').status_code == 405
    assert client.post('/logout').status_code == 302


def test_security_headers_are_set(client):
    response = client.get('/')

    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['X-Frame-Options'] == 'SAMEORIGIN'
    assert response.headers['Referrer-Policy'] == 'strict-origin-when-cross-origin'
    assert 'geolocation=()' in response.headers['Permissions-Policy']
    assert 'Content-Security-Policy-Report-Only' in response.headers
    assert "object-src 'none'" in response.headers[
        'Content-Security-Policy-Report-Only'
    ]


def test_session_and_remember_cookie_defaults(app):
    assert app.config['SESSION_PROTECTION'] == 'strong'
    assert app.config['PERMANENT_SESSION_LIFETIME'].total_seconds() == 12 * 3600
    assert app.config['REMEMBER_COOKIE_DURATION'].days == 7
    assert app.config['SESSION_COOKIE_HTTPONLY'] is True
    assert app.config['SESSION_COOKIE_SAMESITE'] == 'Lax'


def test_https_redirect_when_forced(client, app, monkeypatch):
    monkeypatch.setitem(app.config, 'FORCE_HTTPS', True)

    response = client.get('/')

    assert response.status_code == 301
    assert response.headers['Location'].startswith('https://')
