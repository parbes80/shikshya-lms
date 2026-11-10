import pytest

from config import normalize_database_url


@pytest.mark.parametrize('raw, expected', [
    (
        'postgres://user:pass@host:5432/db',
        'postgresql://user:pass@host:5432/db?sslmode=require',
    ),
    (
        'postgresql://user:pass@host:5432/db',
        'postgresql://user:pass@host:5432/db?sslmode=require',
    ),
    (
        'postgresql+psycopg://user:pass@host:5432/db',
        'postgresql+psycopg://user:pass@host:5432/db?sslmode=require',
    ),
    (
        'postgresql+psycopg2://user:pass@host:5432/db',
        'postgresql+psycopg2://user:pass@host:5432/db?sslmode=require',
    ),
    (
        'postgresql://user:pass@host:5432/db?sslmode=require',
        'postgresql://user:pass@host:5432/db?sslmode=require',
    ),
    (
        'postgresql://user:pass@host:5432/db?application_name=shikshya',
        'postgresql://user:pass@host:5432/db?application_name=shikshya&sslmode=require',
    ),
    (
        'sqlite:///shikshya.db',
        'sqlite:///shikshya.db',
    ),
])
def test_normalize_database_url(raw, expected):
    assert normalize_database_url(raw) == expected
