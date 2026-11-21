from datetime import date

from database import db

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"
SECTION_TITLE = b"Recent transactions"


def login(client, email=DEMO_EMAIL, password=DEMO_PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


def register(client, name, email, password="password123"):
    return client.post(
        "/register", data={"name": name, "email": email, "password": password}
    )


def format_date(value):
    """The app's format_date filter, looked up after the app fixture loads."""
    from app import app as flask_app
    return flask_app.jinja_env.filters["format_date"](value)


def demo_id():
    return db.get_user_by_email(DEMO_EMAIL)["id"]


def add_expense(user_id, amount, on_date, description=None, category="Food"):
    conn = db.get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, on_date, description),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def new_user(client, name, email):
    register(client, name, email)
    return db.get_user_by_email(email)["id"]


def get_profile(client, email=DEMO_EMAIL, password=DEMO_PASSWORD):
    login(client, email, password)
    response = client.get("/profile")
    assert response.status_code == 200
    return response.data.decode()


def table_body(html):
    """The recent-transactions table body, so other sections can't match."""
    start = html.index("<tbody>")
    return html[start:html.index("</tbody>", start)]


# ------------------------------------------------------------------ #
# format_date filter                                                  #
# ------------------------------------------------------------------ #

def test_format_date_iso_date(app):
    assert format_date("2026-11-25") == "25 Nov 2026"


def test_format_date_timestamp_and_empty(app):
    assert format_date("2026-11-20 14:03:09") == "20 Nov 2026"
    assert format_date("") == ""
    assert format_date(None) == ""


# ------------------------------------------------------------------ #
# get_recent_expenses helper                                          #
# ------------------------------------------------------------------ #

def test_helper_returns_demo_rows_newest_first(app):
    rows = db.get_recent_expenses(demo_id())
    assert len(rows) == 8
    assert set(rows[0].keys()) == {
        "id", "amount", "category", "date", "description"
    }
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates, reverse=True)
    assert rows[0]["category"] == "Other"
    assert rows[0]["description"] is None


def test_helper_limits_to_ten_newest(app, client):
    uid = new_user(client, "Many", "many@example.com")
    for day in range(1, 13):
        add_expense(uid, day, f"2026-10-{day:02d}", f"Item {day}")
    rows = db.get_recent_expenses(uid)
    assert len(rows) == 10
    assert [r["description"] for r in rows] == [
        f"Item {d}" for d in range(12, 2, -1)
    ]
    assert len(db.get_recent_expenses(uid, limit=3)) == 3


def test_helper_ties_ordered_by_id_desc(app, client):
    uid = new_user(client, "Tie", "tie@example.com")
    first = add_expense(uid, 1, "2026-10-05", "First")
    second = add_expense(uid, 2, "2026-10-05", "Second")
    third = add_expense(uid, 3, "2026-10-05", "Third")
    rows = db.get_recent_expenses(uid)
    assert [r["id"] for r in rows] == [third, second, first]


def test_helper_empty_for_user_without_expenses(app, client):
    uid = new_user(client, "Empty", "empty@example.com")
    assert db.get_recent_expenses(uid) == []


# ------------------------------------------------------------------ #
# Rendered section                                                    #
# ------------------------------------------------------------------ #

def test_demo_profile_shows_all_eight_transactions(app, client):
    html = get_profile(client)
    assert "Recent transactions" in html
    body = table_body(html)
    assert body.count("<tr>") == 8
    for desc in (
        "Monthly rent share", "Groceries", "Metro card top-up", "Pharmacy",
        "Movie night", "New shoes", "Dinner out",
    ):
        assert desc in body
    assert "₹1,599.99" in body
    assert "₹1,200.00" in body


def test_demo_profile_newest_first(app, client):
    body = table_body(get_profile(client))
    first_row = body[:body.index("</tr>")]
    day_25 = format_date(date.today().replace(day=25).isoformat())
    assert day_25 in first_row
    assert "Other" in first_row
    assert "—" in first_row
    assert "₹75.00" in first_row
    assert body.index("Dinner out") < body.index("Groceries")


def test_profile_shows_only_ten_newest(app, client):
    uid = new_user(client, "Many", "many@example.com")
    for day in range(1, 13):
        add_expense(uid, day, f"2026-10-{day:02d}", f"Item {day:02d}")
    body = table_body(get_profile(client, "many@example.com", "password123"))
    assert body.count("<tr>") == 10
    assert "Item 12" in body
    assert "Item 03" in body
    assert "Item 02" not in body
    assert "Item 01" not in body
    assert body.index("Item 12") < body.index("Item 03")


def test_new_user_has_no_transactions_section(app, client):
    register(client, "Fresh", "fresh@example.com")
    html = get_profile(client, "fresh@example.com", "password123")
    assert "Recent transactions" not in html
    assert "<tbody>" not in html
    assert "No expenses yet." in html


def test_users_never_see_each_others_transactions(app, client):
    alice = new_user(client, "Alice", "alice@example.com")
    bob = new_user(client, "Bob", "bob@example.com")
    add_expense(alice, 11.11, "2026-10-01", "Alice secret lunch")
    add_expense(bob, 22.22, "2026-10-02", "Bob secret taxi")

    alice_body = table_body(get_profile(client, "alice@example.com", "password123"))
    assert "Alice secret lunch" in alice_body
    assert "Bob secret taxi" not in alice_body
    assert "Monthly rent share" not in alice_body
    client.get("/logout")

    bob_body = table_body(get_profile(client, "bob@example.com", "password123"))
    assert "Bob secret taxi" in bob_body
    assert "Alice secret lunch" not in bob_body
    client.get("/logout")

    demo_body = table_body(get_profile(client))
    assert "Alice secret lunch" not in demo_body
    assert "Bob secret taxi" not in demo_body

    assert [r["description"] for r in db.get_recent_expenses(alice)] == [
        "Alice secret lunch"
    ]


def test_dates_rendered_in_day_month_year_format(app, client):
    uid = new_user(client, "Dated", "dated@example.com")
    add_expense(uid, 5, "2026-11-25", "Dated item")
    body = table_body(get_profile(client, "dated@example.com", "password123"))
    assert "25 Nov 2026" in body
    assert "2026-11-25" not in body
