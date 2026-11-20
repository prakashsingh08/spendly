import sqlite3
import sys

import pytest
from werkzeug.security import check_password_hash

from database import db

VALID = {
    "name": "Alice Smith",
    "email": "alice@example.com",
    "password": "password123",
}


def user_count():
    conn = db.get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()


def get_user(email):
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

def test_get_register_returns_200(client):
    response = client.get("/register")
    assert response.status_code == 200
    assert b'name="email"' in response.data


def test_register_creates_user_with_hashed_password(client):
    client.post("/register", data=VALID)
    user = get_user("alice@example.com")
    assert user is not None
    assert user["name"] == "Alice Smith"
    assert user["password_hash"] != VALID["password"]
    assert user["password_hash"].startswith(("scrypt:", "pbkdf2:"))
    assert check_password_hash(user["password_hash"], VALID["password"])


def test_register_redirects_to_login(client):
    response = client.post("/register", data=VALID)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_register_shows_flash_on_login(client):
    response = client.post("/register", data=VALID, follow_redirects=True)
    assert response.status_code == 200
    assert response.request.path == "/login"
    assert b"Account created" in response.data
    assert b"auth-success" in response.data


def test_register_normalises_email(client):
    client.post("/register", data={**VALID, "email": "Test@Example.com "})
    assert get_user("test@example.com") is not None
    assert get_user("Test@Example.com ") is None


@pytest.mark.parametrize("email", ["demo@spendly.com", " DEMO@Spendly.com"])
def test_register_duplicate_email_rejected(client, email):
    before = user_count()
    response = client.post("/register", data={**VALID, "email": email})
    assert response.status_code == 400
    assert b"An account with that email already exists." in response.data
    assert user_count() == before


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"name": "   "}, b"Please enter your name."),
        ({"email": "no-at"}, b"Please enter a valid email address."),
        ({"email": "a@nodot"}, b"Please enter a valid email address."),
        ({"email": "@x.com"}, b"Please enter a valid email address."),
        ({"email": "a@x.com."}, b"Please enter a valid email address."),
        ({"password": "short7c"}, b"Password must be at least 8 characters."),
    ],
)
def test_register_invalid_input_returns_400(client, overrides, message):
    before = user_count()
    response = client.post("/register", data={**VALID, **overrides})
    assert response.status_code == 400
    assert message in response.data
    assert user_count() == before


def test_error_keeps_name_and_email_not_password(client):
    response = client.post(
        "/register",
        data={"name": "Alice", "email": "alice@example.com", "password": "Zq9shrt"},
    )
    assert response.status_code == 400
    assert b'value="Alice"' in response.data
    assert b'value="alice@example.com"' in response.data
    assert b"Zq9shrt" not in response.data


def test_register_form_action_uses_url_for(app):
    source, _, _ = app.jinja_loader.get_source(app.jinja_env, "register.html")
    assert "url_for('register')" in source
    assert 'action="/register"' not in source


def test_integrity_error_handled(client, monkeypatch):
    # Simulate a race: the pre-check misses, the INSERT hits the UNIQUE index.
    monkeypatch.setattr(sys.modules["app"], "get_user_by_email", lambda email: None)
    before = user_count()
    response = client.post("/register", data={**VALID, "email": "demo@spendly.com"})
    assert response.status_code == 400
    assert b"An account with that email already exists." in response.data
    assert user_count() == before


# ------------------------------------------------------------------ #
# DB helpers                                                          #
# ------------------------------------------------------------------ #

def test_get_user_by_email_hit_and_miss(temp_db):
    db.seed_db()
    user = db.get_user_by_email("demo@spendly.com")
    assert user is not None
    assert user["name"] == "Demo User"
    assert db.get_user_by_email("nobody@example.com") is None


def test_create_user_returns_id(temp_db):
    user_id = db.create_user("Bob", "bob@example.com", "password123")
    user = db.get_user_by_email("bob@example.com")
    assert user["id"] == user_id


def test_create_user_duplicate_raises(temp_db):
    db.create_user("Bob", "bob@example.com", "password123")
    with pytest.raises(sqlite3.IntegrityError):
        db.create_user("Bob 2", "bob@example.com", "password456")
