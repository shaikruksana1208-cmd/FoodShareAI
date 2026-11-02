# FoodShare AI Review 2: Three-Minute Demo

This script uses the working Flask app and its local SQLite database. Use test accounts and invented food details, not real personal information.

## 0:00-0:25 — Start and Introduce

**Action:** Start Waitress using the README instructions and open `http://127.0.0.1:5000`.

**Say:** “FoodShare AI connects our existing pastel website to a Flask API and SQLite. The matching component is a transparent rule-based agent, not a trained AI model.”

## 0:25-0:55 — Add a Donation

**Action:** Create or sign in to a donor account. Enter a future best-before time, a positive quantity and unit, pickup area, storage/condition information, and confirm food safety. Submit.

**Say:** “The browser sends this form to Flask using `fetch()`. The server validates the input and stores it in SQLite. The success message appears only after the API confirms saving.”

## 0:55-1:20 — Create a Request

**Action:** Sign out, create or sign in to a recipient account, submit a request with the same category and unit, and choose a quantity no greater than the donation.

**Say:** “The recipient creates a real open request. User roles and record ownership are checked on the server; hiding a button is not the security control.”

## 1:20-2:00 — Show AI Matching

**Action:** Choose the request in the matching section. Point out the score and individual reasons. If no record qualifies, use an incompatible category or request quantity larger than available and show the no-match message and expandable rejection explanation.

**Say:** “The agent first enforces hard constraints: category, units, stock, availability, safety, and expiry. Only valid pairs are scored. Urgency and named location affect ranking; location is not a distance estimate.”

## 2:00-2:25 — Accept and Update Stock

**Action:** Sign in as the donation owner, view matches for that owner's listings, and accept a valid match.

**Say:** “The API checks the match again in a transaction before reserving quantity. This prevents stale or competing requests from allocating the same stock twice.”

## 2:25-2:45 — Show the Admin Dashboard

**Action:** Sign in using the configured admin email and show Community Snapshot.

**Say:** “These totals are calculated from saved application records. Quantity is separated by unit. It is not a verified environmental-impact measurement.”

## 2:45-3:00 — Experiment and Close

**Action:** Briefly show `experiments/results/experiment_summary.csv` or its quality chart.

**Say:** “The algorithm comparison uses fixed synthetic CSV data, not our live database. The measured result is specific to that small dataset. We also run 30 automated tests covering matching and the API workflow.”

## If Something Goes Wrong

- If the server is not running: return to the terminal and restart with the README command.
- If no match appears: verify category and unit are identical, requested quantity is within available stock, expiry is in the future, and donation/request are still open.
- If dashboard access is denied: check that the admin email was set in `FOODSHARE_ADMIN_EMAILS` before that account registered.
- If a database error appears: stop the server, check the configured database path, and preserve the file before any reset. Do not delete the database during a demo.
