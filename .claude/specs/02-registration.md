# Spec: Registration

## Overview
Make the existing registration page actually create accounts. Today
`GET /register` renders `register.html`, but the form posts to a route
that only accepts GET, so submitting it fails with 405. This step adds
`POST /register`. It validates the name, email and password, stores
the new user with a werkzeug-hashed password, and redirects to the
login page with a success message. Registration is the first piece of
authentication on the Spendly roadmap. It builds on the `users` table
from Step 1, and Step 3 (login/logout) needs it so that real users
exist to sign in. This step does not log the user in or create a
session. That is Step 3's job.

## Depends on
- **Step 1 — Database setup**: the `users` table (`id`, `name`, `email UNIQUE`,
  `password_hash`, `created_at`) and `get_db()` in `database/db.py`.

## Routes
- `GET /register` — render the registration form (already exists; keep as is, now
  sharing a function with POST) — public
- `POST /register` — validate the form, create the user, then `redirect` to
  `url_for('login')` with a flashed success message. On a validation error,
  re-render `register.html` with HTTP 400, an `error` message, and the submitted
  `name` and `email` filled back in (never the password) — public

## Database changes
No database changes. The `users` table in `database/db.py` already has every
column needed, and the `UNIQUE` constraint on `email` is the final guard
against duplicate accounts.

New helper functions in `database/db.py` (no schema change):
- `get_user_by_email(email)` — returns the `sqlite3.Row` for the user, or `None`
- `create_user(name, email, password)` — hashes the password with
  `generate_password_hash` and inserts the row with a parameterised query.
  Returns the new user id. Raises `sqlite3.IntegrityError` on a duplicate email
  so the caller can handle a race between the check and the insert.

## Templates
- **Create:** none
- **Modify:**
  - `templates/register.html` — change `action="/register"` to
    `action="{{ url_for('register') }}"`. Add `value="{{ name or '' }}"` /
    `value="{{ email or '' }}"` to keep entered values after an error. Add
    `minlength="8"` to the password input.
  - `templates/login.html` — render flashed messages
    (`get_flashed_messages(with_categories=true)`) above the form so the
    "Account created" message shows after the redirect.

## Files to change
- `app.py` — set `app.secret_key` (from the `SECRET_KEY` env var, with a dev
  fallback; flashing needs it). Change `register()` to accept
  `methods=["GET", "POST"]`. Import `request`, `redirect`, `url_for` and
  `flash`, and import the new db helpers.
- `database/db.py` — add `get_user_by_email()` and `create_user()`.
- `templates/register.html` — see Templates.
- `templates/login.html` — see Templates.
- `static/css/style.css` — add an `.auth-success` style next to the existing
  `.auth-error`, using `var(--accent)` and `var(--accent-light)`.

## Files to create
- `tests/test_registration.py` — route tests using the Flask test client
  against the `temp_db` fixture from `tests/conftest.py`.

## New dependencies
No new dependencies. `flask` and `werkzeug` are already in `requirements.txt`.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders), never f-strings in SQL
- Passwords hashed with werkzeug `generate_password_hash`; never store or log
  the plain password
- Use CSS variables; never hardcode hex values
- All templates extend `base.html`
- All DB access goes through `database/db.py` helpers; no SQL in `app.py`
- Use `url_for()` for every internal link and form action
- Validation rules, checked server-side (the HTML `required`/`minlength`
  attributes are a convenience only):
  - `name`: required after `.strip()`
  - `email`: required, `.strip().lower()` before checking and storing, and
    must contain `@` with a `.` in the domain part
  - `password`: at least 8 characters
  - email must not already exist; message: "An account with that email already exists."
- Show one error at a time, using the existing `{% if error %}` block in `register.html`
- Catch `sqlite3.IntegrityError` from `create_user()` and show the
  duplicate-email error instead of a 500
- Do not implement login, sessions or `/logout`; those belong to Step 3
- Route function stays thin: read the form, call the validation and db helpers,
  then render or redirect

## Definition of done
- [ ] `GET /register` renders the form with a 200 status
- [ ] Submitting valid name/email/password creates a row in `users`, and
      `password_hash` is not the plain password (it starts with a werkzeug
      hash prefix such as `scrypt:` or `pbkdf2:`)
- [ ] After a successful sign-up the browser lands on `/login` and shows an
      "Account created" success message
- [ ] An email entered as `Test@Example.com ` is stored as `test@example.com`
- [ ] Registering with `demo@spendly.com` (the seeded user) shows "An account
      with that email already exists." and creates no new row
- [ ] An empty name, an invalid email, or a password shorter than 8
      characters each re-render the form with a clear error and HTTP 400
- [ ] After an error, the name and email fields keep their values and the
      password field is empty
- [ ] The register form's `action` uses `url_for('register')`, with no hardcoded URL
- [ ] `pytest` passes, including the new `tests/test_registration.py`
- [ ] The app still starts with `python app.py` on port 5001
