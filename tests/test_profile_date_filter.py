import re
from datetime import date, timedelta

from werkzeug.datastructures import MultiDict

from database import db

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"
INVALID_DATE_ERROR = "Please enter valid dates."
DATE_ORDER_ERROR = "Start date must be on or before end date."
DEMO_MONTH_TOTAL = "₹3,820.24"
FIXED_TODAY = date(2026, 11, 21)


def login(client, email=DEMO_EMAIL, password=DEMO_PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


def register(client, name, email, password="password123"):
    return client.post(
        "/register", data={"name": name, "email": email, "password": password}
    )


def new_user(client, name, email):
    register(client, name, email)
    return db.get_user_by_email(email)["id"]


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


def day(n):
    """ISO date for day n of the current month (matches seed_db)."""
    return date.today().replace(day=n).isoformat()


def parse(**params):
    from app import parse_date_filter
    return parse_date_filter(MultiDict(params))


def build(today=FIXED_TODAY, **params):
    from app import build_date_filter
    return build_date_filter(MultiDict(params), today=today)


def get_profile(client, query="", email=DEMO_EMAIL, password=DEMO_PASSWORD):
    login(client, email, password)
    response = client.get("/profile" + query)
    assert response.status_code == 200
    return response.data.decode()


def stat_values(html):
    """[count, total, month_total] as rendered in the stat tiles."""
    return re.findall(r'<span class="profile-stat-value">([^<]*)</span>', html)


def table_body(html):
    start = html.index("<tbody>")
    return html[start:html.index("</tbody>", start)]


def category_names(html):
    return re.findall(r'<span class="category-name">([^<]*)</span>', html)


def active_presets(html):
    """Labels of preset links marked aria-current."""
    return re.findall(
        r'<a class="date-preset"[^>]*aria-current="true"[^>]*>([^<]*)</a>', html
    )


def all_expense_rows():
    conn = db.get_db()
    try:
        return [
            tuple(r) for r in conn.execute(
                "SELECT id, user_id, amount, category, date, description "
                "FROM expenses ORDER BY id"
            ).fetchall()
        ]
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# DB helpers with a date range                                        #
# ------------------------------------------------------------------ #

def test_range_clause_builds_fixed_fragments(temp_db):
    assert db._date_range_clause(None, None) == ("", [])
    assert db._date_range_clause("2026-11-01", None) == (
        " AND date >= ?", ["2026-11-01"]
    )
    assert db._date_range_clause(None, "2026-11-10") == (
        " AND date <= ?", ["2026-11-10"]
    )
    fragment, params = db._date_range_clause("2026-11-01", "2026-11-10")
    assert fragment == " AND date >= ? AND date <= ?"
    assert params == ["2026-11-01", "2026-11-10"]
    assert "2026" not in fragment


def test_summary_filters_count_and_total(app):
    summary = db.get_expense_summary(
        demo_id(), start_date=day(1), end_date=day(10)
    )
    assert summary["count"] == 4
    assert round(summary["total"], 2) == 1525.50


def test_summary_bounds_are_inclusive(app):
    summary = db.get_expense_summary(
        demo_id(), start_date=day(3), end_date=day(8)
    )
    assert summary["count"] == 3
    assert round(summary["total"], 2) == 325.50


def test_summary_month_total_ignores_range(app):
    uid = demo_id()
    unfiltered = db.get_expense_summary(uid, today=date.today())
    filtered = db.get_expense_summary(
        uid, today=date.today(), start_date=day(1), end_date=day(3)
    )
    assert filtered["month_total"] == unfiltered["month_total"]
    assert round(filtered["month_total"], 2) == 3820.24


def test_summary_without_range_unchanged(app):
    summary = db.get_expense_summary(demo_id(), today=date.today())
    assert summary["count"] == 8
    assert round(summary["total"], 2) == 3820.24


def test_summary_empty_range_gives_zeros(app):
    summary = db.get_expense_summary(
        demo_id(), today=FIXED_TODAY,
        start_date="2000-01-01", end_date="2000-01-31",
    )
    assert summary["count"] == 0
    assert summary["total"] == 0


def test_recent_expenses_open_start(app):
    rows = db.get_recent_expenses(demo_id(), start_date=day(20))
    assert [r["date"] for r in rows] == [day(25), day(20)]


def test_recent_expenses_open_end(app):
    rows = db.get_recent_expenses(demo_id(), end_date=day(3))
    assert [r["date"] for r in rows] == [day(3), day(1)]


def test_recent_expenses_range_keeps_order_and_limit(app, client):
    uid = new_user(client, "Many", "many@example.com")
    for n in range(1, 16):
        add_expense(uid, n, f"2026-10-{n:02d}", f"Item {n}")
    rows = db.get_recent_expenses(
        uid, start_date="2026-10-02", end_date="2026-10-14"
    )
    assert [r["description"] for r in rows] == [
        f"Item {n}" for n in range(14, 4, -1)
    ]
    rows = db.get_recent_expenses(
        uid, limit=3, start_date="2026-10-02", end_date="2026-10-14"
    )
    assert len(rows) == 3


def test_category_breakdown_percent_of_filtered_total(app):
    breakdown = db.get_category_breakdown(
        demo_id(), start_date=day(1), end_date=day(10)
    )
    assert [b["category"] for b in breakdown] == [
        "Bills", "Health", "Food", "Transport"
    ]
    by_cat = {b["category"]: b for b in breakdown}
    assert by_cat["Bills"]["percent"] == 78.7
    assert by_cat["Health"]["percent"] == 16.4
    assert by_cat["Food"]["percent"] == 3.0
    assert by_cat["Transport"]["percent"] == 2.0
    assert by_cat["Food"]["count"] == 1


def test_category_breakdown_empty_range(app):
    assert db.get_category_breakdown(
        demo_id(), start_date="2000-01-01", end_date="2000-01-31"
    ) == []


def test_helpers_isolate_users_under_range(app, client):
    alice = new_user(client, "Alice", "alice@example.com")
    add_expense(alice, 99.0, day(5), "Alice same-day item")
    rows = db.get_recent_expenses(demo_id(), start_date=day(5), end_date=day(5))
    assert [r["description"] for r in rows] == ["Metro card top-up"]
    assert db.get_expense_summary(
        alice, start_date=day(1), end_date=day(28)
    )["count"] == 1


def test_user_has_expenses(app, client):
    uid = new_user(client, "Empty", "empty@example.com")
    assert db.user_has_expenses(uid) is False
    assert db.user_has_expenses(demo_id()) is True


def test_summary_start_only_is_inclusive(app):
    summary = db.get_expense_summary(
        demo_id(), today=FIXED_TODAY, start_date=day(20)
    )
    assert summary["count"] == 2
    assert round(summary["total"], 2) == 195.75


def test_summary_end_only_is_inclusive(app):
    summary = db.get_expense_summary(
        demo_id(), today=FIXED_TODAY, end_date=day(3)
    )
    assert summary["count"] == 2
    assert round(summary["total"], 2) == 1245.50


def test_summary_single_day_range(app):
    summary = db.get_expense_summary(
        demo_id(), today=FIXED_TODAY, start_date=day(8), end_date=day(8)
    )
    assert summary["count"] == 1
    assert round(summary["total"], 2) == 250.00


def test_recent_expenses_without_range_unchanged(app):
    rows = db.get_recent_expenses(demo_id())
    assert [r["date"] for r in rows] == [
        day(n) for n in (25, 20, 15, 12, 8, 5, 3, 1)
    ]


def test_recent_expenses_same_day_ordered_by_id_desc(app):
    uid = demo_id()
    first = add_expense(uid, 1, day(10), "first")
    second = add_expense(uid, 2, day(10), "second")
    rows = db.get_recent_expenses(uid, start_date=day(10), end_date=day(10))
    assert [r["id"] for r in rows] == [second, first]


def test_recent_expenses_empty_range(app):
    assert db.get_recent_expenses(
        demo_id(), start_date="2000-01-01", end_date="2000-01-31"
    ) == []


def test_category_breakdown_isolates_users_under_range(app, client):
    other = new_user(client, "Other", "other@example.com")
    add_expense(other, 777, day(4), "other in range", category="Shopping")
    categories = {b["category"] for b in db.get_category_breakdown(
        demo_id(), start_date=day(1), end_date=day(10)
    )}
    assert "Shopping" not in categories


def test_helpers_bind_dates_as_parameters(app, client):
    """A quote-laden bound must be compared as a value, not run as SQL."""
    other = new_user(client, "Other", "other@example.com")
    add_expense(other, 999, day(2), "other secret")
    evil = "0' OR '1'='1"
    uid = demo_id()
    assert db.get_recent_expenses(uid, end_date=evil) == []
    assert db.get_category_breakdown(uid, end_date=evil) == []
    assert db.get_expense_summary(
        uid, today=FIXED_TODAY, end_date=evil
    )["count"] == 0


def test_db_helpers_are_read_only(app):
    uid = demo_id()
    before = all_expense_rows()
    db.get_expense_summary(
        uid, today=FIXED_TODAY, start_date=day(1), end_date=day(10)
    )
    db.get_recent_expenses(uid, start_date=day(1), end_date=day(10))
    db.get_category_breakdown(uid, start_date=day(1), end_date=day(10))
    assert all_expense_rows() == before


# ------------------------------------------------------------------ #
# parse_date_filter                                                   #
# ------------------------------------------------------------------ #

def test_parse_no_params(app):
    assert parse() == {"start": None, "end": None, "error": None}


def test_parse_empty_strings(app):
    assert parse(start="", end="") == {"start": None, "end": None, "error": None}


def test_parse_whitespace_only_is_empty(app):
    assert parse(start="   ", end="\t") == {
        "start": None, "end": None, "error": None
    }


def test_parse_strips_surrounding_whitespace(app):
    result = parse(start=" 2026-11-01 ", end="2026-11-10 ")
    assert result == {
        "start": date(2026, 11, 1), "end": date(2026, 11, 10), "error": None
    }


def test_parse_valid_range(app):
    result = parse(start="2026-11-01", end="2026-11-10")
    assert result["start"] == date(2026, 11, 1)
    assert result["end"] == date(2026, 11, 10)
    assert result["error"] is None


def test_parse_open_bounds(app):
    assert parse(start="2026-11-01") == {
        "start": date(2026, 11, 1), "end": None, "error": None
    }
    assert parse(end="2026-11-10") == {
        "start": None, "end": date(2026, 11, 10), "error": None
    }


def test_parse_same_day_range_is_valid(app):
    result = parse(start="2026-11-05", end="2026-11-05")
    assert result["error"] is None
    assert result["start"] == result["end"] == date(2026, 11, 5)


def test_parse_malformed_start(app):
    assert parse(start="abc") == {
        "start": None, "end": None, "error": INVALID_DATE_ERROR
    }


def test_parse_impossible_end_clears_both(app):
    assert parse(start="2026-11-01", end="2026-13-40") == {
        "start": None, "end": None, "error": INVALID_DATE_ERROR
    }


def test_parse_reversed_range(app):
    assert parse(start="2026-11-20", end="2026-11-01") == {
        "start": None, "end": None, "error": DATE_ORDER_ERROR
    }


# ------------------------------------------------------------------ #
# Presets and build_date_filter                                       #
# ------------------------------------------------------------------ #

def test_presets_dates(app):
    from app import date_presets
    presets = {p["key"]: p for p in date_presets(FIXED_TODAY)}
    assert presets["this_month"]["start"] == date(2026, 11, 1)
    assert presets["this_month"]["end"] == FIXED_TODAY
    assert presets["last_30_days"]["start"] == date(2026, 10, 23)
    assert presets["last_30_days"]["end"] == FIXED_TODAY
    assert presets["all_time"]["start"] is None
    assert presets["all_time"]["end"] is None


def test_build_default_is_all_time(app):
    result = build()
    assert result["active"] == ["all_time"]
    assert result["is_active"] is False
    assert result["start_iso"] is None and result["end_iso"] is None


def test_build_this_month_active(app):
    result = build(start="2026-11-01", end="2026-11-21")
    assert result["active"] == ["this_month"]
    assert result["is_active"] is True
    assert result["start_iso"] == "2026-11-01"
    assert result["end_iso"] == "2026-11-21"


def test_build_last_30_days_active(app):
    assert build(start="2026-10-23", end="2026-11-21")["active"] == ["last_30_days"]


def test_build_on_30th_both_matching_presets_active(app):
    """On the 30th, today - 29 days is the 1st, so both presets match."""
    from app import build_date_filter

    result = build_date_filter(
        {"start": "2026-11-01", "end": "2026-11-30"}, today=date(2026, 11, 30)
    )
    assert result["active"] == ["this_month", "last_30_days"]


def test_build_custom_range_has_no_active_preset(app):
    assert build(start="2026-11-01", end="2026-11-10")["active"] == []


def test_build_invalid_input_falls_back_to_all_time(app):
    result = build(start="abc")
    assert result["error"] == INVALID_DATE_ERROR
    assert result["is_active"] is False
    assert result["active"] == ["all_time"]


# ------------------------------------------------------------------ #
# Rendered profile                                                    #
# ------------------------------------------------------------------ #

def test_no_params_page_unchanged(app, client):
    html = get_profile(client)
    assert stat_values(html) == ["8", "₹3,820.24", DEMO_MONTH_TOTAL]
    assert table_body(html).count("<tr>") == 8
    assert len(category_names(html)) == 7
    assert "Filter by date" in html
    assert active_presets(html) == ["All time"]
    assert html.count('<span class="profile-stat-note">All time</span>') == 2
    assert "Selected range" not in html
    assert 'role="alert"' not in html


def test_filter_bar_form_and_inputs(app, client):
    html = get_profile(client)
    assert '<form class="date-filter-form" method="get" action="/profile">' in html
    assert 'type="date" id="filter-start" name="start"' in html
    assert 'type="date" id="filter-end" name="end"' in html
    assert '<label for="filter-start">' in html
    assert '<label for="filter-end">' in html
    assert ">Apply</button>" in html


def test_preset_links_point_to_query_urls(app, client):
    from app import date_presets
    html = get_profile(client)
    presets = {p["key"]: p for p in date_presets(date.today())}
    for key in ("this_month", "last_30_days"):
        p = presets[key]
        href = (
            f'href="/profile?start={p["start"].isoformat()}'
            f'&amp;end={p["end"].isoformat()}"'
        )
        assert href in html
    assert '<a class="date-preset" href="/profile"' in html


def test_filtered_day_1_to_10(app, client):
    html = get_profile(client, f"?start={day(1)}&end={day(10)}")
    assert stat_values(html) == ["4", "₹1,525.50", DEMO_MONTH_TOTAL]
    body = table_body(html)
    assert body.count("<tr>") == 4
    order = [body.index(d) for d in (
        "Pharmacy", "Metro card top-up", "Groceries", "Monthly rent share"
    )]
    assert order == sorted(order)
    for excluded in ("Movie night", "New shoes", "Dinner out"):
        assert excluded not in html
    assert category_names(html) == ["Bills", "Health", "Food", "Transport"]
    assert "78.7%" in html


def test_filtered_view_labels_and_range_line(app, client):
    html = get_profile(client, f"?start={day(1)}&end={day(10)}")
    from app import app as flask_app
    fmt = flask_app.jinja_env.filters["format_date"]
    assert f"Showing {fmt(day(1))} – {fmt(day(10))}" in html
    assert html.count('<span class="profile-stat-note">Selected range</span>') == 2
    assert f'value="{day(1)}"' in html
    assert f'value="{day(10)}"' in html


def test_only_start_shows_since_and_later_expenses(app, client):
    html = get_profile(client, f"?start={day(20)}")
    body = table_body(html)
    assert body.count("<tr>") == 2
    assert "Dinner out" in body
    assert "₹75.00" in body
    from app import app as flask_app
    fmt = flask_app.jinja_env.filters["format_date"]
    assert f"Since {fmt(day(20))}" in html
    assert stat_values(html)[0] == "2"


def test_only_end_shows_up_to_and_earlier_expenses(app, client):
    html = get_profile(client, f"?end={day(3)}")
    body = table_body(html)
    assert body.count("<tr>") == 2
    assert "Monthly rent share" in body
    assert "Groceries" in body
    from app import app as flask_app
    fmt = flask_app.jinja_env.filters["format_date"]
    assert f"Up to {fmt(day(3))}" in html
    assert stat_values(html)[:2] == ["2", "₹1,245.50"]


def test_this_month_preset_highlighted(app, client):
    today = date.today()
    html = get_profile(
        client, f"?start={today.replace(day=1).isoformat()}&end={today.isoformat()}"
    )
    assert "This month" in active_presets(html)
    assert "All time" not in active_presets(html)


def test_last_30_days_preset_highlighted(app, client):
    today = date.today()
    start = (today - timedelta(days=29)).isoformat()
    html = get_profile(client, f"?start={start}&end={today.isoformat()}")
    # On the 30th "This month" covers the same range and is marked too.
    assert "Last 30 days" in active_presets(html)
    assert "All time" not in active_presets(html)


def test_custom_range_highlights_no_preset(app, client):
    html = get_profile(client, f"?start={day(2)}&end={day(4)}")
    assert active_presets(html) == []


def test_empty_period_message(app, client):
    html = get_profile(client, "?start=2000-01-01&end=2000-01-31")
    assert "No expenses in this period." in html
    assert "No expenses yet." not in html
    assert stat_values(html) == ["0", "₹0.00", DEMO_MONTH_TOTAL]
    assert "Recent transactions" not in html
    assert "<tbody>" not in html
    assert "Spending by category" not in html


def test_new_user_with_filter_sees_no_expenses_yet(app, client):
    register(client, "Fresh", "fresh@example.com")
    html = get_profile(
        client, "?start=2000-01-01&end=2000-01-31",
        email="fresh@example.com", password="password123",
    )
    assert "No expenses yet." in html
    assert "No expenses in this period." not in html


def test_malformed_start_shows_error_and_unfiltered_data(app, client):
    html = get_profile(client, "?start=abc")
    assert f'<div class="auth-error" role="alert">{INVALID_DATE_ERROR}</div>' in html
    assert stat_values(html) == ["8", "₹3,820.24", DEMO_MONTH_TOTAL]
    assert table_body(html).count("<tr>") == 8
    assert active_presets(html) == ["All time"]


def test_impossible_end_date_returns_200_with_error(app, client):
    html = get_profile(client, f"?start={day(1)}&end=2026-13-40")
    assert INVALID_DATE_ERROR in html
    assert stat_values(html)[0] == "8"


def test_reversed_range_shows_error_and_unfiltered_data(app, client):
    html = get_profile(client, "?start=2026-11-20&end=2026-11-01")
    assert f'<div class="auth-error" role="alert">{DATE_ORDER_ERROR}</div>' in html
    assert stat_values(html) == ["8", "₹3,820.24", DEMO_MONTH_TOTAL]
    assert table_body(html).count("<tr>") == 8
    assert "Showing" not in html


def test_sql_like_input_is_rejected_as_invalid(app, client):
    html = get_profile(client, "?start=2026-11-01'%20OR%20'1'='1")
    assert INVALID_DATE_ERROR in html
    assert stat_values(html)[0] == "8"


def test_filtered_view_isolates_users(app, client):
    alice = new_user(client, "Alice", "alice@example.com")
    bob = new_user(client, "Bob", "bob@example.com")
    add_expense(alice, 11.11, day(5), "Alice secret lunch")
    add_expense(bob, 22.22, day(5), "Bob secret taxi")
    query = f"?start={day(1)}&end={day(10)}"

    alice_html = get_profile(client, query, "alice@example.com", "password123")
    assert "Alice secret lunch" in alice_html
    assert "Bob secret taxi" not in alice_html
    assert "Monthly rent share" not in alice_html
    assert stat_values(alice_html)[:2] == ["1", "₹11.11"]
    client.get("/logout")

    demo_html = get_profile(client, query)
    assert "Alice secret lunch" not in demo_html
    assert "Bob secret taxi" not in demo_html
    assert stat_values(demo_html)[:2] == ["4", "₹1,525.50"]


def test_user_id_query_param_is_ignored(app, client):
    alice = new_user(client, "Alice", "alice@example.com")
    add_expense(alice, 11.11, day(5), "Alice secret lunch")
    html = get_profile(
        client, f"?start={day(1)}&end={day(10)}&user_id={alice}"
    )
    assert "Alice secret lunch" not in html
    assert stat_values(html)[0] == "4"


def test_logged_out_filtered_profile_redirects_to_login(client):
    response = client.get(f"/profile?start={day(1)}&end={day(10)}")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_filter_bar_appears_above_summary(app, client):
    html = get_profile(client)
    assert html.index("Filter by date") < html.index("Spending summary")


def test_new_user_without_filter_sees_no_expenses_yet(app, client):
    register(client, "Fresh", "fresh@example.com")
    html = get_profile(client, email="fresh@example.com", password="password123")
    assert "No expenses yet." in html
    assert "No expenses in this period." not in html


def test_valid_filter_shows_no_error(app, client):
    html = get_profile(client, f"?start={day(1)}&end={day(10)}")
    assert INVALID_DATE_ERROR not in html
    assert DATE_ORDER_ERROR not in html
    assert 'role="alert"' not in html


def test_filtering_does_not_modify_expenses(app, client):
    login(client)
    before = all_expense_rows()
    for query in (
        f"?start={day(1)}&end={day(10)}",
        f"?start={day(20)}",
        f"?end={day(3)}",
        "?start=abc",
        "?start=2026-11-20&end=2026-11-01",
    ):
        assert client.get("/profile" + query).status_code == 200
    assert all_expense_rows() == before


def test_filtered_profile_deleted_user_session_cleared(app, client):
    uid = new_user(client, "Gone", "gone@example.com")
    login(client, "gone@example.com", "password123")
    conn = db.get_db()
    try:
        conn.execute("DELETE FROM users WHERE id = ?", (uid,))
        conn.commit()
    finally:
        conn.close()
    response = client.get(f"/profile?start={day(1)}")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    with client.session_transaction() as sess:
        assert "user_id" not in sess
