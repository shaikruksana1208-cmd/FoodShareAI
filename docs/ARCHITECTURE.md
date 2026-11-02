# FoodShare AI Architecture

This diagram shows the implemented local demonstration. The matching agent reads current application records through Flask for live recommendations. The experiment runner separately reads synthetic CSV inputs; experiment data is not imported into the live database.

```mermaid
flowchart LR
    Donor[Donor]
    Recipient[Recipient]
    Admin[Administrator]
    Browser[Browser: existing HTML/CSS/JavaScript]
    API[Flask routes, validation, sessions]
    Agent[Rule-based matching and allocation agent]
    DB[(SQLite application database)]
    CSV[Synthetic experiment CSVs]
    Runner[Greedy/search experiment runner]
    Charts[Measured CSV outputs and Matplotlib charts]

    Donor --> Browser
    Recipient --> Browser
    Admin --> Browser
    Browser -->|fetch JSON| API
    API --> DB
    API --> Agent
    Agent --> API
    API -->|JSON response| Browser
    CSV --> Runner
    Runner --> Agent
    Runner --> Charts
```

## Live Workflow

```mermaid
flowchart LR
    D[Donor creates safe donation] --> F[Flask validates and stores]
    F --> S[(SQLite)]
    R[Recipient creates request] --> F
    S --> A[Matching agent checks hard constraints]
    A -->|ineligible: explain rejection| X[No recommendation]
    A -->|eligible: score and rank| M[Explainable recommendations]
    M --> O[Donation owner or admin accepts]
    O --> T[Transaction rechecks and reserves stock]
    T --> S
    S --> Dashboard[Admin dashboard reads saved totals]
```

## Key Boundaries

- `index.html`, `style.css`, and `script.js` provide the pastel website and call the API with `fetch()`.
- `app.py` serves the frontend and provides authentication, donation, request, matching, acceptance, and admin-summary routes.
- `matching_agent.py` applies hard constraints, creates reasoned scores, and implements greedy/exhaustive allocation methods.
- `instance/foodshare.sqlite3` is generated at startup and stores accounts, donations, requests, and allocations. The database directory is ignored by Git.
- `experiments/data/` contains fixed synthetic records. `experiments/run_experiment.py` writes metrics and charts without using the app database.

## Safety Rules

- Eligibility is checked by Python on current records, not by the browser.
- Match acceptance verifies ownership and rechecks constraints in a SQLite write transaction.
- Invalid pairs are excluded from recommendations; their constraints are returned separately for explanation.
- Dashboard values are calculated from saved application records. Allocated quantities are grouped by unit and are not verified impact estimates.