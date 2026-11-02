from datetime import datetime, timezone

import pytest

from matching_agent import (
    allocate_exhaustive,
    allocate_greedy,
    evaluate_candidates,
    evaluate_pair,
    recommend,
    validate_allocation,
)


NOW = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


def donation(**overrides):
    record = {
        "id": "D1",
        "category": "produce",
        "quantity": 5,
        "unit": "kg",
        "status": "available",
        "food_safe": True,
        "expires_at": "2026-01-03T12:00:00Z",
        "location": "North",
    }
    return {**record, **overrides}


def request(**overrides):
    record = {
        "id": "R1",
        "category": "produce",
        "quantity": 5,
        "unit": "kg",
        "status": "open",
        "urgency": "high",
        "location": "North",
    }
    return {**record, **overrides}


def test_perfect_match_has_maximum_score_and_explanation():
    result = evaluate_pair(donation(), request(), now=NOW)
    assert result.compatible is True
    assert result.score == 100
    assert result.rejected_constraints == ()
    assert any("Exact category" in reason for reason in result.match_reasons)


def test_sqlite_style_integer_true_is_accepted_for_food_safety():
    assert evaluate_pair(donation(food_safe=1), request(), now=NOW).compatible is True


def test_surplus_quantity_is_valid_but_quantity_fit_score_is_lower():
    exact = evaluate_pair(donation(), request(), now=NOW)
    surplus = evaluate_pair(donation(quantity=10), request(), now=NOW)
    assert surplus.compatible is True
    assert surplus.score < exact.score


def test_insufficient_quantity_is_a_hard_rejection():
    result = evaluate_pair(donation(quantity=4), request(quantity=5), now=NOW)
    assert result.compatible is False
    assert any("insufficient" in reason for reason in result.rejected_constraints)


def test_incompatible_category_is_rejected():
    result = evaluate_pair(donation(category="bakery"), request(), now=NOW)
    assert result.compatible is False
    assert "Food categories are incompatible" in result.rejected_constraints


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({"expires_at": "2025-12-31T00:00:00Z"}, "expired"),
        ({"food_safe": False}, "safety"),
    ],
)
def test_expired_or_unsafe_food_is_never_recommended(changes, expected):
    result = evaluate_pair(donation(**changes), request(), now=NOW)
    assert result.compatible is False
    assert any(expected in reason.lower() for reason in result.rejected_constraints)


def test_claimed_donation_is_rejected():
    result = evaluate_pair(donation(status="claimed"), request(), now=NOW)
    assert result.compatible is False
    assert "Donation is not available" in result.rejected_constraints


def test_competing_requests_cannot_overallocate_one_donation():
    donations = [donation(quantity=5)]
    requests = [request(id="R1", quantity=3), request(id="R2", quantity=3)]
    for allocator in (allocate_greedy, allocate_exhaustive):
        allocation = allocator(donations, requests, now=NOW)
        assert len(allocation.assignments) == 1
        assert validate_allocation(allocation, donations, requests, now=NOW) == {
            "invalid_matches": 0,
            "double_allocations": 0,
            "constraint_violations": 0,
        }


def test_multiple_donations_and_requests_are_allocated_without_duplicate_requests():
    donations = [donation(id="D1", quantity=5), donation(id="D2", quantity=4)]
    requests = [request(id="R1", quantity=3), request(id="R2", quantity=4)]
    allocation = allocate_exhaustive(donations, requests, now=NOW)
    assert len(allocation.assignments) == 2
    assert {item["request_id"] for item in allocation.assignments} == {"R1", "R2"}
    assert validate_allocation(allocation, donations, requests, now=NOW)["constraint_violations"] == 0


def test_missing_or_invalid_required_values_are_rejected_safely():
    invalid_records = [
        donation(category=""),
        donation(quantity="lots"),
        donation(expires_at="not-a-date"),
        donation(food_safe=None),
        donation(id=None),
    ]
    invalid_requests = [request(id=None), request(quantity=0), request(urgency="soon"), request(unit="loaves")]
    for bad_donation in invalid_records:
        assert evaluate_pair(bad_donation, request(), now=NOW).compatible is False
    for bad_request in invalid_requests:
        assert evaluate_pair(donation(), bad_request, now=NOW).compatible is False


def test_no_valid_match_returns_rejections_instead_of_fake_recommendations():
    results = recommend(
        [donation(status="claimed")],
        [request()],
        now=NOW,
    )
    diagnostics = evaluate_candidates(
        [donation(status="claimed")],
        [request()],
        now=NOW,
    )
    assert results == []
    assert len(diagnostics) == 1
    assert diagnostics[0].compatible is False
    assert diagnostics[0].score is None
    assert diagnostics[0].rejected_constraints


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "claimed"},
        {"food_safe": False},
        {"expires_at": "2025-12-31T00:00:00Z"},
    ],
)
def test_recommendation_list_never_contains_claimed_unsafe_or_expired_food(changes):
    assert recommend([donation(**changes)], [request()], now=NOW) == []


def test_location_mismatch_is_explained_without_claiming_distance():
    result = evaluate_pair(donation(location="West"), request(location="East"), now=NOW)
    assert result.compatible is True
    assert any("no distance is inferred" in reason for reason in result.match_reasons)


def test_exhaustive_search_is_at_least_as_good_as_greedy_on_small_fixture():
    donations = [donation(id="D1", quantity=5), donation(id="D2", quantity=3)]
    requests = [
        request(id="R1", quantity=3, location="North"),
        request(id="R2", quantity=5, location="North"),
    ]
    greedy = allocate_greedy(donations, requests, now=NOW)
    searched = allocate_exhaustive(donations, requests, now=NOW)
    assert len(searched.assignments) >= len(greedy.assignments)
    if len(searched.assignments) == len(greedy.assignments):
        assert searched.total_score >= greedy.total_score


def test_exhaustive_search_avoids_greedy_competition_trap():
    donations = [
        donation(id="D1", category="prepared meals", quantity=8, unit="portion", location="North"),
        donation(id="D2", category="prepared meals", quantity=5, unit="portion", location="South"),
    ]
    requests = [
        request(id="R1", category="prepared meals", quantity=5, unit="portion", urgency="high", location="North"),
        request(id="R2", category="prepared meals", quantity=8, unit="portion", urgency="low", location="South"),
    ]
    greedy = allocate_greedy(donations, requests, now=NOW)
    searched = allocate_exhaustive(donations, requests, now=NOW)
    assert len(greedy.assignments) == 1
    assert len(searched.assignments) == 2
    assert validate_allocation(searched, donations, requests, now=NOW)["constraint_violations"] == 0


def test_duplicate_ids_are_not_ambiguously_allocated():
    donations = [donation(id="D1"), donation(id="D1")]
    assert allocate_greedy(donations, [request()], now=NOW).assignments == ()
    assert allocate_exhaustive(donations, [request()], now=NOW).assignments == ()


def test_allocation_audit_detects_incorrect_quantity_and_duplicate_request():
    donations = [donation(quantity=10)]
    requests = [request(quantity=5)]
    allocation = allocate_greedy(donations, requests, now=NOW)
    partial = {**allocation.assignments[0], "quantity": 2}
    forged = type(allocation)(
        allocation.method,
        allocation.assignments + (partial,),
        allocation.total_score * 2,
        allocation.search_states,
    )
    audit = validate_allocation(forged, donations, requests, now=NOW)
    assert audit["invalid_matches"] == 1
    assert audit["double_allocations"] == 1
    assert audit["constraint_violations"] == 2