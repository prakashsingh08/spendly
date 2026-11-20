import pytest

from database import db

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"
INVALID_LOGIN = b"Invalid email or password."


def login(client, email=DEMO_EMAIL, password=DEMO_PASSWORD, **kwargs):
    return client.post(
        "/login", data={"email": email, "password": password}, **kwargs
    )


def demo_id():
    return db.get_user_by_email(DEMO_EMAIL)["id"]


# ------------------------------------------------------------------ #
# Login                                                               #
# ------------------------------------------------------------------ #

def test_get_login_returns_200(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b'name="email"' in response.data


def test_login_demo_redirects_to_profile(client):
    response = login(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile")
    with client.session_transaction() as sess:
        assert sess["user_id"] == demo_id()
        assert sess["user_name"] == "Demo User"
        assert "password_hash" not in sess


def test_login_normalises_email(client):
    response = login(client, email="  Demo@Spendly.com ")
    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert sess["user_id"] == demo_id()


def test_registered_user_can_login(client):
    client.post(
        "/register",
        data={
            "name": "Alice Smith",
            "email": "alice@example.com",
            "password": "password123",
        },
    )
    response = login(client, email="alice@example.com", password="password123")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile")
    with client.session_transaction() as sess:
        assert sess["user_name"] == "Alice Smith"


@pytest.mark.parametrize(
    "email, password",
    [
        (DEMO_EMAIL, "wrongpass"),
        ("nobody@example.com", DEMO_PASSWORD),
        ("", DEMO_PASSWORD),
        (DEMO_EMAIL, ""),
        ("", ""),
    ],
)
def test_failed_login_returns_401(client, email, password):
    response = login(client, email=email, password=password)
    assert response.status_code == 401
    assert INVALID_LOGIN in response.data
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_failed_login_keeps_email_not_password(client):
    response = login(client, password="Zq9wrong1")
    assert response.status_code == 401
    assert b'value="demo@spendly.com"' in response.data
    assert b"Zq9wrong1" not in response.data


def test_login_clears_stale_session(client):
    with client.session_transaction() as sess:
        sess["stale"] = "x"
    login(client)
    with client.session_transaction() as sess:
        assert "stale" not in sess
        assert sess["user_id"] == demo_id()


def test_login_form_action_uses_url_for(app):
    source, _, _ = app.jinja_loader.get_source(app.jinja_env, "login.html")
    assert "url_for('login')" in source
    assert 'action="/login"' not in source


# ------------------------------------------------------------------ #
# Already logged in                                                   #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("path", ["/login", "/register"])
def test_logged_in_user_redirected_to_profile(client, path):
    login(client)
    response = client.get(path)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile")


# ------------------------------------------------------------------ #
# Navbar                                                              #
# ------------------------------------------------------------------ #

def test_navbar_logged_out(client):
    response = client.get("/")
    assert b"Sign in" in response.data
    assert b"Get started" in response.data
    assert b"Sign out" not in response.data


def test_navbar_logged_in(client):
    login(client)
    response = client.get("/")
    assert b"Demo User" in response.data
    assert b"Sign out" in response.data
    assert b'href="/logout"' in response.data
    assert b"Get started" not in response.data


# ------------------------------------------------------------------ #
# Logout                                                              #
# ------------------------------------------------------------------ #

def test_logout_clears_session(client):
    login(client)
    response = client.get("/logout", follow_redirects=True)
    assert response.status_code == 200
    assert response.request.path == "/"
    assert b"You have been signed out." in response.data
    assert b"Get started" in response.data
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_logout_when_logged_out(client):
    response = client.get("/logout")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
    assert client.get("/").status_code == 200


# ------------------------------------------------------------------ #
# Flash messages                                                      #
# ------------------------------------------------------------------ #

def test_register_flash_shown_once(client):
    response = client.post(
        "/register",
        data={
            "name": "Bob",
            "email": "bob@example.com",
            "password": "password123",
        },
        follow_redirects=True,
    )
    assert response.request.path == "/login"
    assert response.data.count(b"Account created") == 1


# ------------------------------------------------------------------ #
# DB helper                                                           #
# ------------------------------------------------------------------ #

@pytest.fixture
def seeded(temp_db):
    db.seed_db()


def test_authenticate_user_success(seeded):
    user = db.authenticate_user(DEMO_EMAIL, DEMO_PASSWORD)
    assert user is not None
    assert user["email"] == DEMO_EMAIL


@pytest.mark.parametrize(
    "email, password",
    [
        (DEMO_EMAIL, "wrongpass"),
        ("nobody@example.com", DEMO_PASSWORD),
        ("", DEMO_PASSWORD),
        (DEMO_EMAIL, ""),
        (None, None),
    ],
)
def test_authenticate_user_failure(seeded, email, password):
    assert db.authenticate_user(email, password) is None
