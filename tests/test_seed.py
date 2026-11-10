from models.user import Role, User
from seed import seed_database


def test_seed_ensures_roles_but_skips_demo_users_by_default(app, monkeypatch):
    monkeypatch.setitem(app.config, 'SEED_DEMO_DATA', False)

    seed_database()

    assert Role.query.filter_by(name='Admin').count() == 1
    assert Role.query.filter_by(name='Teacher').count() == 1
    assert Role.query.filter_by(name='Student').count() == 1
    assert User.query.count() == 0


def test_seed_creates_demo_data_only_when_explicitly_enabled(app, monkeypatch):
    monkeypatch.setitem(app.config, 'SEED_DEMO_DATA', True)

    seed_database()

    admin = User.query.filter_by(email='admin@shikshya.edu').first()
    assert admin is not None
    assert admin.role.name == 'Admin'
    assert admin.check_password('admin123')
    assert User.query.count() == 3

    # Running again is idempotent and does not create duplicate demo users.
    seed_database()
    assert User.query.count() == 3
