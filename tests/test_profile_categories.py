from datetime import date

from database import db

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"

DEMO_BREAKDOWN = [
    ("Shopping", 1599.99, 1),
    ("Bills", 1200.00, 1),
    ("Entertainment", 499.00, 1),
    ("Health", 250.00, 1),
    ("Food", 166.25, 2),
    ("Other", 75.00, 1),
    ("Transport", 30.00, 1),
]


def login(client, email=DEMO_EMAIL, password=DEMO_PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


def register(client, name, email, password="password123"):
    return client.post(
        "/register", data={"name": name, "email": email, "password": password}
    )


def demo_id():
    return db.get_user_by_email(DEMO_EMAIL)["id"]


def create_user(name, email):
    db.create_user(name, email, "password123")
    return db.get_user_by_email(email)["id"]


def add_expense(user_id, amount, category, on_date=None):
    on_date = on_date or date.today()
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
# Helper                                                              #
# ------------------------------------------------------------------ #

def test_demo_breakdown_order_totals_counts(app):
    breakdown = db.get_category_breakdown(demo_id())
    assert len(breakdown) == 7
    actual = [
        (item["category"], round(item["total"], 2), item["count"])
        for item in breakdown
    ]
    assert actual == DEMO_BREAKDOWN


def test_demo_breakdown_item_keys(app):
    for item in db.get_category_breakdown(demo_id()):
        assert set(item) == {"category", "total", "count", "percent"}


def test_demo_breakdown_percents(app):
    by_category = {
        item["category"]: item["percent"]
        for item in db.get_category_breakdown(demo_id())
    }
    assert by_category["Shopping"] == 41.9
    assert by_category["Bills"] == 31.4


def test_percents_sum_to_about_100(app):
    total = sum(item["percent"] for item in db.get_category_breakdown(demo_id()))
    assert abs(total - 100) <= 0.5


def test_ties_ordered_by_category_name(temp_db):
    user_id = create_user("Tie User", "tie@example.com")
    add_expense(user_id, 50, "Transport")
    add_expense(user_id, 50, "Bills")
    add_expense(user_id, 50, "Food")
    add_expense(user_id, 100, "Shopping")
    breakdown = db.get_category_breakdown(user_id)
    assert [item["category"] for item in breakdown] == [
        "Shopping", "Bills", "Food", "Transport",
    ]
    assert [item["percent"] for item in breakdown] == [40.0, 20.0, 20.0, 20.0]


def test_no_expenses_returns_empty_list(temp_db):
    user_id = create_user("Empty User", "empty@example.com")
    assert db.get_category_breakdown(user_id) == []


def test_breakdowns_isolated_between_users(app):
    other_id = create_user("Other User", "other@example.com")
    add_expense(other_id, 999, "Health")
    add_expense(other_id, 1, "Food")

    other = db.get_category_breakdown(other_id)
    assert [(i["category"], i["total"], i["count"]) for i in other] == [
        ("Health", 999, 1),
        ("Food", 1, 1),
    ]
    assert [i["percent"] for i in other] == [99.9, 0.1]

    demo = db.get_category_breakdown(demo_id())
    assert [
        (i["category"], round(i["total"], 2), i["count"]) for i in demo
    ] == DEMO_BREAKDOWN


# ------------------------------------------------------------------ #
# Rendered page                                                       #
# ------------------------------------------------------------------ #

def test_profile_shows_category_breakdown(client):
    login(client)
    html = client.get("/profile").get_data(as_text=True)
    assert "Spending by category" in html
    assert "₹1,599.99" in html
    assert "41.9%" in html
    assert "width: 41.9%" in html
    assert "31.4%" in html


def test_profile_category_rows_in_order(client):
    login(client)
    html = client.get("/profile").get_data(as_text=True)
    section = html.split("Spending by category", 1)[1]
    positions = [
        section.index(f'category-name">{name}<') for name, _, _ in DEMO_BREAKDOWN
    ]
    assert positions == sorted(positions)


def test_profile_hides_breakdown_without_expenses(client):
    register(client, "Fresh User", "fresh@example.com")
    login(client, "fresh@example.com", "password123")
    html = client.get("/profile").get_data(as_text=True)
    assert "No expenses yet." in html
    assert "Spending by category" not in html


def test_profile_breakdown_isolated_between_users(client):
    register(client, "Second User", "second@example.com")
    other_id = db.get_user_by_email("second@example.com")["id"]
    add_expense(other_id, 4321, "Health")

    login(client, "second@example.com", "password123")
    html = client.get("/profile").get_data(as_text=True)
    assert "Spending by category" in html
    assert "₹4,321.00" in html
    assert "100.0%" in html
    assert "₹1,599.99" not in html
    assert "Shopping" not in html
