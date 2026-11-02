# FoodShare AI Live Demonstration Script

> This script documents the earlier static-prototype stage. For the current tested Flask/SQLite Review 2 workflow, use [REVIEW_2_DEMO.md](REVIEW_2_DEMO.md).

**Duration:** About 3–5 minutes. The website portion demonstrates the current static prototype; the separate algorithm portion uses only synthetic CSV records.

## 0:00-0:30 — Open the Homepage

**Action:** Open `http://127.0.0.1:8000` if serving the folder with `python -m http.server 8000`, or open the provided project page. Show the header and hero.

**Say:** “This is FoodShare AI, a frontend prototype for a community food-sharing concept. The current version focuses on presenting the idea and responsive interface. It does not yet submit or store real donations.”

## 0:30-1:00 — Show the Responsive Menu

**Action:** Narrow the browser to a mobile width, open the menu, select a link, then reopen it and press Escape.

**Say:** “The navigation works on small screens. It can be opened with the menu button, closes after choosing a section, and also supports the Escape key.”

## 1:00-1:35 — Show Food Listings

**Action:** Select “Find food” or scroll to “On the community table.”

**Say:** “These three cards show examples of how food listings could look. They are hardcoded sample content. There is no search, request action, or database behind them, and the page notes that no food is currently available to request.”

## 1:35-2:00 — Explain Donation and Request Status

**Action:** Select “Donate food” and point out the call-to-action section.

**Say:** “The donate section is an informational placeholder. There is no donation form in this version, so I cannot submit or save a donation. Food requests are also not implemented.”

## 2:00-2:25 — Matching and Login Placeholders

**Action:** Select the matching feature card, then the login link if time allows. Point out the toast notice.

**Say:** “The website's matching and login links are placeholders. Separately, the project has a Python rule-based matching and allocation experiment, but it is not connected to the page or a live database, and there is no secure authentication.”

## 2:25-3:15 — Show the Standalone AI Experiment

**Action:** From the project root in a prepared virtual environment, run `python experiments/run_experiment.py`, then open `experiments/results/experiment_summary.csv` and `experiments/results/allocation_quality.png`.

**Say:** “This is an offline experiment on clearly labeled synthetic records. It compares a greedy baseline with exhaustive search. In the recorded run, the search method assigned six valid requests and the greedy method assigned five, with zero constraint violations for both. This result applies only to this small dataset; it is not live website activity or proof that search is always better.”

## 2:25-2:50 — Reuse and Disposal Content

**Action:** Scroll to the reuse tips and footer navigation labeled “Disposal guide.”

**Say:** “This section currently provides three general food-management tips. A structured searchable reuse collection and disposal guide have not been implemented. Local composting and recycling rules would need to be added carefully in a future version.”

## 2:50-3:15 — Impact Panel and Close

**Action:** Show the trust strip and impact panel.

**Say:** “The displayed quantities and connections are illustrative demo figures. They are not based on donations, database calculations, or measured environmental outcomes. The next technical step is adding and testing a backend before presenting live activity.”

## Important Demonstration Notes

- Do not claim to add a donation or submit a food request; no forms exist.
- Do not describe the sample listings as available real food.
- Do not describe the impact values as measured results.
- Do not call the matching or login links working website features. Explain that the algorithm is currently standalone.
- If an evaluator asks for the backend, explain that Flask and SQLite are not in the inspected project workspace yet.
- For an actual screenshot slide, capture the current site directly; this project does not include saved screenshots.