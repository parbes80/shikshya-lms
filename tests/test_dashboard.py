from database import db
from models.course import Category, Course
from models.interaction import Notification, Payment
from models.learning import Enrollment, LessonProgress
from models.user import User


def test_dashboards_require_login(client):
    for url in ('/dashboard/student', '/dashboard/teacher', '/dashboard/admin'):
        response = client.get(url)
        assert response.status_code == 302
        assert '/login' in response.headers['Location']


def test_each_role_can_open_its_own_dashboard(client, auth, make_user):
    for role, url in (
        ('Student', '/dashboard/student'),
        ('Teacher', '/dashboard/teacher'),
        ('Admin', '/dashboard/admin'),
    ):
        user = make_user(role=role)
        auth.login(user)

        response = client.get(url)

        assert response.status_code == 200, f'{role} could not open {url}'


def test_student_cannot_open_teacher_or_admin_dashboard(
    client, auth, make_user
):
    student = make_user(role='Student')
    auth.login(student)

    teacher_dashboard = client.get('/dashboard/teacher')
    admin_dashboard = client.get('/dashboard/admin')

    assert teacher_dashboard.status_code == 302
    assert teacher_dashboard.headers['Location'].endswith('/')
    assert admin_dashboard.status_code == 302
    assert admin_dashboard.headers['Location'].endswith('/')


def test_teacher_cannot_open_admin_dashboard(client, auth, make_user):
    teacher = make_user(role='Teacher')
    auth.login(teacher)

    response = client.get('/dashboard/admin')

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/')


def test_admin_can_approve_teacher(client, auth, make_user):
    admin = make_user(role='Admin')
    teacher = make_user(role='Teacher', approved=False)
    auth.login(admin)

    response = client.get(f'/dashboard/admin/approve-teacher/{teacher.id}')

    assert response.status_code == 302
    assert db.session.get(User, teacher.id).is_approved is True


def test_admin_can_publish_course_and_notifies_teacher(
    client, auth, make_user, make_course
):
    admin = make_user(role='Admin')
    data = make_course(published=False)
    auth.login(admin)

    response = client.get(
        f'/dashboard/admin/approve-course/{data.course.id}'
    )

    assert response.status_code == 302
    assert db.session.get(Course, data.course.id).is_published is True
    assert Notification.query.filter_by(
        user_id=data.teacher.id, title='Course Approved!'
    ).count() == 1


def test_admin_approves_course_payment_and_enrolls_student(
    client, auth, make_user, make_course
):
    admin = make_user(role='Admin')
    student = make_user()
    data = make_course(lessons=2, price=1500.0)
    payment = Payment(
        student_id=student.id,
        course_id=data.course.id,
        amount=1500.0,
        payment_method='esewa',
        transaction_id='TXN-TEST-001',
        status='pending',
        description='Course purchase',
    )
    db.session.add(payment)
    db.session.commit()
    auth.login(admin)

    response = client.get(f'/dashboard/admin/approve-payment/{payment.id}')

    assert response.status_code == 302
    assert db.session.get(Payment, payment.id).status == 'completed'

    enrollment = Enrollment.query.filter_by(
        student_id=student.id, course_id=data.course.id
    ).first()
    assert enrollment is not None
    assert LessonProgress.query.filter_by(
        enrollment_id=enrollment.id
    ).count() == 2
    assert Notification.query.filter_by(
        user_id=student.id, title='Payment Verified!'
    ).count() == 1


def test_admin_cannot_delete_another_admin(client, auth, make_user):
    admin = make_user(role='Admin')
    other_admin = make_user(role='Admin')
    auth.login(admin)

    response = client.post(f'/dashboard/admin/delete-user/{other_admin.id}')

    assert response.status_code == 302
    assert db.session.get(User, other_admin.id) is not None


def test_admin_can_delete_student(client, auth, make_user):
    admin = make_user(role='Admin')
    student = make_user()
    auth.login(admin)

    response = client.post(f'/dashboard/admin/delete-user/{student.id}')

    assert response.status_code == 302
    assert db.session.get(User, student.id) is None


def test_admin_can_create_category(client, auth, make_user):
    admin = make_user(role='Admin')
    auth.login(admin)

    response = client.post(
        '/dashboard/admin/add-category',
        data={'name': 'Cyber Security', 'icon': 'fa-shield'},
    )

    assert response.status_code == 302

    category = Category.query.filter_by(name='Cyber Security').first()
    assert category is not None
    assert category.slug == 'cyber-security'


def test_only_course_owner_and_admin_can_view_analytics(
    client, auth, make_user, make_course
):
    owner = make_user(role='Teacher')
    other_teacher = make_user(role='Teacher')
    admin = make_user(role='Admin')
    student = make_user()
    data = make_course(teacher=owner, lessons=2)

    auth.login(owner)
    assert client.get(
        f'/dashboard/teacher/analytics/{data.course.id}'
    ).status_code == 200

    auth.login(other_teacher)
    assert client.get(
        f'/dashboard/teacher/analytics/{data.course.id}'
    ).status_code == 403

    auth.login(student)
    assert client.get(
        f'/dashboard/teacher/analytics/{data.course.id}'
    ).status_code == 403

    auth.login(admin)
    assert client.get(
        f'/dashboard/teacher/analytics/{data.course.id}'
    ).status_code == 200


def test_course_owner_can_export_progress_csv(
    client, auth, make_user, make_course, enroll
):
    owner = make_user(role='Teacher')
    student = make_user()
    data = make_course(teacher=owner, lessons=2)
    enroll(student, data.course, completed=[data.lessons[0]])
    auth.login(owner)

    response = client.get(
        f'/dashboard/teacher/analytics/{data.course.id}/export-csv'
    )

    assert response.status_code == 200
    assert response.mimetype == 'text/csv'
    assert b'Student,Email,Progress' in response.data
    assert student.username.encode() in response.data


def test_student_can_view_gradebook(
    client, auth, make_user, make_course, enroll
):
    student = make_user()
    data = make_course(quiz=True, assignment=True)
    enroll(student, data.course)
    auth.login(student)

    response = client.get('/dashboard/student/gradebook')

    assert response.status_code == 200
    assert data.course.title.encode() in response.data
