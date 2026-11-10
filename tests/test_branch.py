from database import db
from models.user import Branch


def _make_branch(**overrides):
    data = {
        'name': 'Test Branch',
        'slug': 'test-branch',
        'address': '1 Test Road',
        'city': 'Kathmandu',
        'latitude': 27.7172,
        'longitude': 85.3240,
    }
    data.update(overrides)
    branch = Branch(**data)
    db.session.add(branch)
    db.session.commit()
    return branch


def test_public_branch_api_does_not_expose_user_locations(client, make_user):
    student = make_user(username='private_learner')
    student.profile.city = 'Secretville'
    student.profile.latitude = 27.111111
    student.profile.longitude = 85.222222
    db.session.commit()

    _make_branch()

    response = client.get('/branches/api/data')
    payload = response.get_json()

    assert response.status_code == 200
    assert 'users' not in payload
    assert len(payload['branches']) == 1

    body = response.get_data(as_text=True)
    assert 'private_learner' not in body
    assert 'Secretville' not in body
    assert '27.111111' not in body
    assert '85.222222' not in body


def test_public_branch_map_does_not_render_learners(client, make_user):
    student = make_user(username='private_learner')
    student.profile.latitude = 27.111111
    student.profile.longitude = 85.222222
    db.session.commit()

    _make_branch()

    response = client.get('/branches/map')

    assert response.status_code == 200
    assert b'private_learner' not in response.data
