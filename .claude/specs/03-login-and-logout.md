# Spec: Login and Logout

## Overview
Let registered users sign in and sign out. Today `GET /login` renders
`login.html`, but the form posts to a route that only accepts GET (so
submitting it fails with 405), and `GET /logout` is a stub that returns a
raw string. This step adds `POST /login`, which checks the email and
password against the werkzeug hash in `users` and stores the user in the
Flask session. It also replaces the `/logout` stub with a route that
clears the session. The navbar in `base.html` changes based on login
state. Step 2 (registration) creates real users, and this step gives
them a session. Later steps (profile in Step 4, expense CRUD in Steps 7–9)
need to know who the current user is, and this step provides that.

## Depends on
- **Step 1 — Database setup**: `users` table, `get_db()`, and the seeded demo
  user (`demo@spendly.com` / `demo123`).
- **Step 2 — Registration**: `get_user_by_email()` in `database/db.py`,
  `app.secret_key` (sessions need it), and the flash-message block in
  `login.html`.

## Routes
- `GET /login` — render the sign-in form (already exists; now shares a
  function with POST). If the user is already logged in, redirect to
  `url_for('profile')` — public
- `POST /login` — normalise the email (`.strip().lower()`), check the
  credentials, and on success clear the session, set `session["user_id"]` and
  `session["user_name"]`, flash a welcome message, and redirect to
  `url_for('profile')`. On failure, re-render `login.html` with HTTP 401, the
  generic error "Invalid email or password.", and the submitted email filled
  back in (never the password) — public
- `GET /logout` — replace the stub. Run `session.clear()`, flash "You have been
  signed out.", and redirect to `url_for('landing')`. Safe to call when not
  logged in — public
- `GET /register` — small change: if the user is already logged in, redirect
  to `url_for('profile')` — public

`/profile` stays a stub (Step 4). Redirecting there after login is expected to
show the Step 4 placeholder text for now.

## Database changes
No database changes. The `users` table already has `email` and
`password_hash`.

New helper in `database/db.py` (no schema change):
- `authenticate_user(email, password)` — looks the user up with
  `get_user_by_email()`, checks the password with werkzeug
  `check_password_hash`, and returns the user row on success or `None` on
  failure (unknown email or wrong password: the caller cannot tell which).

## Templates
- **Create:** none
- **Modify:**
  - `templates/login.html` — change `action="/login"` to
    `action="{{ url_for('login') }}"`. Add `value="{{ email or '' }}"` to the
    email input so it keeps its value after an error.
  - `templates/base.html` — navbar is conditional on `session.get('user_id')`:
    - logged out: keep the "Sign in" and "Get started" links
    - logged in: show the user's name (`session.get('user_name')`), a link to
      `url_for('profile')`, and a "Sign out" link to `url_for('logout')`
    - Render flashed messages once in `base.html` (above `{% block content %}`),
      using `.auth-success` / `.auth-error`, so the "signed out" message shows
      on the landing page. Remove the duplicate flash block from `login.html`
      so messages do not show twice.

## Files to change
- `app.py` — import `session` and `authenticate_user`. Make `login()` accept
  `methods=["GET", "POST"]`. Replace the `logout()` stub. Add the
  "already logged in" redirect to `login()` and `register()`.
- `database/db.py` — add `authenticate_user()` and import `check_password_hash`.
- `templates/login.html` — see Templates.
- `templates/base.html` — see Templates.
- `static/css/style.css` — add styles for the logged-in navbar items (user name
  label, sign-out link) and a wrapper for the flash messages in `base.html`,
  using existing CSS variables only.
- `CLAUDE.md` — mark `POST /login` and `GET /logout` as implemented (Step 3)
  in the routes table.

## Files to create
- `tests/test_auth.py` — route tests with the Flask test client and the `app`
  fixture from `tests/conftest.py` (temp DB, seeded demo user).

## New dependencies
No new dependencies. `flask` (sessions) and `werkzeug` (`check_password_hash`)
are already in `requirements.txt`.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders), never f-strings in SQL
- Passwords hashed with werkzeug: check them with `check_password_hash`,
  never compare plain text, never log or flash the password
- Use CSS variables; never hardcode hex values
- All templates extend `base.html`
- All DB access goes through `database/db.py` helpers; no SQL or password
  checks in `app.py`
- Use `url_for()` for every internal link, redirect and form action
- Use Flask's built-in signed-cookie `session`; no Flask-Login or other
  packages
- Store only `user_id` and `user_name` in the session, never the password hash
- Call `session.clear()` before setting the user on login (prevents session
  fixation) and on logout
- One generic error for every failed login ("Invalid email or password."), so
  the page never shows whether an email is registered
- Do not apply the 8-character minimum from registration to login: the seeded
  demo password `demo123` is 7 characters and must still work
- An empty email or password is a failed login (HTTP 401, same generic
  error), not a 500
- Do not implement the profile page or a `login_required` guard on other
  routes; those belong to Step 4 and later
- Route functions stay thin: read the form, call the db helper, set the
  session, then render or redirect

## Definition of done
- [ ] `GET /login` renders the form with a 200 status
- [ ] Signing in as `demo@spendly.com` / `demo123` redirects to `/profile`,
      and the session contains `user_id` for the demo user
- [ ] Signing in with ` Demo@Spendly.com ` (mixed case, spaces) also works
- [ ] A user created through `/register` can then sign in with the same
      credentials
- [ ] A wrong password, an unknown email, or empty fields each re-render the
      form with HTTP 401 and "Invalid email or password." and set no session
- [ ] After a failed login the email field keeps its value and the password
      field is empty
- [ ] When logged in, the navbar shows the user's name and a "Sign out" link
      instead of "Sign in" / "Get started"
- [ ] Visiting `/login` or `/register` while logged in redirects to `/profile`
- [ ] `GET /logout` clears the session, redirects to `/`, and shows "You have
      been signed out."; the navbar is back to "Sign in" / "Get started"
- [ ] `GET /logout` while not logged in still redirects to `/` with no error
- [ ] Flash messages appear once (not duplicated) on the login page after
      registration
- [ ] The login form's `action` uses `url_for('login')`, with no hardcoded URL
- [ ] `pytest` passes, including the new `tests/test_auth.py` and the existing
      `tests/test_registration.py`
- [ ] The app still starts with `python app.py` on port 5001
