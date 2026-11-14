from database import db
from models.interaction import Notification


def test_notifications_page_requires_login(client):
    response = client.get('/notifications')

    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_notifications_page_lists_only_own_notifications(
    client, auth, make_user
):
    student = make_user()
    other = make_user()
    db.session.add_all([
        Notification(user_id=student.id, title='Mine', message='For me'),
        Notification(user_id=other.id, title='Theirs', message='For them'),
    ])
    db.session.commit()
    auth.login(student)

    response = client.get('/notifications')

    assert response.status_code == 200
    assert b'Mine' in response.data
    assert b'For me' in response.data
    assert b'Their' not in response.data
    assert b'For them' not in response.data


def test_mark_all_notifications_read_only_affects_current_user(
    client, auth, make_user
):
    student = make_user()
    other = make_user()
    mine = Notification(user_id=student.id, title='Mine', message='Mine')
    theirs = Notification(user_id=other.id, title='Theirs', message='Theirs')
    db.session.add_all([mine, theirs])
    db.session.commit()
    auth.login(student)

    response = client.post('/notifications/read-all')

    assert response.status_code == 302
    assert db.session.get(Notification, mine.id).is_read is True
    assert db.session.get(Notification, theirs.id).is_read is False


def test_mark_single_notification_read_rejects_other_users(
    client, auth, make_user
):
    student = make_user()
    other = make_user()
    notification = Notification(
        user_id=other.id, title='Theirs', message='Theirs'
    )
    db.session.add(notification)
    db.session.commit()
    auth.login(student)

    response = client.post(f'/notifications/{notification.id}/read')

    assert response.status_code == 404
    assert db.session.get(Notification, notification.id).is_read is False


def test_notifications_unread_filter(client, auth, make_user):
    student = make_user()
    db.session.add_all([
        Notification(user_id=student.id, title='Unread one', message='x'),
        Notification(
            user_id=student.id, title='Read one', message='y', is_read=True
        ),
    ])
    db.session.commit()
    auth.login(student)

    response = client.get('/notifications?status=unread')

    assert response.status_code == 200
    assert b'Unread one' in response.data
    assert b'Read one' not in response.data
