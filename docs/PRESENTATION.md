# FoodShare AI Presentation Outline

> Keep team names and screenshots as placeholders until the actual details and captures are supplied. Distinguish live local application records from the separate synthetic experiment dataset.

## Slide 1: Title and Team

- FoodShare AI: A community food-sharing website prototype
- Presented by: `[Add actual team member names]`
- Department / class: `[Add actual details]`

**Speaker notes:** Introduce the idea and team. Explain that the submitted version is a frontend prototype. Do not add names or affiliations that have not been confirmed.

## Slide 2: Problem Statement

- Safe surplus food can go unused.
- People may not know where to find nearby surplus food.
- A clear interface can communicate a possible sharing workflow.

**Speaker notes:** Describe the community problem in general terms. Do not claim that this prototype has already rescued food or connected real donors and recipients.

## Slide 3: Proposed Solution

- An existing pastel website connected to a Flask API for local demo records.
- SQLite storage for donations, requests, and accepted allocations.
- The separate experiment uses synthetic CSV records only.

**Speaker notes:** Explain that the browser forms call the local Flask API and save to SQLite. Use only test data during the classroom demonstration.

## Slide 4: Objectives

- Present the food-sharing idea in a clear way.
- Build a responsive web interface.
- Show example food cards and educational content.
- Identify the next steps toward a data-backed application.

**Speaker notes:** The local implementation includes API-backed donation/request flow, live matching, and database-derived administrator counts. Production deployment hardening and a broader field evaluation remain future work.

## Slide 5: Main Features

- Responsive single-page homepage and mobile navigation.
- API-backed food listings with search and category filter.
- Three static food-management tips.
- Explainable rule-based matching and transactional quantity reservation.
- Admin totals calculated from saved application data.
- Standalone greedy/search experiment using synthetic data.
- Sample impact panel, labeled as illustrative.

**Speaker notes:** Show a saved listing and match from the local review database. The original homepage impact panel remains illustrative; the admin snapshot uses application records.

## Slide 6: Technology Stack

- HTML for page structure.
- CSS for styling and responsive behavior.
- JavaScript for menu interaction and API requests.
- Python and Flask for API, validation, and matching.
- SQLite for local application storage.
- Waitress for a Windows-compatible WSGI server.
- External Google Fonts and Unsplash images.

**Speaker notes:** The app uses Flask and SQLite locally. The algorithm comparison uses a separate synthetic dataset and is not part of real donation activity.

## Slide 7: System Architecture

- User opens the website in a browser.
- Browser loads HTML, CSS, and JavaScript files.
- JavaScript uses `fetch()` to call Flask routes.
- Flask validates and reads/writes SQLite records.
- The Python matching agent checks constraints and returns explainable rankings.
- The experiment runner separately reads synthetic CSV data.

**Speaker notes:** Use the diagram in [ARCHITECTURE.md](ARCHITECTURE.md). Explain the difference between live demo records and synthetic experiment inputs.

## Slide 8: Website Screenshots and Demonstration

- Insert a screenshot of the homepage: `[Add actual screenshot]`.
- Insert a mobile navigation screenshot: `[Add actual screenshot]`.
- Create a donor listing and recipient request.
- Show a valid match and its score/reasons, then accept it as the donor.
- Show the database-backed admin totals.

**Speaker notes:** Capture the current site directly. Use test accounts and do not use real personal contact details.

## Slide 9: Testing and Results

- Opened the page in a browser.
- Checked responsive layout and mobile menu interactions.
- Checked JavaScript syntax.
- 35 Python unit and API tests passed in the latest full run.
- Browser flow tested donation, request, explained matching, acceptance, stock change, and admin summary.
- Synthetic experiment ran 25 repetitions per method.

**Speaker notes:** On this fixed synthetic dataset, greedy observed 5 matches (41.0% demand fulfillment) and search observed 6 matches (61.5%); both had zero constraint violations. Do not generalize beyond this dataset.

## Slide 10: Conclusion and Future Scope

- Current result: a locally tested Flask/SQLite donation, request, matching, and admin-summary workflow.
- Current limitations: demo-level security, self-declared food safety, and synthetic algorithm experiment.
- Next: security review, richer category/unit support, and persistent deployment storage.
- Sample homepage impact figures remain illustrative.

**Speaker notes:** Summarize tested functionality and limitations. The synthetic comparison is not measured community impact; the original homepage figures are illustrative.