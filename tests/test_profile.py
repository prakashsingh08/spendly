from datetime import date, timedelta

import pytest
from flask import url_for

from database import db

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"
SIGN_IN_MESSAGE = b"Please sign in to continue."


def login(client, email=DEMO_EMAIL, password=DEMO_PASSWORD, **kwargs):
    return client.post(
        "/login", data={"email": email, "password": password}, **kwargs
    )


def register(client, name, email, password="password123"):
    return client.post(
        "/register", data={"name": name, "email": email, "password": password}
    )


def demo_id():
    return db.get_user_by_email(DEMO_EMAIL)["id"]


def add_expense(user_id, amount, on_date, category="Food"):
    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date) "
            "VALUES (?, ?, ?, ?)",
            (user_id, amount, category, on_date.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# Access control                                                      #
# ------------------------------------------------------------------ #

def test_profile_requires_login(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    followed = client.get("/profile", follow_redirects=True)
    assert followed.request.path == "/login"
    assert SIGN_IN_MESSAGE in followed.data


def test_profile_stale_session_redirects_and_clears(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 9999
        sess["user_name"] = "Ghost"
    response = client.get("/profile", follow_redirects=True)
    assert response.request.path == "/login"
    assert SIGN_IN_MESSAGE in response.data
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_login_required_preserves_endpoint_name(app):
    with app.test_request_context():
        assert url_for("profile") == "/profile"


# ------------------------------------------------------------------ #
# Page content                                                        #
# ------------------------------------------------------------------ #

def test_login_lands_on_profile(client):
    response = login(client, follow_redirects=True)
    assert response.status_code == 200
    assert response.request.path == "/profile"
    assert b"Welcome back" in response.data
    assert b"Sign out" in response.data


def test_profile_shows_account_details(client):
    login(client)
    response = client.get("/profile")
    assert response.status_code == 200
    assert b"Demo User" in response.data
    assert b"demo@spendly.com" in response.data
    assert b"Member since" in response.data


def test_profile_demo_summary(client):
    login(client)
    html = client.get("/profile").get_data(as_text=True)
    assert '<span class="profile-stat-value">8</span>' in html
    assert html.count("₹3,820.24") == 2  # total and this month
    assert "No expenses yet." not in html


def test_profile_new_user_empty_state(client):
    register(client, "Alice", "alice@example.com")
    login(client, email="alice@example.com", password="password123")
    html = client.get("/profile").get_data(as_text=True)
    assert '<span class="profile-stat-value">0</span>' in html
    assert html.count("₹0.00") == 2
    assert "No expenses yet." in html


def test_profile_isolated_between_users(client):
    register(client, "Bob", "bob@example.com")
    bob_id = db.get_user_by_email("bob@example.com")["id"]
    add_expense(bob_id, 42.50, date.today())

    login(client, email="bob@example.com", password="password123")
    html = client.get("/profile").get_data(as_text=True)
    assert "₹42.50" in html
    assert "₹3,820.24" not in html
    assert '<span class="profile-stat-value">1</span>' in html


def test_profile_never_shows_password_hash(client):
    stored_hash = db.get_user_by_email(DEMO_EMAIL)["password_hash"]
    login(client)
    html = client.get("/profile").get_data(as_text=True)
    assert stored_hash not in html


def test_profile_uses_page_stylesheet(client):
    login(client)
    response = client.get("/profile")
    assert b"css/profile.css" in response.data


# ------------------------------------------------------------------ #
# DB helpers                                                          #
# ------------------------------------------------------------------ #

@pytest.fixture
def seeded(temp_db):
    db.seed_db()


def test_get_user_by_id_found(seeded):
    user = db.get_user_by_id(demo_id())
    assert user["email"] == DEMO_EMAIL
    assert user["name"] == "Demo User"
    assert "password_hash" not in user.keys()


def test_get_user_by_id_missing(seeded):
    assert db.get_user_by_id(9999) is None


def test_expense_summary_demo(seeded):
    summary = db.get_expense_summary(demo_id())
    assert summary["count"] == 8
    assert summary["total"] == pytest.approx(3820.24)
    assert summary["month_total"] == pytest.approx(3820.24)


def test_expense_summary_no_expenses(temp_db):
    user_id = db.create_user("Empty", "empty@example.com", "password123")
    assert db.get_expense_summary(user_id) == {
        "count": 0,
        "total": 0,
        "month_total": 0,
    }


def test_month_total_excludes_last_month(seeded):
    last_month = date.today().replace(day=1) - timedelta(days=1)
    add_expense(demo_id(), 100.00, last_month)
    summary = db.get_expense_summary(demo_id())
    assert summary["count"] == 9
    assert summary["total"] == pytest.approx(3920.24)
    assert summary["month_total"] == pytest.approx(3820.24)


@pytest.mark.parametrize(
    "today, inside, outside",
    [
        # December rolls over to January of the next year
        (date(2026, 12, 15), date(2026, 12, 31), date(2027, 1, 1)),
        # February in a leap year
        (date(2028, 2, 10), date(2028, 2, 29), date(2028, 3, 1)),
        # First day of month: previous month's last day is excluded
        (date(2026, 11, 1), date(2026, 11, 1), date(2026, 10, 31)),
    ],
)
def test_month_boundaries(temp_db, today, inside, outside):
    user_id = db.create_user("Edge", "edge@example.com", "password123")
    add_expense(user_id, 10.00, inside)
    add_expense(user_id, 5.00, outside)
    summary = db.get_expense_summary(user_id, today=today)
    assert summary["count"] == 2
    assert summary["total"] == pytest.approx(15.00)
    assert summary["month_total"] == pytest.approx(10.00)
