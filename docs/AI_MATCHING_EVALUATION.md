# FoodShare AI Matching Agent: Experimental Evaluation

## Scope and Status

The matching agent in [../matching_agent.py](../matching_agent.py) is a rule-based Python program used by the Flask matching API and by a standalone experiment runner. It is not machine learning: it does not train a model or learn weights from examples. The browser's live recommendations come from the Flask API and current SQLite records; the experiment itself uses separate synthetic CSVs.

All records under `../experiments/data/` are invented for repeatable testing and are marked `SYNTHETIC`. They are not real donors, recipients, or food activity.

## Problem and Motivation

Given surplus-food donations and recipient requests, identify safe, feasible pairs and allocate limited donation quantities without assigning more food than exists. The program should explain its decisions so a student or user can understand why a pair was accepted or rejected.

## AI Technique and Suitability

The project uses two classical AI ideas at a small scale:

- **Heuristic evaluation:** a transparent weighted score ranks pairs that first pass all hard feasibility checks.
- **State-space search:** exhaustive depth-first search explores feasible allocations for small datasets and selects the best complete assignment under a defined objective.

This is suitable for a capstone because inputs, actions, constraints, and objectives are visible. It is testable without training data or paid services. The search is intentionally limited to a small synthetic problem; its exponential growth makes it unsuitable for large live datasets without a more scalable optimizer.

## Input and Output

Each donation record uses:

| Field | Meaning |
| --- | --- |
| `id` | Unique donation identifier |
| `category` | Food category; currently must exactly match the request category after trimming and case normalization |
| `quantity` | Positive numeric quantity |
| `unit` | Unit such as `kg`, `loaf`, `liter`, or `portion`; must exactly match the request unit |
| `status` | Must be `available` |
| `food_safe` | Must be boolean true or SQLite-style integer `1` |
| `expires_at` | ISO-8601 timestamp with timezone, later than evaluation time |
| `location` | Optional named area; no coordinates or exact distance are inferred |

Each request uses `id`, `category`, positive `quantity`, `unit`, `status` (`open` or `pending`), `urgency` (`low`, `medium`, or `high`), and optional named `location`.

The pair evaluator returns donation and request IDs, whether the pair is compatible, a 0-100 compatibility score for accepted pairs, human-readable reasons, rejected constraints, and a recommended next action. Rejected pairs receive no score. The recommendation list can include rejected candidates after valid ones so the caller can explain why no match was possible; allocation methods select only eligible pairs.

## Hard Constraints and Score

Hard constraints are checked before scoring and cannot be overcome by a high score:

1. Both IDs must be present.
2. Categories must be present and equal after normalization.
3. Donation and request quantities must be positive finite numbers; units must be present and equal.
4. Donation status must be `available` and request status must be `open` or `pending`.
5. Food must be explicitly marked safe.
6. Expiry must be a valid timezone-aware ISO-8601 timestamp later than evaluation time.
7. Donation quantity must satisfy the entire request. This implementation does not partially fill a request.
8. Urgency must be one of the documented levels.

For eligible pairs, the compatibility score is:

```text
score = category_points + quantity_points + urgency_points + location_points

category_points = 40
quantity_points = 25 * requested_quantity / currently_remaining_donation_quantity
urgency_points = low: 5, medium: 12, high: 20
location_points = 15 for same known named area; 5 for different known areas; 0 when either is missing
```

Location is a soft ranking hint, not a hard geographic constraint. A different named area receives fewer points but may still be feasible. Missing location contributes zero and is explained. Exact distance is never calculated. The score is a rule-based ranking value, not a probability of successful pickup.

## Allocation Methods

### Method A: Greedy Baseline

- **Input:** donation records, open requests, and a fixed evaluation time.
- **State:** remaining quantity per donation, pending requests, and assignments already made.
- **Action:** select the currently feasible pair with the highest score; reserve the full requested amount and remove that request from the pending set.
- **Goal:** produce a feasible allocation; greedy does not guarantee a globally optimal allocation.
- **Objective for comparison:** maximize the number of fully satisfied requests, then use total score as a descriptive tie-break metric. Greedy itself makes local highest-score choices.
- **Constraints:** hard pair rules above; each request at most once; donor remaining quantity cannot become negative.
- **Termination:** no eligible pairs remain or no requests remain.
- **Complexity:** for `R` requests and `D` donations, the implementation rescans all pending pairs once per assignment round, giving an upper bound of `O(R^2 D * C)`, where `C` is the cost of validating/scoring a pair. Pair checks have a fixed number of fields, excluding timestamp parsing.

### Method B: Exhaustive Depth-First Allocation Search

- **Initial state:** request index zero, each donation's full available quantity, and an empty assignment list.
- **State representation:** current request position, remaining quantity vector for all donations, selected assignments, and cumulative score.
- **Actions:** assign the current request to any currently feasible donation, or leave it unmatched.
- **Goal state:** every request has been considered and all chosen assignments satisfy constraints.
- **Objective:** lexicographically maximize (1) number of fully satisfied requests and then (2) total compatibility score.
- **Constraints:** same hard pair rules; each request gets at most one donation; assignments cannot exceed initial donation quantity.
- **Termination:** recursion reaches the end of the request list on every explored action path.
- **Complexity:** each request has at most `D + 1` choices (one donor or unmatched), so the search explores `O((D + 1)^R)` leaves. Including donor checks and copying quantity vectors, a conservative time bound for this implementation is `O(D * (D + 1)^R * C)`. Recursion and per-level state use `O(RD)` memory, excluding returned results.

The search is an optimization/search method, not a learned AI model. It can find the best allocation for the specified objective only within its finite input and assumptions.

## Experiment Method

- `../experiments/data/synthetic_donations.csv`: 9 synthetic donations covering multiple categories, units, locations, safety and availability states, and a missing category.
- `../experiments/data/synthetic_requests.csv`: 12 synthetic requests covering quantity differences, urgency, location, competition, incompatible categories, invalid urgency, and a missing unit.
- `../tests/test_matching_agent.py`: unit and allocation tests with a fixed evaluation timestamp.
- `../experiments/run_experiment.py`: runs both methods 25 times on the same fixed records and timestamp, measures wall-clock time with `perf_counter`, writes CSVs, and creates charts.

The records are fixed rather than randomly generated, so reruns use identical inputs. Timing can vary by machine and system load. The exported records carry the `SYNTHETIC_ONLY` label.

## Metrics

- **Valid matches:** count of complete request assignments produced by an allocator.
- **Quantity fulfilled:** sum of quantities assigned in complete requests.
- **Quantity fulfillment rate:** quantity fulfilled divided by positive numeric quantities for well-formed open requests. Here, well-formed means non-empty ID and category, positive numeric quantity, non-empty unit, open/pending status, and documented urgency. Malformed requests are rejected and excluded from this denominator.
- **Rejected candidate pairs:** donation/request pairs rejected by hard validation, independent of the allocator's final assignments.
- **Invalid matches:** selected pairs that fail the pair evaluator.
- **Double allocations:** request IDs assigned more than once plus any donation whose assigned total exceeds its starting quantity.
- **Constraint violations:** invalid selected pairs plus donor over-allocation events. This should be zero; a non-zero result indicates an implementation error.
- **Execution time:** elapsed seconds for one allocator call, averaged across 25 runs. The summary CSV also includes population standard deviation.

## Results: Observed Synthetic Run

The following values were read from `../experiments/results/experiment_summary.csv`, generated in this environment on the fixed dataset. They are not real-world impact or general performance guarantees.

| Method | Mean valid matches | Mean quantity fulfilled | Mean fulfillment rate | Invalid | Double allocations | Constraint violations | Mean time (seconds) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Greedy | 5 | 16 | 0.410256 (41.0%) | 0 | 0 | 0 | 0.005056308 |
| Exhaustive search | 6 | 24 | 0.615385 (61.5%) | 0 | 0 | 0 | 0.050691204 |

The dataset contains 9 donations, 12 requests, and 108 possible pairs. The evaluator rejected 94 pairs and found 14 eligible pairs before allocation. Both algorithms had zero invalid assignments, double allocations, and constraint violations in these runs. On this particular dataset, exhaustive search satisfied one additional request and fulfilled 8 additional quantity units, but took longer. This does not establish that search is always better; it reflects one small, hand-authored synthetic dataset and the selected objective.

## Generated Artifacts

- `../experiments/results/experiment_runs.csv`: 50 measured rows (25 per method).
- `../experiments/results/experiment_summary.csv`: actual aggregate metrics.
- `../experiments/results/allocation_details.csv`: final run assignments and explanations.
- `../experiments/results/allocation_quality.png`: valid-request and fulfillment comparison.
- `../experiments/results/allocation_timing.png`: runtime comparison with timing variation.

Charts are generated by Matplotlib from the same in-memory summary rows written to CSV. Do not edit results manually; rerun the script after changing the code or input dataset.

## Reproduce the Work

From the project root in Windows PowerShell, create an isolated environment and install the experiment dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-ai-experiments.txt
python -m pytest -q
python experiments/run_experiment.py
```

The final command recreates the CSV and PNG files under `experiments/results/`.

## Architecture and Integration Status

The Flask `/api/matches` endpoint reads real current database records, calls the matching agent, and returns valid recommendations with reasons plus separate rejection constraints. Match acceptance rechecks eligibility and writes an allocation transactionally. The synthetic experiment runner remains separate and must not seed the application database.

## Limitations

- Exact category equality only; no taxonomy or synonym handling.
- Exact unit string matching; no unit conversion.
- No partial request fulfillment.
- No coordinates, geocoding, travel time, or exact distance.
- Food safety depends on a trusted upstream value; the code cannot inspect food.
- Expiry is enforced only when a valid timezone-aware timestamp is provided.
- Fixed weights are manually selected, not learned or calibrated from outcomes.
- Exhaustive search is exponential and intended only for small datasets.
- Synthetic results may not represent real demand patterns.
- Flask, SQLite, and frontend integration cannot be performed against the files currently available.

## Future Scope

- Connect through a verified Flask API and existing schema after backend source is provided.
- Add a category compatibility table and carefully validated unit conversions.
- Consider partial fulfillment only with explicit recipient consent and transaction-safe inventory updates.
- Compare against more baselines and larger, varied synthetic datasets.
- Use real, consented, anonymized outcome data before tuning weights.
- Consider integer linear programming or a scalable matching algorithm for larger allocations.

## References

- Russell, S. and Norvig, P., *Artificial Intelligence: A Modern Approach*, sections on problem-solving agents and search.
- Python documentation, `dataclasses`: https://docs.python.org/3/library/dataclasses.html
- Python documentation, `csv`: https://docs.python.org/3/library/csv.html
- Matplotlib documentation: https://matplotlib.org/stable/
- pytest documentation: https://docs.pytest.org/
