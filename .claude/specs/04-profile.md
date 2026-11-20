# Spec: Profile

## Overview
Replace the `/profile` stub with a real page for the logged-in user. Right
now login (Step 3) sends users to `/profile`, but the route returns a raw
"coming in Step 4" string: it ignores `base.html`, so the navbar and flash
messages don't show. It is also reachable without signing in. This step adds
a reusable `login_required` decorator and puts it on `/profile`. It also
renders a `profile.html` template that shows the user's account details
(name, email, member since) and a short spending summary (number of
expenses, total spent, spent this month) from the `expenses` table. This is
the first page that reads per-user data, and the `login_required` guard it
adds will be reused by the expense routes in Steps 7–9.

## Depends on
- **Step 1 — Database setup**: `users` and `expenses` tables, `get_db()`, and
  the seeded demo user with 8 expenses dated in the current month.
- **Step 2 — Registration**: real users with `created_at` timestamps.
- **Step 3 — Login and logout**: `session["user_id"]` / `session["user_name"]`,
  flash messages rendered in `base.html`, and the redirect to `/profile`
  after login.

## Routes
- `GET /profile` — replace the stub. Load the current user and their expense
  summary, then render `profile.html` — logged-in
  - Not logged in: redirect to `url_for('login')` and flash "Please sign in to
    continue." (category `error`)
  - `session["user_id"]` points to a user that no longer exists: run
    `session.clear()`, flash the same message, and redirect to `/login`. Don't
    return a 500.

No other new routes. The `login_required` decorator is defined in `app.py` but
in this step it only goes on `/profile`. The expense stubs stay untouched
until their own steps.

## Database changes
No database changes. `users` already has `name`, `email` and `created_at`, and
`expenses` already has `user_id`, `amount` and `date`.

New helpers in `database/db.py` (no schema change):
- `get_user_by_id(user_id)` — returns `id, name, email, created_at` (never
  `password_hash`) or `None`.
- `get_expense_summary(user_id)` — returns a dict with:
  - `count`: number of expenses for the user
  - `total`: `COALESCE(SUM(amount), 0)` over all of the user's expenses
  - `month_total`: the same sum, limited to the current month, using
    `date >= ?` and `date < ?` with the first day of this month and of next
    month passed as ISO strings (no string formatting in the SQL)

  Every query filters on `user_id = ?`, so a user never sees another user's
  data. A user with no expenses gets `0` for all three values. That is not
  an error.

## Templates
- **Create:**
  - `templates/profile.html` — extends `base.html` and loads
    `css/profile.css` in `{% block head %}`. It contains:
    - a header with the user's name
    - an "Account" card showing name, email, and "Member since" (the date
      part of `created_at`, shown e.g. as `20 Nov 2026`)
    - a "Spending summary" section with three stat tiles: Expenses (count),
      Total spent, and This month. Amounts are shown as `₹` with two decimals
      and thousands separators (e.g. `₹3,820.24`), formatted in Jinja
      (`"{:,.2f}".format(...)`) and not stored as strings.
    - an empty-state line when `count` is 0: "No expenses yet."
- **Modify:**
  - None. `base.html` already has the Profile link and renders flash messages.

## Files to change
- `app.py`:
  - import `wraps` from `functools`
  - add a `login_required` decorator
  - replace the `profile()` stub and move it out of the "Placeholder routes"
    section
  - import `get_user_by_id` and `get_expense_summary`
- `database/db.py` — add `get_user_by_id()` and `get_expense_summary()`.
- `CLAUDE.md`:
  - mark `GET /profile` as implemented (Step 4)
  - optionally fix the stale "`database/db.py` is currently empty" warning

## Files to create
- `templates/profile.html`
- `static/css/profile.css` — styles specific to the profile page (cards, stat
  grid, responsive stacking at ≤600px), using only the existing CSS variables
  from `style.css` `:root`.
- `tests/test_profile.py` — route and helper tests using the pytest-flask
  `client` fixture, the `app` fixture and `temp_db` from `tests/conftest.py`.

## New dependencies
No new dependencies. `functools.wraps` and `datetime` are in the standard
library.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders), never f-strings in SQL
- Passwords hashed with werkzeug: never select, pass, or render
  `password_hash` on the profile page
- Use CSS variables; never hardcode hex values
- All templates extend `base.html`
- Page-specific styles go in `static/css/profile.css`, not inline `<style>`
  tags
- All DB access goes through `database/db.py` helpers; no SQL in `app.py`
- Use `url_for()` for every internal link and redirect
- `login_required` uses `functools.wraps` so `url_for('profile')` keeps
  working
- The route only reads `session["user_id"]`. Never trust a user id from the
  query string or form.
- The route stays thin: get the user and the summary, then render
- Do not add profile editing, password change, an expense list, or a
  dashboard. Those belong to later steps.
- Do not implement the expense add/edit/delete stubs

## Definition of done
- [ ] Visiting `/profile` while logged out redirects to `/login` and shows
      "Please sign in to continue."
- [ ] Logging in as `demo@spendly.com` / `demo123` lands on `/profile` with
      HTTP 200, and the page shows the shared navbar (name + Sign out) and the
      "Welcome back" flash
- [ ] The page shows "Demo User", `demo@spendly.com`, and a "Member since" date
- [ ] The demo user's summary shows 8 expenses, a total of `₹3,820.24`, and
      a this-month total of `₹3,820.24` (all seed expenses are in the current
      month)
- [ ] A newly registered user with no expenses sees 0 expenses, `₹0.00`
      totals, and "No expenses yet."
- [ ] One user's profile never includes another user's expenses (tested with
      two users)
- [ ] An expense dated last month counts in the total but not in "This month"
- [ ] If the session's `user_id` no longer exists in the DB, `/profile` clears
      the session and redirects to `/login` instead of erroring
- [ ] The page source never contains the password hash
- [ ] The layout stacks cleanly at ≤600px width
- [ ] `pytest` passes, including the new `tests/test_profile.py` and all
      existing tests
- [ ] The app still starts with `python app.py` on port 5001
