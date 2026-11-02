"""Run reproducible synthetic allocation experiments and export CSVs/charts."""

from __future__ import annotations

import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from matching_agent import (  # noqa: E402
    URGENCY_POINTS,
    allocate_exhaustive,
    allocate_greedy,
    evaluate_candidates,
    validate_allocation,
)

DATA_DIR = ROOT / "experiments" / "data"
RESULTS_DIR = ROOT / "experiments" / "results"
AS_OF = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
REPETITIONS = 25


def load_csv(path: Path, *, boolean_fields: set[str] | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            record: dict[str, Any] = dict(row)
            for key in ("quantity",):
                if record.get(key, "").strip():
                    try:
                        record[key] = float(record[key])
                    except ValueError:
                        pass
            for key in boolean_fields or set():
                value = record.get(key, "").strip().casefold()
                record[key] = True if value == "true" else False if value == "false" else None
            records.append(record)
    return records


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    donations = load_csv(DATA_DIR / "synthetic_donations.csv", boolean_fields={"food_safe"})
    requests = load_csv(DATA_DIR / "synthetic_requests.csv")
    algorithms = {
        "greedy": allocate_greedy,
        "exhaustive_search": allocate_exhaustive,
    }
    rejected_candidates = sum(
        not item.compatible for item in evaluate_candidates(donations, requests, now=AS_OF)
    )
    eligible_requested_quantity = sum(
        float(row["quantity"])
        for row in requests
        if row.get("id")
        and str(row.get("category", "")).strip()
        and isinstance(row.get("quantity"), (float, int))
        and row["quantity"] > 0
        and str(row.get("unit", "")).strip()
        and str(row.get("status", "")).casefold() in {"open", "pending"}
        and str(row.get("urgency", "")).casefold() in URGENCY_POINTS
    )
    run_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []

    for method, allocator in algorithms.items():
        latest = None
        for repetition in range(1, REPETITIONS + 1):
            start = time.perf_counter()
            allocation = allocator(donations, requests, now=AS_OF)
            elapsed = time.perf_counter() - start
            checks = validate_allocation(allocation, donations, requests, now=AS_OF)
            fulfilled_quantity = sum(float(item["quantity"]) for item in allocation.assignments)
            run_rows.append(
                {
                    "method": method,
                    "repetition": repetition,
                    "valid_matches": len(allocation.assignments),
                    "quantity_fulfilled": round(fulfilled_quantity, 3),
                    "eligible_requested_quantity": round(eligible_requested_quantity, 3),
                    "quantity_fulfillment_rate": round(
                        fulfilled_quantity / eligible_requested_quantity
                        if eligible_requested_quantity else 0,
                        6,
                    ),
                    "rejected_candidate_pairs": rejected_candidates,
                    "invalid_matches": checks["invalid_matches"],
                    "double_allocations": checks["double_allocations"],
                    "constraint_violations": checks["constraint_violations"],
                    "execution_seconds": f"{elapsed:.9f}",
                    "allocation_score": allocation.total_score,
                    "search_states": allocation.search_states,
                    "dataset_label": "SYNTHETIC_ONLY",
                }
            )
            latest = allocation
        assert latest is not None
        detail_rows.extend(
            {
                "method": method,
                "donation_id": item["donation_id"],
                "request_id": item["request_id"],
                "quantity_allocated": item["quantity"],
                "compatibility_score": item["score"],
                "match_reasons": " | ".join(item["match_reasons"]),
                "dataset_label": "SYNTHETIC_ONLY",
            }
            for item in latest.assignments
        )

    write_csv(
        RESULTS_DIR / "experiment_runs.csv",
        run_rows,
        [
            "method", "repetition", "valid_matches", "quantity_fulfilled",
            "eligible_requested_quantity",
            "quantity_fulfillment_rate", "rejected_candidate_pairs", "invalid_matches",
            "double_allocations", "constraint_violations", "execution_seconds",
            "allocation_score", "search_states", "dataset_label",
        ],
    )
    write_csv(
        RESULTS_DIR / "allocation_details.csv",
        detail_rows,
        [
            "method", "donation_id", "request_id", "quantity_allocated",
            "compatibility_score", "match_reasons", "dataset_label",
        ],
    )

    summary_rows = []
    for method in algorithms:
        method_rows = [row for row in run_rows if row["method"] == method]
        summary_rows.append(
            {
                "method": method,
                "runs": len(method_rows),
                "mean_valid_matches": mean(row["valid_matches"] for row in method_rows),
                "mean_quantity_fulfilled": mean(row["quantity_fulfilled"] for row in method_rows),
                "mean_quantity_fulfillment_rate": mean(
                    row["quantity_fulfillment_rate"] for row in method_rows
                ),
                "mean_invalid_matches": mean(row["invalid_matches"] for row in method_rows),
                "mean_double_allocations": mean(row["double_allocations"] for row in method_rows),
                "mean_constraint_violations": mean(row["constraint_violations"] for row in method_rows),
                "mean_execution_seconds": mean(float(row["execution_seconds"]) for row in method_rows),
                "execution_seconds_population_stddev": pstdev(
                    float(row["execution_seconds"]) for row in method_rows
                ),
                "mean_allocation_score": mean(row["allocation_score"] for row in method_rows),
                "rejected_candidate_pairs": rejected_candidates,
                "dataset_label": "SYNTHETIC_ONLY",
            }
        )
    write_csv(
        RESULTS_DIR / "experiment_summary.csv",
        summary_rows,
        list(summary_rows[0].keys()),
    )

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = [row["method"].replace("_", " ").title() for row in summary_rows]
    colors = ["#7e9b81", "#cf9278"]
    figure, axes = plt.subplots(1, 2, figsize=(10, 4.5), constrained_layout=True)
    axes[0].bar(names, [row["mean_valid_matches"] for row in summary_rows], color=colors)
    axes[0].set_title("Mean fully satisfied requests")
    axes[0].set_ylabel("Requests per run")
    axes[0].grid(axis="y", alpha=0.2)
    axes[1].bar(
        names,
        [row["mean_quantity_fulfillment_rate"] * 100 for row in summary_rows],
        color=colors,
    )
    axes[1].set_title("Mean requested quantity fulfilled")
    axes[1].set_ylabel("Percent of all requested quantity")
    axes[1].grid(axis="y", alpha=0.2)
    figure.suptitle("Synthetic FoodShare allocation comparison (not real activity)")
    figure.savefig(RESULTS_DIR / "allocation_quality.png", dpi=160)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(7, 4.5), constrained_layout=True)
    axis.bar(
        names,
        [row["mean_execution_seconds"] for row in summary_rows],
        yerr=[row["execution_seconds_population_stddev"] for row in summary_rows],
        capsize=5,
        color=colors,
    )
    axis.set_title("Mean allocation execution time")
    axis.set_ylabel("Seconds (error bars: population standard deviation)")
    axis.grid(axis="y", alpha=0.2)
    figure.suptitle("Synthetic FoodShare allocation comparison (not real activity)")
    figure.savefig(RESULTS_DIR / "allocation_timing.png", dpi=160)
    plt.close(figure)

    print(f"Synthetic donations: {len(donations)}")
    print(f"Synthetic requests: {len(requests)}")
    print(f"Rejected candidate pairs: {rejected_candidates}")
    print(f"Repetitions per method: {REPETITIONS}")
    for row in summary_rows:
        print(
            f"{row['method']}: valid_matches={row['mean_valid_matches']:.2f}, "
            f"fulfillment={row['mean_quantity_fulfillment_rate']:.3f}, "
            f"invalid={row['mean_invalid_matches']:.2f}, "
            f"double_allocations={row['mean_double_allocations']:.2f}, "
            f"violations={row['mean_constraint_violations']:.2f}, "
            f"mean_seconds={row['mean_execution_seconds']:.9f}"
        )
    print(f"Results written to: {RESULTS_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    run()