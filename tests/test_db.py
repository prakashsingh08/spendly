import sqlite3
from datetime import date

import pytest
from werkzeug.security import check_password_hash

from database import db


def test_tables_exist(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    names = {row["name"] for row in rows}
    assert {"users", "expenses"} <= names


def test_init_db_is_idempotent(temp_db):
    db.init_db()
    db.init_db()
    conn = db.get_db()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name IN ('users', 'expenses')"
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 2


def test_seed_inserts_once(conn):
    db.seed_db()
    db.seed_db()
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 8
    categories = {
        row["category"]
        for row in conn.execute("SELECT DISTINCT category FROM expenses")
    }
    assert categories == set(db.CATEGORIES)


def test_seed_dates_in_current_month(conn):
    db.seed_db()
    prefix = date.today().strftime("%Y-%m")
    for row in conn.execute("SELECT date FROM expenses"):
        assert date.fromisoformat(row["date"]).isoformat() == row["date"]
        assert row["date"].startswith(prefix)


def test_demo_user_password_is_hashed(conn):
    db.seed_db()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?", ("demo@spendly.com",)
    ).fetchone()
    assert user["name"] == "Demo User"
    assert user["password_hash"] != "demo123"
    assert check_password_hash(user["password_hash"], "demo123")


def test_duplicate_email_rejected(conn):
    db.seed_db()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Someone", "demo@spendly.com", "x"),
        )


def test_foreign_keys_enforced(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date) "
            "VALUES (?, ?, ?, ?)",
            (9999, 10.0, "Food", "2026-01-01"),
        )


def test_row_factory_dict_access(conn):
    db.seed_db()
    row = conn.execute("SELECT * FROM users").fetchone()
    assert row["email"] == "demo@spendly.com"
    assert set(dict(row)) == {
        "id", "name", "email", "password_hash", "created_at"
    }
    assert row["created_at"] is not None


def test_amount_stored_as_real(conn):
    db.seed_db()
    types = {
        row[0] for row in conn.execute("SELECT typeof(amount) FROM expenses")
    }
    assert types == {"real"}


def test_deleting_user_cascades_to_expenses(conn):
    db.seed_db()
    conn.execute("DELETE FROM users WHERE email = ?", ("demo@spendly.com",))
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 0
