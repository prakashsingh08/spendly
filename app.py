import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from database.db import (
    authenticate_user,
    create_user,
    get_category_breakdown,
    get_db,
    get_expense_summary,
    get_recent_expenses,
    get_user_by_email,
    get_user_by_id,
    init_db,
    seed_db,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Validation                                                          #
# ------------------------------------------------------------------ #

NAME_REQUIRED_ERROR = "Please enter your name."
INVALID_EMAIL_ERROR = "Please enter a valid email address."
SHORT_PASSWORD_ERROR = "Password must be at least 8 characters."
DUPLICATE_EMAIL_ERROR = "An account with that email already exists."
INVALID_LOGIN_ERROR = "Invalid email or password."
MIN_PASSWORD_LENGTH = 8


def is_valid_email(email):
    local, sep, domain = email.rpartition("@")
    return (
        bool(sep)
        and bool(local)
        and "." in domain
        and not domain.startswith(".")
        and not domain.endswith(".")
    )


def validate_registration(name, email, password):
    """Return the first validation error message, or None if all valid."""
    if not name:
        return NAME_REQUIRED_ERROR
    if not is_valid_email(email):
        return INVALID_EMAIL_ERROR
    if len(password) < MIN_PASSWORD_LENGTH:
        return SHORT_PASSWORD_ERROR
    return None


# ------------------------------------------------------------------ #
# Auth helpers                                                        #
# ------------------------------------------------------------------ #

LOGIN_REQUIRED_MESSAGE = "Please sign in to continue."


def login_required(view):
    """Redirect to the login page unless a user is in the session."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash(LOGIN_REQUIRED_MESSAGE, "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


# ------------------------------------------------------------------ #
# Template filters                                                    #
# ------------------------------------------------------------------ #

@app.template_filter("member_since")
def member_since(value):
    """Format a SQLite 'YYYY-MM-DD HH:MM:SS' timestamp as '20 Nov 2026'."""
    if not value:
        return ""
    return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%d %b %Y")


# ------------------------------------------------------------------ #
# Profile data — summary stats                                        #
# ------------------------------------------------------------------ #

def profile_summary_context(user_id):
    """Template context for the profile's summary stat tiles."""
    return {"summary": get_expense_summary(user_id)}

# ---------------------- end summary stats ------------------------- #


# ------------------------------------------------------------------ #
# Profile data — transaction history                                  #
# ------------------------------------------------------------------ #

def profile_transactions_context(user_id):
    """Template context for the profile's recent-transactions table."""
    return {"recent_expenses": get_recent_expenses(user_id)}


@app.template_filter("format_date")
def format_date(value):
    """Format an ISO 'YYYY-MM-DD' (or longer timestamp) as '20 Nov 2026'."""
    if not value:
        return ""
    return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%d %b %Y")

# -------------------- end transaction history --------------------- #


# ------------------------------------------------------------------ #
# Profile data — category breakdown                                   #
# ------------------------------------------------------------------ #

def profile_categories_context(user_id):
    """Template context for the profile's spending-by-category bars."""
    return {"category_breakdown": get_category_breakdown(user_id)}

# -------------------- end category breakdown ---------------------- #


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    error = validate_registration(name, email, password)
    if error is None and get_user_by_email(email) is not None:
        error = DUPLICATE_EMAIL_ERROR
    if error is None:
        try:
            create_user(name, email, password)
        except sqlite3.IntegrityError:
            error = DUPLICATE_EMAIL_ERROR

    if error:
        return render_template(
            "register.html", error=error, name=name, email=email
        ), 400

    flash("Account created! Please sign in.", "success")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    user = authenticate_user(email, password)
    if user is None:
        return render_template(
            "login.html", error=INVALID_LOGIN_ERROR, email=email
        ), 401

    # Clear first to prevent session fixation; flash after, or it is wiped.
    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    flash(f"Welcome back, {user['name']}!", "success")
    return redirect(url_for("profile"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("landing"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/profile")
@login_required
def profile():
    user = get_user_by_id(session["user_id"])
    if user is None:
        # Session points at a deleted user: treat as signed out.
        session.clear()
        flash(LOGIN_REQUIRED_MESSAGE, "error")
        return redirect(url_for("login"))
    return render_template(
        "profile.html",
        user=user,
        **profile_summary_context(user["id"]),
        **profile_transactions_context(user["id"]),
        **profile_categories_context(user["id"]),
    )


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
