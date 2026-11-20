import pytest

from database import db


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point the DB layer at a throwaway file and create the schema."""
    path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", str(path))
    db.init_db()
    return path


@pytest.fixture
def conn(temp_db):
    connection = db.get_db()
    yield connection
    connection.close()


@pytest.fixture
def app(temp_db):
    """Flask app wired to the temp DB, seeded with the demo user.

    Imported inside the fixture: importing app.py runs init_db()/seed_db(),
    so DB_PATH must already point at the temp file.
    """
    from app import app as flask_app

    flask_app.config.update(TESTING=True)
    db.seed_db()
    yield flask_app
