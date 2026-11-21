import os
import sqlite3
from datetime import date, datetime, timedelta
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
    user_has_expenses,
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

def profile_summary_context(user_id, start_date=None, end_date=None):
    """Template context for the profile's summary stat tiles."""
    return {
        "summary": get_expense_summary(
            user_id, start_date=start_date, end_date=end_date
        )
    }

# ---------------------- end summary stats ------------------------- #


# ------------------------------------------------------------------ #
# Profile data — transaction history                                  #
# ------------------------------------------------------------------ #

def profile_transactions_context(user_id, start_date=None, end_date=None):
    """Template context for the profile's recent-transactions table."""
    return {
        "recent_expenses": get_recent_expenses(
            user_id, start_date=start_date, end_date=end_date
        )
    }


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

def profile_categories_context(user_id, start_date=None, end_date=None):
    """Template context for the profile's spending-by-category bars."""
    return {
        "category_breakdown": get_category_breakdown(
            user_id, start_date=start_date, end_date=end_date
        )
    }

# -------------------- end category breakdown ---------------------- #


# ------------------------------------------------------------------ #
# Profile data — date range filter                                    #
# ------------------------------------------------------------------ #

INVALID_DATE_ERROR = "Please enter valid dates."
DATE_ORDER_ERROR = "Start date must be on or before end date."


def parse_date_filter(args):
    """Parse optional 'start'/'end' ISO dates from query args.

    Returns {"start", "end", "error"} with date objects or None. Any
    invalid input clears both bounds and sets an error message.
    """
    bounds = {}
    for key in ("start", "end"):
        raw = (args.get(key) or "").strip()
        if not raw:
            bounds[key] = None
            continue
        try:
            bounds[key] = date.fromisoformat(raw)
        except ValueError:
            return {"start": None, "end": None, "error": INVALID_DATE_ERROR}

    start, end = bounds["start"], bounds["end"]
    if start and end and start > end:
        return {"start": None, "end": None, "error": DATE_ORDER_ERROR}
    return {"start": start, "end": end, "error": None}


def _preset(key, label, start, end):
    """One preset, with the query params its link needs ({} = no filter)."""
    params = {"start": start.isoformat(), "end": end.isoformat()} if start else {}
    return {"key": key, "label": label, "start": start, "end": end,
            "params": params}


def date_presets(today):
    """Return the quick-pick date ranges shown above the profile stats."""
    return [
        _preset("this_month", "This month", today.replace(day=1), today),
        _preset("last_30_days", "Last 30 days",
                today - timedelta(days=29), today),
        _preset("all_time", "All time", None, None),
    ]


def build_date_filter(args, today=None):
    """Template context describing the active profile date filter."""
    parsed = parse_date_filter(args)
    presets = date_presets(today or date.today())
    # A list, not one key: on the 30th "This month" and "Last 30 days"
    # cover the same range, and both should be highlighted.
    active = [
        p["key"] for p in presets
        if (p["start"], p["end"]) == (parsed["start"], parsed["end"])
    ]
    is_active = bool(parsed["start"] or parsed["end"])
    return {
        **parsed,
        "start_iso": parsed["start"].isoformat() if parsed["start"] else None,
        "end_iso": parsed["end"].isoformat() if parsed["end"] else None,
        "is_active": is_active,
        "scope_label": "Selected range" if is_active else "All time",
        "presets": presets,
        "active": active,
    }


def profile_empty_state_context(user_id, summary, date_filter):
    """Whether the user has any expenses at all, for the empty-state text.

    Only queries when the filtered count is 0 under an active filter.
    """
    has_any = summary["count"] > 0 or (
        date_filter["is_active"] and user_has_expenses(user_id)
    )
    return {"has_any_expenses": has_any}

# ------------------- end date range filter ------------------------ #


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
    date_filter = build_date_filter(request.args)
    date_range = (date_filter["start_iso"], date_filter["end_iso"])
    summary_context = profile_summary_context(user["id"], *date_range)
    return render_template(
        "profile.html",
        user=user,
        date_filter=date_filter,
        **summary_context,
        **profile_empty_state_context(
            user["id"], summary_context["summary"], date_filter
        ),
        **profile_transactions_context(user["id"], *date_range),
        **profile_categories_context(user["id"], *date_range),
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
