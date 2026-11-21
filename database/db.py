import os
import sqlite3
from datetime import date, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "expense_tracker.db")

CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]


def get_db():
    """Return a SQLite connection with dict-like rows and FK enforcement on."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all tables. Safe to call multiple times."""
    conn = get_db()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                email         TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at    TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL
                            REFERENCES users(id) ON DELETE CASCADE,
                amount      REAL NOT NULL,
                category    TEXT NOT NULL,
                date        TEXT NOT NULL,
                description TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def seed_db():
    """Insert a demo user and sample expenses. No-op if users already exist."""
    conn = get_db()
    try:
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if user_count > 0:
            return

        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", "demo@spendly.com", generate_password_hash("demo123")),
        )
        user_id = cursor.lastrowid

        today = date.today()
        # (day of month, amount, category, description) — days <= 28 are
        # valid in every month.
        samples = [
            (1, 1200.00, "Bills", "Monthly rent share"),
            (3, 45.50, "Food", "Groceries"),
            (5, 30.00, "Transport", "Metro card top-up"),
            (8, 250.00, "Health", "Pharmacy"),
            (12, 499.00, "Entertainment", "Movie night"),
            (15, 1599.99, "Shopping", "New shoes"),
            (20, 120.75, "Food", "Dinner out"),
            (25, 75.00, "Other", None),
        ]
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, amount, category, today.replace(day=day).isoformat(), desc)
                for day, amount, category, desc in samples
            ],
        )
        conn.commit()
    finally:
        conn.close()


def get_user_by_email(email):
    """Return the user row for this email, or None."""
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, name, email, password_hash, created_at "
            "FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    finally:
        conn.close()


def create_user(name, email, password):
    """Insert a user with a hashed password and return the new id.

    Raises sqlite3.IntegrityError if the email is already registered.
    """
    password_hash = generate_password_hash(password)
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def authenticate_user(email, password):
    """Return the user row if email and password match, otherwise None.

    Unknown email and wrong password both return None, so callers cannot
    reveal which one failed.
    """
    if not email or not password:
        return None
    user = get_user_by_email(email)
    if user is None or not check_password_hash(user["password_hash"], password):
        return None
    return user


def get_user_by_id(user_id):
    """Return id, name, email, created_at for this user, or None.

    Never selects password_hash: this is for display.
    """
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# Summary stats                                                       #
# ------------------------------------------------------------------ #

def get_expense_summary(user_id, today=None):
    """Return {"count", "total", "month_total"} for this user's expenses.

    month_total covers the calendar month containing `today`
    (defaults to date.today()). A user with no expenses gets zeros.
    """
    today = today or date.today()
    month_start = today.replace(day=1)
    next_month_start = (month_start.replace(day=28) + timedelta(days=4)).replace(
        day=1
    )
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*), "
            "COALESCE(SUM(amount), 0), "
            "COALESCE(SUM(CASE WHEN date >= ? AND date < ? "
            "THEN amount END), 0) "
            "FROM expenses WHERE user_id = ?",
            (month_start.isoformat(), next_month_start.isoformat(), user_id),
        ).fetchone()
    finally:
        conn.close()
    return {"count": row[0], "total": row[1], "month_total": row[2]}

# ---------------------- end summary stats ------------------------- #


# ------------------------------------------------------------------ #
# Transaction history                                                 #
# ------------------------------------------------------------------ #

def get_recent_expenses(user_id, limit=10):
    """Return up to `limit` of this user's expenses, newest first.

    Rows have id, amount, category, date, description and are sorted by
    date DESC, id DESC so same-day ties show the newest insert first.
    A user with no expenses gets [].
    """
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, amount, category, date, description "
            "FROM expenses WHERE user_id = ? "
            "ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    finally:
        conn.close()

# -------------------- end transaction history --------------------- #


# ------------------------------------------------------------------ #
# Category breakdown                                                  #
# ------------------------------------------------------------------ #

def get_category_breakdown(user_id):
    """Return this user's spending per category, largest first.

    Each item is {"category", "total", "count", "percent"}, where percent
    is the category's share of the user's overall total (1 decimal).
    Ties on total are ordered by category name. No expenses gives [].
    """
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount), COUNT(*) "
            "FROM expenses WHERE user_id = ? "
            "GROUP BY category "
            "ORDER BY SUM(amount) DESC, category ASC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    overall_total = sum(row[1] for row in rows)
    breakdown = []
    for category, total, count in rows:
        percent = round(total / overall_total * 100, 1) if overall_total else 0.0
        breakdown.append(
            {"category": category, "total": total, "count": count, "percent": percent}
        )
    return breakdown

# -------------------- end category breakdown ---------------------- #
