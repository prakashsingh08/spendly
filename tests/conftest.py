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
