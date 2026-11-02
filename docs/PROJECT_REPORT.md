# FoodShare AI: Project Report

> **Implementation status:** The current project includes a pastel HTML/CSS/JavaScript website, a Flask API, SQLite storage, account roles, donation/request forms, matching recommendations, and an admin summary. The matching agent is rule-based, not machine learning. The separate greedy-versus-search experiment uses synthetic CSV data only.

## 1. Project Title

**FoodShare AI: A Community-Oriented Food Sharing Website Prototype**

## 2. Abstract

FoodShare AI is a community food-sharing demonstration. The existing pastel frontend communicates with a Flask API using JSON and `fetch()`. Flask validates accounts, donation listings, and requests; SQLite stores application records; and a Python agent rejects invalid donation/request pairs before ranking valid ones. A separate experiment compares greedy and exhaustive allocation on clearly labeled synthetic data. The results are not real food activity or measured environmental impact.

## 3. Introduction

Food that is still safe to eat may be discarded when its owner cannot use it in time, while another person may need food. FoodShare AI explores a digital interface for making local sharing easier to understand. The current deliverable is a visual prototype that communicates that idea; it is not yet an operational exchange platform.

## 4. Problem Statement

Communities need accessible ways to share safe surplus food and let recipients find suitable listings. A software system must validate submissions, respect availability and food-safety declarations, and avoid allocating the same quantity multiple times.

## 5. Existing System and Its Limitations

The original frontend used static sample listings and impact figures. The current connected listings and admin summary use SQLite, while the old homepage trust-strip and impact panel remain illustrative. The implementation is a college demo: safety is self-declared, location uses text areas rather than distance, and further security review is needed before public deployment. Fonts and photos are external assets.

## 6. Proposed System

The current implementation uses Flask endpoints to validate and persist donations and requests, returns explainable matches from the Python agent, and reserves stock in a SQLite transaction when an authorized donor/admin accepts a match. The separate admin summary is calculated from saved records.

## 7. Project Objectives

- Present a clear community food-sharing concept.
- Provide a responsive, approachable website interface.
- Introduce example listing, reuse, disposal, and impact content.
- Identify a practical path toward a data-backed application.

The responsive interface, API-backed donation/request flow, matching, and database-derived admin counts are implemented and covered by tests. Broader real-world evaluation and deployment hardening remain future work.

## 8. Main Features

### Implemented in the current source

- A single-page homepage with section navigation.
- Food-sharing introduction and calls to action.
- API-backed available food listings, search, and category filters.
- Three short reuse and food-management tips.
- Fixed, explicitly labeled sample impact figures.
- Responsive mobile navigation with click-to-open, link-to-close, and Escape-to-close behavior.
- Registration/login with hashed passwords and session/CSRF checks.
- Donation creation and request creation with server-side validation.
- Explainable live matching from current SQLite records, including constraint rejection reasons.
- Owner/admin match acceptance that reserves quantity transactionally.
- Admin-only dashboard counts from saved application activity.
- A standalone Python matching agent and reproducible synthetic allocation experiment.
- Responsive CSS layouts, reduced-motion support, keyboard focus outlines, and a skip link.

### Not implemented in the current source

- Machine-learning recommendations; matching is rule-based.
- Structured disposal or reuse databases.
- Persisted notification inbox.
- Production-grade authentication/deployment assurances.

## 9. Technologies Used

- **HTML:** page structure, text content, links, and accessible labels.
- **CSS:** pastel theme, layout, responsive breakpoints, hover states, and animation.
- **JavaScript:** mobile menu behavior, Escape-key handling, API-backed forms, listings, matching, status actions, and dashboard rendering.
- **External assets:** Google Fonts (DM Sans and Fraunces) and Unsplash background photos.

Python and Flask implement the application service and matching logic. SQLite stores users, donations, requests, and accepted allocations. Matplotlib and pytest support the separate experiment and tests.

## 10. System Requirements

### Local application

- A modern web browser with JavaScript enabled.
- Internet access for the externally hosted fonts and photos; the page structure and CSS are local.
- Python 3.11 or newer; install dependencies using `python -m pip install -r requirements.txt`.
- From an activated virtual environment, set `FOODSHARE_SECRET_KEY`, `FOODSHARE_DATABASE`, and optionally `FOODSHARE_ADMIN_EMAILS`.
- Start with `waitress-serve --listen=127.0.0.1:5000 app:app`, then open `http://127.0.0.1:5000`.

The SQLite schema is initialized automatically when Flask starts. See the root README for exact PowerShell commands.

## 11. System Architecture

The browser loads `index.html`, `style.css`, and `script.js` from Flask. JavaScript sends JSON to Flask routes with `fetch()`. Flask validates and authorizes each operation, reads/writes SQLite with parameterized queries, and calls the matching agent for recommendations. The separate experiment runner reads synthetic CSV inputs and never inserts those records into the application database. See [ARCHITECTURE.md](ARCHITECTURE.md).

## 12. Database Design

SQLite tables are initialized in `app.py`: `users` (accounts/roles), `donations` (food and remaining quantity), `food_requests` (recipient demand), and `allocations` (accepted request-to-donation reservations). Foreign keys link donations to donors, requests to requesters, and allocations to donations/requests. Unique constraints prevent a request from being allocated twice. The local database defaults to `instance/foodshare.sqlite3` and must not be committed.

## 13. Module Descriptions

- **Homepage and navigation (`index.html`):** contains the header, hero, feature links, steps, sample listings, tips, impact panel, call to action, and footer.
- **Frontend API integration (`script.js`):** handles registration/login, forms, listings, recommendations, status actions, dashboard totals, and mobile navigation.
- **Visual system (`style.css`):** defines cream, sage, peach, and lavender colors; typography; section layouts; breakpoints; animation; and focus styling.
- **Donation/request module:** validated forms call Flask and persist rows in SQLite.
- **Matching module:** `matching_agent.py` enforces hard constraints and explains ranked results.
- **Allocation module:** greedy and exhaustive methods are compared on synthetic CSV data; acceptance rechecks one live match transactionally.
- **Reuse/disposal content:** the page still provides brief static educational tips, not a searchable guide.
- **Admin module:** role-protected counts use actual stored application records; original homepage sample figures remain illustrative.

## 14. Implementation Details

The HTML uses in-page links. CSS retains the cream/sage/peach/lavender design and responsive breakpoints. JavaScript sends API requests and creates result elements using safe text nodes. Flask uses server-side validation, hashed passwords, sessions, CSRF checks, role checks, parameterized SQL, and a transaction for match acceptance. The standalone matching agent provides the hard constraints, weighted score, greedy baseline, and exhaustive search.

## 15. Testing and Results

The browser was tested against the running local Flask server. The tested journey created a donor, saved a donation, created a recipient request, returned an explained match, accepted it as the donor, and showed the stock reduction and admin totals from SQLite. The page was checked at 390 px with no horizontal overflow. `python -m pytest -q` passed 35 tests. The synthetic experiment ran 25 times per algorithm: greedy fulfilled 5 requests/16 units (41.0%); exhaustive search fulfilled 6/24 units (61.5%). Both had zero invalid allocations and constraint violations. These experiment inputs are synthetic; the browser review used a separate local test database. These checks do not constitute a professional security audit.

## 16. Advantages

- The concept and main content are easy to understand.
- The interface adapts to smaller screens.
- The pastel design and typography are consistent across sections.
- The menu supports keyboard interaction and reduced-motion preferences.
- The local demo can be run with a small Python stack and a file-based database.

## 17. Limitations

- This has not had a professional security review or real-world trial.
- Food safety is a user declaration, not an automated inspection.
- Some original homepage statistics are illustrative; only the admin snapshot is database-backed.
- Detailed searchable disposal/reuse guidance and persisted notifications are not implemented.
- Externally hosted fonts and photos may be unavailable offline or change over time.
- The rule-based matching experiment is standalone and not connected to live donations, requests, or the website.

## 18. Future Enhancements

- Add professional security review, rate limits, email verification, and password-reset workflows.
- Consider managed database support and migration/backups before cloud deployment.
- Improve category/unit compatibility and collect consented outcomes before tuning weights.
- Expand searchable food safety, reuse, and disposal guidance.
- Add persistent notifications and a richer admin activity view.
- Expand reuse and disposal guidance with food-safety warnings and local-rule caveats.
- Add automated API tests and deployment configuration after the backend exists.

## 19. Conclusion

FoodShare AI combines its existing pastel interface with a tested Flask/SQLite demo workflow and a separate explainable matching experiment. Donation/request creation, matching reasons, owner acceptance, inventory updates, and admin counts were exercised locally. The experiment is explicitly synthetic, and the system still has safety, scalability, and security limitations that should be stated during evaluation.

## 20. References

- MDN Web Docs, HTML: https://developer.mozilla.org/docs/Web/HTML
- MDN Web Docs, CSS: https://developer.mozilla.org/docs/Web/CSS
- MDN Web Docs, JavaScript: https://developer.mozilla.org/docs/Web/JavaScript
- Python documentation: https://docs.python.org/3/
- Flask documentation: https://flask.palletsprojects.com/
- SQLite documentation: https://www.sqlite.org/docs.html

The matching technique and measured synthetic comparison are documented in [../AI_ALGORITHM.md](../AI_ALGORITHM.md) and [../EXPERIMENTS.md](../EXPERIMENTS.md).