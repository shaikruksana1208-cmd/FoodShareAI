"""Explainable food matching and small-dataset allocation algorithms."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Mapping, Sequence

SCORE_WEIGHTS = {"category": 40, "quantity": 25, "urgency": 20, "location": 15}
URGENCY_POINTS = {"low": 5, "medium": 12, "high": 20}


@dataclass(frozen=True)
class Candidate:
    donation_id: Any
    request_id: Any
    compatible: bool
    score: float | None
    match_reasons: tuple[str, ...]
    rejected_constraints: tuple[str, ...]
    recommended_next_action: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "donation_id": self.donation_id,
            "request_id": self.request_id,
            "compatible": self.compatible,
            "compatibility_score": self.score,
            "match_reasons": list(self.match_reasons),
            "rejected_constraints": list(self.rejected_constraints),
            "recommended_next_action": self.recommended_next_action,
        }


@dataclass(frozen=True)
class Allocation:
    method: str
    assignments: tuple[dict[str, Any], ...]
    total_score: float
    search_states: int


def _normalized(value: Any) -> str:
    return " ".join(str(value).strip().casefold().split()) if value is not None else ""


def _positive_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) and number > 0 else None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _utc_now(now: datetime | None) -> datetime:
    selected = now or datetime.now(timezone.utc)
    if selected.tzinfo is None:
        raise ValueError("now must include a timezone")
    return selected.astimezone(timezone.utc)


def evaluate_pair(
    donation: Mapping[str, Any],
    request: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> Candidate:
    """Evaluate a pair; hard constraints always override score."""
    donation_id = donation.get("id")
    request_id = request.get("id")
    rejected: list[str] = []
    reasons: list[str] = []
    if donation_id is None or not str(donation_id).strip():
        rejected.append("Donation ID is missing")
    if request_id is None or not str(request_id).strip():
        rejected.append("Request ID is missing")
    category_donation = _normalized(donation.get("category"))
    category_request = _normalized(request.get("category"))
    if not category_donation or not category_request:
        rejected.append("Food category is missing")
    elif category_donation != category_request:
        rejected.append("Food categories are incompatible")

    donation_quantity = _positive_number(donation.get("quantity"))
    request_quantity = _positive_number(request.get("quantity"))
    if donation_quantity is None:
        rejected.append("Donation quantity must be a positive number")
    if request_quantity is None:
        rejected.append("Requested quantity must be a positive number")
    donation_unit = _normalized(donation.get("unit"))
    request_unit = _normalized(request.get("unit"))
    if not donation_unit or not request_unit:
        rejected.append("Quantity unit is missing")
    elif donation_unit != request_unit:
        rejected.append("Donation and request quantity units do not match")
    if _normalized(donation.get("status")) != "available":
        rejected.append("Donation is not available")
    if _normalized(request.get("status")) not in {"open", "pending"}:
        rejected.append("Request is not open")
    if donation.get("food_safe") is not True and donation.get("food_safe") != 1:
        rejected.append("Food safety has not been confirmed")

    expiry = _parse_datetime(donation.get("expires_at"))
    if expiry is None:
        rejected.append("Donation expiry is missing or invalid")
    elif expiry <= _utc_now(now):
        rejected.append("Donation is expired")
    if donation_quantity is not None and request_quantity is not None:
        if donation_quantity < request_quantity:
            rejected.append("Available quantity is insufficient for a complete request")
    urgency = _normalized(request.get("urgency"))
    if urgency not in URGENCY_POINTS:
        rejected.append("Request urgency is missing or invalid")

    if rejected:
        return Candidate(
            donation_id,
            request_id,
            False,
            None,
            (),
            tuple(rejected),
            "Correct the rejected data or choose another donation",
        )

    assert donation_quantity is not None and request_quantity is not None
    score = float(SCORE_WEIGHTS["category"])
    reasons.append(f"Exact category match: {category_donation} (+40)")
    quantity_points = SCORE_WEIGHTS["quantity"] * request_quantity / donation_quantity
    score += quantity_points
    reasons.append(
        f"Quantity can fully satisfy the request ({request_quantity:g} of {donation_quantity:g}) "
        f"(+{quantity_points:.1f})"
    )
    urgency_points = URGENCY_POINTS[urgency]
    score += urgency_points
    reasons.append(f"{urgency.title()} pickup urgency (+{urgency_points})")
    donation_location = _normalized(donation.get("location"))
    request_location = _normalized(request.get("location"))
    if donation_location and request_location:
        location_points = 15 if donation_location == request_location else 5
        score += location_points
        if donation_location == request_location:
            reasons.append("Named pickup area matches (+15)")
        else:
            reasons.append("Pickup areas differ; no distance is inferred (+5)")
    else:
        reasons.append("Location unavailable; location score is not added")
    reasons.append("Food is marked safe and has not expired")
    return Candidate(
        donation_id,
        request_id,
        True,
        round(score, 2),
        tuple(reasons),
        (),
        "Review the details and coordinate pickup",
    )


def evaluate_candidates(
    donations: Sequence[Mapping[str, Any]],
    requests: Sequence[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> list[Candidate]:
    """Evaluate and rank every pair, including rejected pairs for diagnostics."""
    candidates = [
        evaluate_pair(donation, request, now=now)
        for donation in donations
        for request in requests
    ]
    return sorted(
        candidates,
        key=lambda item: (
            not item.compatible,
            -(item.score or 0),
            str(item.request_id),
            str(item.donation_id),
        ),
    )


def recommend(
    donations: Sequence[Mapping[str, Any]],
    requests: Sequence[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> list[Candidate]:
    """Return only eligible, safe matches; rejected pairs are never recommendations."""
    return [
        candidate
        for candidate in evaluate_candidates(donations, requests, now=now)
        if candidate.compatible
    ]


def _allocation_candidate(
    donation: Mapping[str, Any],
    request: Mapping[str, Any],
    remaining: float,
    *,
    now: datetime,
) -> Candidate:
    adjusted = dict(donation)
    adjusted["quantity"] = remaining
    return evaluate_pair(adjusted, request, now=now)


def _uniquely_identified(records: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Exclude missing or duplicate IDs so ambiguous records cannot be allocated."""
    counts: dict[str, int] = {}
    for record in records:
        identifier = record.get("id")
        if identifier is not None and str(identifier).strip():
            key = str(identifier)
            counts[key] = counts.get(key, 0) + 1
    return [
        record
        for record in records
        if record.get("id") is not None
        and str(record.get("id")).strip()
        and counts.get(str(record.get("id"))) == 1
    ]


def allocate_greedy(
    donations: Sequence[Mapping[str, Any]],
    requests: Sequence[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> Allocation:
    """Repeatedly assign the highest-scoring currently feasible pair."""
    current_time = _utc_now(now)
    ordered_donations = sorted(_uniquely_identified(donations), key=lambda row: str(row.get("id")))
    ordered_requests = sorted(_uniquely_identified(requests), key=lambda row: str(row.get("id")))
    remaining = {
        str(row.get("id")): _positive_number(row.get("quantity")) or 0
        for row in ordered_donations
    }
    pending = {str(row.get("id")): row for row in ordered_requests}
    assignments: list[dict[str, Any]] = []
    states = 0
    while pending:
        best: tuple[Candidate, Mapping[str, Any], Mapping[str, Any]] | None = None
        for request in pending.values():
            for donation in ordered_donations:
                states += 1
                candidate = _allocation_candidate(
                    donation,
                    request,
                    remaining[str(donation.get("id"))],
                    now=current_time,
                )
                if candidate.compatible and (
                    best is None
                    or candidate.score > best[0].score
                    or (
                        candidate.score == best[0].score
                        and (str(candidate.request_id), str(candidate.donation_id))
                        < (str(best[0].request_id), str(best[0].donation_id))
                    )
                ):
                    best = (candidate, donation, request)
        if best is None:
            break
        candidate, donation, request = best
        quantity = float(request["quantity"])
        remaining[str(donation.get("id"))] -= quantity
        assignments.append(
            {
                "donation_id": donation.get("id"),
                "request_id": request.get("id"),
                "quantity": quantity,
                "score": candidate.score,
                "match_reasons": list(candidate.match_reasons),
            }
        )
        pending.pop(str(request.get("id")))
    return Allocation(
        "greedy",
        tuple(assignments),
        round(sum(item["score"] or 0 for item in assignments), 2),
        states,
    )


def allocate_exhaustive(
    donations: Sequence[Mapping[str, Any]],
    requests: Sequence[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> Allocation:
    """Enumerate assignments, maximizing fulfilled request count then score."""
    current_time = _utc_now(now)
    ordered_donations = sorted(_uniquely_identified(donations), key=lambda row: str(row.get("id")))
    ordered_requests = sorted(_uniquely_identified(requests), key=lambda row: str(row.get("id")))
    initial_remaining = [
        _positive_number(row.get("quantity")) or 0 for row in ordered_donations
    ]
    states = 0
    best_assignments: list[dict[str, Any]] = []
    best_objective: tuple[int, float] = (-1, -1.0)
    best_tie_key: tuple[tuple[str, str], ...] | None = None

    def search(
        request_index: int,
        remaining: list[float],
        assignments: list[dict[str, Any]],
        score_total: float,
    ) -> None:
        nonlocal states, best_assignments, best_objective, best_tie_key
        states += 1
        if request_index == len(ordered_requests):
            objective = (len(assignments), round(score_total, 8))
            tie_key = tuple(
                (str(item["request_id"]), str(item["donation_id"]))
                for item in assignments
            )
            if objective > best_objective or (
                objective == best_objective
                and (best_tie_key is None or tie_key < best_tie_key)
            ):
                best_objective = objective
                best_tie_key = tie_key
                best_assignments = [dict(item) for item in assignments]
            return

        request = ordered_requests[request_index]
        for donation_index, donation in enumerate(ordered_donations):
            candidate = _allocation_candidate(
                donation, request, remaining[donation_index], now=current_time
            )
            if not candidate.compatible:
                continue
            quantity = float(request["quantity"])
            next_remaining = list(remaining)
            next_remaining[donation_index] -= quantity
            assignments.append(
                {
                    "donation_id": donation.get("id"),
                    "request_id": request.get("id"),
                    "quantity": quantity,
                    "score": candidate.score,
                    "match_reasons": list(candidate.match_reasons),
                }
            )
            search(
                request_index + 1,
                next_remaining,
                assignments,
                score_total + (candidate.score or 0),
            )
            assignments.pop()
        search(request_index + 1, remaining, assignments, score_total)

    search(0, initial_remaining, [], 0)
    return Allocation(
        "exhaustive_search",
        tuple(best_assignments),
        round(sum(item["score"] or 0 for item in best_assignments), 2),
        states,
    )


def validate_allocation(
    allocation: Allocation,
    donations: Sequence[Mapping[str, Any]],
    requests: Sequence[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """Count invalid selected pairs, duplicate requests, and overallocated stock."""
    donation_by_id = {str(row.get("id")): row for row in donations}
    request_by_id = {str(row.get("id")): row for row in requests}
    request_counts: dict[str, int] = {}
    allocated: dict[str, float] = {}
    invalid = 0
    for item in allocation.assignments:
        donation_key = str(item["donation_id"])
        request_key = str(item["request_id"])
        donation = donation_by_id.get(donation_key)
        request = request_by_id.get(request_key)
        if donation is None or request is None:
            invalid += 1
            continue
        if not evaluate_pair(donation, request, now=now).compatible:
            invalid += 1
        requested_quantity = _positive_number(request.get("quantity"))
        allocated_quantity = _positive_number(item.get("quantity"))
        if requested_quantity is None or allocated_quantity != requested_quantity:
            invalid += 1
        request_counts[request_key] = request_counts.get(request_key, 0) + 1
        allocated[donation_key] = allocated.get(donation_key, 0) + (allocated_quantity or 0)
    over_allocated = sum(
        allocated_quantity > (_positive_number(donation_by_id[key].get("quantity")) or 0) + 1e-9
        for key, allocated_quantity in allocated.items()
        if key in donation_by_id
    )
    duplicate_requests = sum(count > 1 for count in request_counts.values())
    return {
        "invalid_matches": invalid,
        "double_allocations": duplicate_requests + int(over_allocated),
        "constraint_violations": invalid + duplicate_requests + int(over_allocated),
    }