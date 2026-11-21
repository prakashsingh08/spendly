"""Step 5 regression tests for the /profile summary stat tiles.

These complement tests/test_profile.py: they check the tiles by label
(so new sections that also print rupee amounts cannot mask a wrong value),
the rendered page across month boundaries, and that the summary agrees
with the raw expense rows.
"""
import re
from datetime import date, timedelta

import pytest

from database import db

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"
SIGN_IN_MESSAGE = b"Please sign in to continue."

TILE_RE = re.compile(
    r'<span class="profile-stat-label">([^<]+)</span>\s*'
    r'<span class="profile-stat-value">([^<]+)</span>'
)


def login(client, email=DEMO_EMAIL, password=DEMO_PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


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


def sum_amounts(user_id, start=None, end=None):
    """Independent sum over raw rows (optionally within [start, end))."""
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT amount, date FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchall()
    finally:
        conn.close()
    total = 0.0
    for amount, on_date in rows:
        if start and on_date < start.isoformat():
            continue
        if end and on_date >= end.isoformat():
            continue
        total += amount
    return total, len(rows)


def month_bounds(today):
    start = today.replace(day=1)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, end


def tiles(html):
    """Map each summary tile label to its rendered value."""
    return dict(TILE_RE.findall(html))


def profile_html(client):
    response = client.get("/profile")
    assert response.status_code == 200
    return response.get_data(as_text=True)


# ------------------------------------------------------------------ #
# Demo user                                                           #
# ------------------------------------------------------------------ #

def test_demo_tiles_unchanged_alongside_new_sections(client):
    login(client)
    html = profile_html(client)
    assert tiles(html) == {
        "Expenses": "8",
        "Total spent": "₹3,820.24",
        "This month": "₹3,820.24",
    }
    assert "Spending summary" in html
    assert "Spending by category" in html
    assert "Recent transactions" in html
    assert "No expenses yet." not in html


def test_summary_section_renders_before_new_sections(client):
    login(client)
    html = profile_html(client)
    summary_at = html.index("Spending summary")
    assert summary_at < html.index("Spending by category")
    assert summary_at < html.index("Recent transactions")


# ------------------------------------------------------------------ #
# Totals vs raw rows, across month boundaries                         #
# ------------------------------------------------------------------ #

def test_page_totals_match_rows_across_month_boundaries(client):
    uid = demo_id()
    start, next_start = month_bounds(date.today())
    add_expense(uid, 100.00, start)                          # 1st: this month
    add_expense(uid, 50.50, start - timedelta(days=1))       # last month
    add_expense(uid, 1000.00, next_start)                    # 1st of next month
    add_expense(uid, 0.26, next_start - timedelta(days=1))   # last day: this month

    total, count = sum_amounts(uid)
    month_total, _ = sum_amounts(uid, start, next_start)
    assert count == 12
    assert total == pytest.approx(3820.24 + 100.00 + 50.50 + 1000.00 + 0.26)
    assert month_total == pytest.approx(3820.24 + 100.00 + 0.26)

    login(client)
    assert tiles(profile_html(client)) == {
        "Expenses": "12",
        "Total spent": "₹4,971.00",
        "This month": "₹3,920.50",
    }


def test_helper_matches_independent_sum(seeded_temp_db):
    uid = demo_id()
    today = date.today()
    start, next_start = month_bounds(today)
    for amount, on_date in [
        (12.34, start),
        (56.78, start - timedelta(days=40)),
        (9.99, next_start),
        (0.01, today),
    ]:
        add_expense(uid, amount, on_date)

    total, count = sum_amounts(uid)
    month_total, _ = sum_amounts(uid, start, next_start)
    summary = db.get_expense_summary(uid)
    assert summary["count"] == count
    assert summary["total"] == pytest.approx(total)
    assert summary["month_total"] == pytest.approx(month_total)


def test_summary_ignores_other_users_rows(seeded_temp_db):
    other = db.create_user("Other", "other@example.com", "password123")
    add_expense(other, 999.00, date.today())
    summary = db.get_expense_summary(demo_id())
    assert summary["count"] == 8
    assert summary["total"] == pytest.approx(3820.24)
    assert summary["month_total"] == pytest.approx(3820.24)


@pytest.fixture
def seeded_temp_db(temp_db):
    db.seed_db()


# ------------------------------------------------------------------ #
# New user / access control                                           #
# ------------------------------------------------------------------ #

def test_new_user_tiles_are_zero(client):
    register(client, "Zed", "zed@example.com")
    login(client, email="zed@example.com", password="password123")
    html = profile_html(client)
    assert tiles(html) == {
        "Expenses": "0",
        "Total spent": "₹0.00",
        "This month": "₹0.00",
    }
    assert "No expenses yet." in html


def test_new_user_only_last_month_spend(client):
    register(client, "Lm", "lm@example.com")
    uid = db.get_user_by_email("lm@example.com")["id"]
    start, _ = month_bounds(date.today())
    add_expense(uid, 1234.5, start - timedelta(days=1))

    login(client, email="lm@example.com", password="password123")
    html = profile_html(client)
    assert tiles(html) == {
        "Expenses": "1",
        "Total spent": "₹1,234.50",
        "This month": "₹0.00",
    }
    assert "No expenses yet." not in html


def test_logged_out_redirects_with_message(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    followed = client.get("/profile", follow_redirects=True)
    assert SIGN_IN_MESSAGE in followed.data
    assert b"profile-stat-value" not in followed.data


def test_stale_session_after_user_deleted(client):
    login(client)
    uid = demo_id()
    conn = db.get_db()
    try:
        conn.execute("DELETE FROM expenses WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM users WHERE id = ?", (uid,))
        conn.commit()
    finally:
        conn.close()

    response = client.get("/profile", follow_redirects=True)
    assert response.request.path == "/login"
    assert SIGN_IN_MESSAGE in response.data
    assert b"profile-stat-value" not in response.data
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_page_never_contains_password_hash(client):
    login(client)
    html = profile_html(client)
    assert "pbkdf2" not in html
    assert "scrypt" not in html
    assert "password_hash" not in html
