# Spec: Backend Route For Profile Page

## Overview
Step 4 gave `/profile` a real backend. It loads the logged-in user and three
summary numbers (count, total, this month). The Step 4 spec left an expense
list and any breakdown for later, so users still cannot see a single expense
anywhere in the app. This step extends the `GET /profile` route with two more
pieces of per-user data from new `database/db.py` helpers. The first is a list
of the user's most recent transactions, newest first. The second is a
spending breakdown by category, with a total and a share of overall spending
for each category. Both are rendered on the existing profile page. This is
the first view of individual expense rows, and the add/edit/delete steps
(7–9) will later link from it.

## Depends on
- **Step 1 — Database setup**: the `expenses` table, `CATEGORIES`, and the
  seeded demo user with 8 current-month expenses.
- **Step 3 — Login and logout**: `session["user_id"]`.
- **Step 4 — Profile**: `login_required`, `get_user_by_id`,
  `get_expense_summary`, `templates/profile.html`, `static/css/profile.css`.

## Routes
- `GET /profile` — modified, not new. In addition to `user` and `summary`, it
  now passes `recent_expenses` and `category_breakdown` to `profile.html` —
  logged-in
  - Every behaviour from Step 4 is unchanged: a logged-out user is redirected
    to login, and a session pointing at a deleted user is cleared and
    redirected.

No new routes.

## Database changes
No database changes. `expenses` already has `id`, `user_id`, `amount`,
`category`, `date` and `description`.

New helpers in `database/db.py` (no schema change):
- `get_recent_expenses(user_id, limit=10)` — returns up to `limit` rows with
  `id, amount, category, date, description` for this user. Rows are sorted by
  `date DESC, id DESC`, so ties on the same date are stable with the newest
  insert first. `LIMIT ?` is a parameter. A user with no expenses gets `[]`.
- `get_category_breakdown(user_id)` — returns a list of dicts
  `{"category", "total", "count", "percent"}`, one per category the user has
  spent in. It uses `SUM(amount)` and `COUNT(*)` with `GROUP BY category`,
  ordered by `total DESC, category ASC`. `percent` is that category's share of
  the user's overall total, rounded to 1 decimal and calculated in Python.
  Guard against dividing by zero. Categories with no spending are left out.
  A user with no expenses gets `[]`.

Every query filters on `user_id = ?`.

## Templates
- **Create:** none.
- **Modify:**
  - `templates/profile.html`, below the "Spending summary" stats:
    - **"Spending by category"** section. One row per breakdown entry shows
      the category name, the amount as `₹` with 2 decimals and thousands
      separators, and the percent (e.g. `41.9%`). Each row has a horizontal
      bar whose width is the percent. The width is set with
      `style="width: {{ item.percent }}%"`. That inline style is the only one
      allowed; all other styling goes in `profile.css`.
    - **"Recent transactions"** section, a table with columns Date, Description,
      Category and Amount. Dates are formatted as `20 Nov 2026`. Reuse the
      `member_since` filter or add a general `format_date` filter in `app.py`.
      A missing description is shown as `—`. Amounts use the same `₹` format,
      right-aligned.
    - When the user has no expenses, both sections are hidden. The existing
      "No expenses yet." line still shows.

## Files to change
- `app.py`:
  - import `get_recent_expenses` and `get_category_breakdown`
  - pass both results from `profile()` to the template
  - optionally add a `format_date` template filter
- `database/db.py` — add `get_recent_expenses()` and `get_category_breakdown()`.
- `templates/profile.html` — add the two sections.
- `static/css/profile.css` — styles for the category bars and the transactions
  table. Below 600px the table scrolls horizontally inside its own wrapper and
  the page itself never scrolls sideways.
- `tests/test_profile.py` — add tests for the new helpers and the rendered
  sections.
- `CLAUDE.md` — update the `GET /profile` row to mention Step 5.

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders, including `LIMIT ?`), never
  f-strings in SQL
- Passwords hashed with werkzeug: never select or render `password_hash`
- Use CSS variables; never hardcode hex values (e.g. `--accent` for bars,
  `--border-soft` for the bar track and table rules)
- All templates extend `base.html`
- No SQL in `app.py`. All DB access goes through `database/db.py` helpers.
- The route reads only `session["user_id"]`, never an id from the URL or form
- The route stays thin: fetch user, summary, recent expenses and breakdown,
  then render
- Use `url_for()` for every internal link
- No JavaScript is needed. Do not add charts libraries.
- Do not implement the add/edit/delete expense stubs, and do not add links to
  them yet
- Do not add filtering, pagination, or a separate expenses page

## Definition of done
- [ ] Logging in as `demo@spendly.com` / `demo123` shows `/profile` with
      "Spending by category" and "Recent transactions" sections
- [ ] The demo user's category breakdown lists 7 categories in this order:
      Shopping `₹1,599.99`, Bills `₹1,200.00`, Entertainment `₹499.00`,
      Health `₹250.00`, Food `₹166.25` (2 expenses), Other `₹75.00`,
      Transport `₹30.00`
- [ ] Percentages are correct to 1 decimal (Shopping `41.9%`, Bills
      `31.4%`) and the bar widths match them
- [ ] Recent transactions show all 8 demo expenses newest first. The first
      row is the day-25 "Other" expense with `—` as its description.
- [ ] With more than 10 expenses, only the 10 newest are shown
- [ ] A newly registered user with no expenses sees "No expenses yet." and
      neither new section
- [ ] One user's profile never shows another user's transactions or category
      totals (tested with two users)
- [ ] Logged-out access to `/profile` still redirects to `/login`
- [ ] At ≤600px width the page has no horizontal page scroll
- [ ] `pytest` passes, including new tests in `tests/test_profile.py` and all
      existing tests
- [ ] The app still starts with `python app.py` on port 5001
