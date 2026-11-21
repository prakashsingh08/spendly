# Spec: Date Filter For Profile Page

## Overview
After Step 5, the profile page shows a spending summary, the 10 most recent
transactions and a breakdown by category. All three always cover the user's
whole history. This step adds a date-range filter to `/profile`. The user
picks a start date and/or an end date, or uses a preset ("This month", "Last
30 days", "All time"). The expense count, total spent, recent transactions
and category breakdown are then recalculated for that range only. The filter
is plain query-string state (`/profile?start=YYYY-MM-DD&end=YYYY-MM-DD`)
sent by a GET form. Filtered views can be bookmarked, and no JavaScript is
needed. This is the first time the profile can answer "what did I spend in
this period?" before the add/edit/delete steps (7–9) add more data.

## Depends on
- **Step 1 — Database setup**: the `expenses` table (`date` stored as ISO
  `YYYY-MM-DD` text) and the seeded demo user with 8 current-month expenses
  on days 1, 3, 5, 8, 12, 15, 20, 25.
- **Step 3 — Login and logout**: `session["user_id"]`.
- **Step 4 — Profile**: `login_required`, `get_user_by_id`,
  `get_expense_summary`, `templates/profile.html`, `static/css/profile.css`.
- **Step 5 — Profile backend**: `get_recent_expenses`,
  `get_category_breakdown`, the `format_date` filter, and the context helpers
  `profile_summary_context`, `profile_transactions_context` and
  `profile_categories_context`.

## Routes
- `GET /profile` — modified, not new. It now reads two optional query
  parameters, `start` and `end` (ISO `YYYY-MM-DD`, both inclusive). It passes
  the parsed range to the summary, transactions and category helpers and
  renders `profile.html` with a `date_filter` context — logged-in
  - The parameters are parsed with `date.fromisoformat()` in a small helper in
    `app.py`, e.g. `parse_date_filter(args)`. The helper returns
    `{"start", "end", "error"}`.
    - Missing or empty parameter → that bound is `None` (open-ended).
    - Malformed value (e.g. `start=abc`, `end=2026-13-40`) → the filter is
      ignored (both bounds `None`). Show the inline error "Please enter valid
      dates." Respond with status 200, not a 500.
    - `start` later than `end` → the filter is ignored. Show the inline error
      "Start date must be on or before end date."
  - Every Step 4/5 behaviour is unchanged when no parameters are given: a
    logged-out user is redirected to login, and a session pointing at a
    deleted user is cleared and redirected.

No new routes.

## Database changes
No database changes. `expenses.date` is already ISO `YYYY-MM-DD` text, so
string comparison with `>=` and `<=` is correct.

Helper changes in `database/db.py` (no schema change). Each one takes new
optional keyword arguments `start_date=None, end_date=None` (ISO strings or
`None`). With both left as `None`, the output is exactly what it is today.
- `get_expense_summary(user_id, today=None, start_date=None, end_date=None)`
  - `count` and `total` cover only expenses within the range.
  - `month_total` keeps its meaning: it always covers the calendar month that
    contains `today`, whatever the filter.
- `get_recent_expenses(user_id, limit=10, start_date=None, end_date=None)`
  returns the 10 newest expenses within the range, with the same ordering as
  before (`date DESC, id DESC`).
- `get_category_breakdown(user_id, start_date=None, end_date=None)` returns
  totals, counts and percents over the expenses within the range only.
  `percent` is the share of the *filtered* total.

Build the range condition once, in a private helper such as
`_date_range_clause(start_date, end_date)`. It returns a SQL fragment made
only of fixed strings (`" AND date >= ?"`, `" AND date <= ?"`) and a list of
parameters. The date values are always bound with `?` and never inserted into
the SQL text. Every query still filters on `user_id = ?`.

## Templates
- **Create:** none.
- **Modify:**
  - `templates/profile.html`. Add a **"Filter by date"** bar above the
    "Spending summary" heading:
    - A `<form method="get" action="{{ url_for('profile') }}">` with two
      `<input type="date">` fields named `start` and `end`. Both have visible
      `<label>`s and are pre-filled with the active range. The form has an
      "Apply" submit button.
    - Preset links built with `url_for('profile', start=..., end=...)`:
      - **This month**: the 1st of the current month to today.
      - **Last 30 days**: today minus 29 days to today.
      - **All time**: `url_for('profile')` with no parameters. This link
        doubles as "Clear filter".
    - Compute the preset dates in `app.py`, not in Jinja. Every preset that
      matches the active range is marked with `aria-current="true"` and an
      active style. On the 30th, "This month" and "Last 30 days" cover the
      same range, so both are marked.
    - When a filter is active, show a line like "Showing 01 Nov 2026 – 10 Nov
      2026" using `format_date`. An open bound reads "Since 01 Nov 2026" or
      "Up to 10 Nov 2026".
    - A validation error is shown inline in the filter bar (role="alert"),
      using the existing error message style.
    - Empty state: if the user has expenses but none in the active range,
      show "No expenses in this period." in place of "No expenses yet.". The
      category and transaction sections stay hidden, as they already do when
      their lists are empty.
    - Update the "Expenses" and "Total spent" tile labels so it is clear they
      follow the filter (e.g. "Total spent" stays, and a sub-label shows the
      range or "All time"). "This month" is unchanged.

## Files to change
- `app.py`:
  - add `parse_date_filter()` and a preset-range helper (pure Python, no SQL)
  - make the three `profile_*_context` helpers accept the range and pass it
    through
  - pass `date_filter` (start, end, error, presets, active preset) to the
    template
  - the `profile()` route stays thin: parse filter → fetch → render
- `database/db.py` — add `_date_range_clause()`, and add the
  `start_date`/`end_date` kwargs to `get_expense_summary`,
  `get_recent_expenses` and `get_category_breakdown`.
- `templates/profile.html` — the filter bar, range label, error and empty
  state.
- `static/css/profile.css` — filter bar layout. The inputs, button and preset
  chips wrap onto their own lines below 600px. Add the active-preset style.
- `CLAUDE.md` — update the `GET /profile` row to mention the date filter
  (Step 6).

## Files to create
- `tests/test_profile_date_filter.py` — tests for `_date_range_clause` via
  the three helpers, `parse_date_filter`, the rendered filter bar, presets,
  invalid input and per-user isolation under a filter.

## New dependencies
No new dependencies. Use the standard-library `datetime` for parsing and
presets.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders). Never insert date strings
  into SQL with f-strings, `%` or `.format()`. Only fixed SQL fragments may
  be joined.
- Passwords hashed with werkzeug: never select or render `password_hash`
- Use CSS variables. Never hardcode hex values (reuse `--accent`,
  `--border-soft` and the existing error colour variables).
- All templates extend `base.html`
- No SQL in `app.py`. All DB access goes through `database/db.py` helpers.
- The route reads only `session["user_id"]` for identity. Query parameters
  `start` and `end` are only date bounds, never a user id.
- Validate dates with `date.fromisoformat()`. Bad input must never raise a
  500 or reach SQL as an unvalidated string.
- Keep the existing helper signatures backward compatible (new kwargs default
  to `None`), so all Step 4/5 tests pass unchanged.
- Use `url_for()` for the form action and every preset link
- Vanilla HTML only. A GET form needs no JavaScript, so add none and no date
  picker libraries.
- Do not implement the add/edit/delete expense stubs. Do not add pagination,
  category filtering or a separate expenses page.

## Definition of done
- [ ] Logged in as `demo@spendly.com` / `demo123`, `/profile` with no
      parameters looks and totals exactly as in Step 5 (8 expenses, all 7
      categories). The new filter bar is shown with "All time" active.
- [ ] Filtering from day 1 to day 10 of the current month shows 4 expenses
      and Total spent `₹1,525.50`. The transactions list days 8, 5, 3 and 1,
      and the categories are Bills, Health, Food and Transport only.
- [ ] Category percents under that filter are calculated against `₹1,525.50`
      (Bills `78.7%`)
- [ ] Only `start` set (day 20) shows the day-20 and day-25 expenses. Only
      `end` set (day 3) shows the day-1 and day-3 expenses. Both bounds are
      inclusive.
- [ ] A range with no expenses (e.g. a month in the past) shows "No
      expenses in this period.", zero count and total, and neither list
      section
- [ ] "This month" tile still shows the full current-month total under any
      filter
- [ ] `?start=abc` and `?start=2026-11-20&end=2026-11-01` each return 200
      with the right inline error and unfiltered data
- [ ] The date inputs keep the submitted values after Apply. The matching
      preset is highlighted, and "All time" clears the filter.
- [ ] A filtered view never shows another user's expenses (tested with two
      users)
- [ ] Logged-out access to `/profile?start=...` still redirects to `/login`
- [ ] At ≤600px width the filter bar wraps and the page has no horizontal
      scroll
- [ ] `pytest` passes, including `tests/test_profile_date_filter.py` and
      all existing tests
- [ ] The app still starts with `python app.py` on port 5001
