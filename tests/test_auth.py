from datetime import date, datetime, timedelta

import pytest

from database import db
from models.interaction import PasswordResetRequest, PasswordResetToken
from models.user import User


def _registration_data(**overrides):
    data = {
        'username': 'new_student',
        'full_name': 'New Student',
        'email': 'new_student@example.com',
        'password': 'secret123',
        'role': 'Student',
    }
    data.update(overrides)
    return data


def test_register_student_creates_approved_user_and_profile(client, app):
    response = client.post(
        '/register', data=_registration_data(), follow_redirects=True
    )

    assert response.status_code == 200
    assert b'Registration successful' in response.data

    user = User.query.filter_by(email='new_student@example.com').first()
    assert user is not None
    assert user.role.name == 'Student'
    assert user.is_approved is True
    assert user.full_name == 'New Student'
    assert user.profile is not None
    assert user.check_password('secret123')


def test_register_teacher_requires_admin_approval(client):
    response = client.post(
        '/register',
        data=_registration_data(
            username='new_teacher',
            email='new_teacher@example.com',
            role='Teacher',
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'Waiting for Admin approval' in response.data

    user = User.query.filter_by(email='new_teacher@example.com').first()
    assert user is not None
    assert user.role.name == 'Teacher'
    assert user.is_approved is False


def test_register_cannot_create_admin(client, app):
    response = client.post(
        '/register',
        data=_registration_data(
            username='attacker',
            email='attacker@example.com',
            role='Admin',
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'Invalid role' in response.data
    assert User.query.filter_by(email='attacker@example.com').count() == 0
    assert User.query.filter(User.role.has(name='Admin')).count() == 0


@pytest.mark.parametrize('overrides, message', [
    ({'password': '123'}, b'at least 6 characters'),
    ({'role': 'Wizard'}, b'Invalid role'),
    ({'role': 'Admin'}, b'Invalid role'),
    ({'username': '', 'email': ''}, b'All fields are required'),
])
def test_register_rejects_invalid_input(client, overrides, message):
    response = client.post(
        '/register',
        data=_registration_data(**overrides),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert message in response.data
    assert User.query.count() == 0


def test_register_rejects_duplicate_username_or_email(client, make_user):
    make_user(username='taken', email='taken@example.com')

    response = client.post(
        '/register',
        data=_registration_data(username='another', email='TAKEN@example.com'),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'already registered' in response.data
    assert User.query.filter_by(email='taken@example.com').count() == 1


@pytest.mark.parametrize('role, destination', [
    ('Student', '/dashboard/student'),
    ('Teacher', '/dashboard/teacher'),
    ('Admin', '/dashboard/admin'),
])
def test_login_redirects_by_role(client, make_user, role, destination):
    user = make_user(role=role)

    response = client.post(
        '/login', data={'email': user.email, 'password': 'secret123'}
    )

    assert response.status_code == 302
    assert response.headers['Location'].endswith(destination)


def test_login_tracks_learning_streak(client, make_user):
    user = make_user()

    client.post('/login', data={'email': user.email, 'password': 'secret123'})

    refreshed = db.session.get(User, user.id)
    assert refreshed.streak_count == 1
    assert refreshed.last_activity_date == date.today()


def test_login_rejects_bad_credentials(client, make_user):
    user = make_user()

    wrong_password = client.post(
        '/login',
        data={'email': user.email, 'password': 'not-the-password'},
        follow_redirects=True,
    )
    unknown_email = client.post(
        '/login',
        data={'email': 'nobody@example.com', 'password': 'secret123'},
        follow_redirects=True,
    )

    assert b'Invalid email or password' in wrong_password.data
    assert b'Invalid email or password' in unknown_email.data


def test_logout_clears_session(client, auth, make_user):
    user = make_user()
    auth.login(user)

    response = client.get('/logout')

    assert response.status_code == 302
    protected = client.get('/profile')
    assert protected.status_code == 302
    assert '/login' in protected.headers['Location']


def test_protected_pages_require_login(client):
    response = client.get('/profile')

    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_profile_can_be_updated(client, auth, make_user):
    user = make_user()
    auth.login(user)

    response = client.post(
        '/profile',
        data={
            'username': 'updated_name',
            'email': 'updated@example.com',
            'bio': 'A short bio',
            'qualification': 'BSc',
            'skills': 'Python',
            'website': 'https://example.com',
            'github': 'https://github.com/example',
            'linkedin': 'https://linkedin.com/in/example',
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'Profile updated successfully' in response.data

    refreshed = db.session.get(User, user.id)
    assert refreshed.username == 'updated_name'
    assert refreshed.email == 'updated@example.com'
    assert refreshed.profile.bio == 'A short bio'
    assert refreshed.profile.skills == 'Python'


def test_profile_password_change(client, auth, make_user):
    user = make_user()
    auth.login(user)

    response = client.post(
        '/profile',
        data={
            'action': 'password',
            'current_password': 'secret123',
            'new_password': 'brand-new-pass',
            'confirm_password': 'brand-new-pass',
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'Password changed successfully' in response.data

    refreshed = db.session.get(User, user.id)
    assert refreshed.check_password('brand-new-pass')
    assert not refreshed.check_password('secret123')


def test_profile_password_change_rejects_wrong_current_password(
    client, auth, make_user
):
    user = make_user()
    auth.login(user)

    response = client.post(
        '/profile',
        data={
            'action': 'password',
            'current_password': 'wrong',
            'new_password': 'brand-new-pass',
            'confirm_password': 'brand-new-pass',
        },
        follow_redirects=True,
    )

    assert b'Current password is incorrect' in response.data
    assert db.session.get(User, user.id).check_password('secret123')


def test_forgot_password_creates_pending_request(client, make_user):
    user = make_user()

    response = client.post(
        '/forgot-password',
        data={'email': user.email},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'request has been submitted' in response.data

    reset_request = PasswordResetRequest.query.filter_by(user_id=user.id).first()
    assert reset_request is not None
    assert reset_request.status == 'pending'


def test_forgot_password_does_not_duplicate_pending_requests(client, make_user):
    user = make_user()
    client.post('/forgot-password', data={'email': user.email})

    response = client.post(
        '/forgot-password',
        data={'email': user.email},
        follow_redirects=True,
    )

    assert b'If an account exists for that email address' in response.data
    assert PasswordResetRequest.query.filter_by(user_id=user.id).count() == 1


def test_forgot_password_response_does_not_reveal_account_existence(
    client, make_user
):
    user = make_user()

    known = client.post(
        '/forgot-password',
        data={'email': user.email},
        follow_redirects=True,
    )
    unknown = client.post(
        '/forgot-password',
        data={'email': 'nobody@example.com'},
        follow_redirects=True,
    )

    generic = b'If an account exists for that email address'
    assert known.status_code == 200
    assert unknown.status_code == 200
    assert generic in known.data
    assert generic in unknown.data
    assert user.email.encode() not in known.data
    assert PasswordResetRequest.query.filter_by(user_id=user.id).count() == 1
    assert PasswordResetRequest.query.filter_by(
        email='nobody@example.com'
    ).count() == 0


def test_admin_reset_never_returns_reset_token(
    client, auth, make_user, caplog
):
    import logging

    caplog.set_level(logging.DEBUG)
    admin = make_user(role='Admin')
    target = make_user()
    auth.login(admin)

    response = client.post(
        '/admin/reset-password',
        data={'email': target.email},
        follow_redirects=True,
    )

    token = PasswordResetToken.query.filter_by(user_id=target.id).first()
    assert token is not None
    assert response.status_code == 200
    assert token.token.encode() not in response.data
    assert b'/reset-password/' not in response.data
    assert token.token not in caplog.text
    assert '/reset-password/' not in caplog.text


def test_approved_reset_never_returns_reset_token(
    client, auth, make_user, caplog
):
    import logging

    caplog.set_level(logging.DEBUG)
    admin = make_user(role='Admin')
    target = make_user()
    reset_request = PasswordResetRequest(user_id=target.id, email=target.email)
    db.session.add(reset_request)
    db.session.commit()
    auth.login(admin)

    response = client.get(
        f'/admin/approve-reset-request/{reset_request.id}',
        follow_redirects=True,
    )

    token = PasswordResetToken.query.filter_by(user_id=target.id).first()
    assert token is not None
    assert response.status_code == 200
    assert token.token.encode() not in response.data
    assert b'/reset-password/' not in response.data
    assert token.token not in caplog.text
    assert '/reset-password/' not in caplog.text


def test_reset_password_with_valid_token(client, make_user):
    user = make_user()
    token = PasswordResetToken(
        user_id=user.id,
        token='valid-reset-token',
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    db.session.add(token)
    db.session.commit()

    page = client.get('/reset-password/valid-reset-token')
    response = client.post(
        '/reset-password/valid-reset-token',
        data={'password': 'new-password', 'confirm_password': 'new-password'},
        follow_redirects=True,
    )

    assert page.status_code == 200
    assert response.status_code == 200
    assert b'Password reset successfully' in response.data

    refreshed = db.session.get(User, user.id)
    assert refreshed.check_password('new-password')
    assert db.session.get(PasswordResetToken, token.id).is_used is True


def test_reset_password_rejects_invalid_or_expired_token(client, make_user):
    user = make_user()
    expired = PasswordResetToken(
        user_id=user.id,
        token='expired-token',
        expires_at=datetime.utcnow() - timedelta(hours=1),
    )
    db.session.add(expired)
    db.session.commit()

    invalid_response = client.get('/reset-password/unknown-token')
    expired_response = client.get('/reset-password/expired-token')

    assert invalid_response.status_code == 302
    assert expired_response.status_code == 302
    assert '/login' in invalid_response.headers['Location']
    assert '/login' in expired_response.headers['Location']


def test_reset_password_validates_new_password(client, make_user):
    user = make_user()
    token = PasswordResetToken(
        user_id=user.id,
        token='short-password-token',
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    db.session.add(token)
    db.session.commit()

    too_short = client.post(
        '/reset-password/short-password-token',
        data={'password': '123', 'confirm_password': '123'},
    )
    mismatch = client.post(
        '/reset-password/short-password-token',
        data={'password': 'abcdef', 'confirm_password': 'ghijkl'},
    )

    assert too_short.status_code == 200
    assert mismatch.status_code == 200
    assert db.session.get(User, user.id).check_password('secret123')


def test_non_admin_cannot_access_admin_reset_page(client, auth, make_user):
    student = make_user(role='Student')
    auth.login(student)

    response = client.get('/admin/reset-password')

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/')


def test_admin_can_generate_password_reset_link(client, auth, make_user):
    admin = make_user(role='Admin')
    target = make_user()
    auth.login(admin)

    page = client.get('/admin/reset-password')
    response = client.post(
        '/admin/reset-password', data={'email': target.email}
    )

    assert page.status_code == 200
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/dashboard/admin')
    assert PasswordResetToken.query.filter_by(user_id=target.id).count() == 1


def test_admin_can_approve_password_reset_request(client, auth, make_user):
    admin = make_user(role='Admin')
    target = make_user()
    reset_request = PasswordResetRequest(user_id=target.id, email=target.email)
    db.session.add(reset_request)
    db.session.commit()
    auth.login(admin)

    response = client.get(
        f'/admin/approve-reset-request/{reset_request.id}'
    )

    assert response.status_code == 302
    refreshed = db.session.get(PasswordResetRequest, reset_request.id)
    assert refreshed.status == 'approved'
    assert refreshed.resolved_by == admin.id
    assert PasswordResetToken.query.filter_by(user_id=target.id).count() == 1
