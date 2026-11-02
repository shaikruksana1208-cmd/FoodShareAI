from datetime import datetime, timedelta, timezone
import sqlite3
from pathlib import Path

import pytest

from app import SCHEMA, create_app


@pytest.fixture
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "test.sqlite3"),
            "SECRET_KEY": "test-only-secret",
            "ADMIN_EMAILS": {"admin@example.test"},
            "SESSION_COOKIE_SECURE": False,
        }
    )
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client):
    response = client.get("/api/csrf")
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json["csrf_token"]}


def register(client, name, email, role, headers):
    response = client.post(
        "/api/register",
        json={"name": name, "email": email, "password": "test-password-123", "role": role},
        headers=headers,
    )
    assert response.status_code == 201, response.json
    return response.json["user"]


def donation_payload(**changes):
    expires = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    return {
        "food_name": "Garden tomatoes",
        "category": "produce",
        "quantity": 5,
        "unit": "kg",
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires,
        "location": "Northside",
        "storage_info": "Keep chilled",
        "condition_info": "Fresh and undamaged",
        "donor_contact": "donor@example.test",
        "food_safe": True,
        **changes,
    }


def request_payload(**changes):
    return {
        "category": "produce",
        "quantity": 3,
        "unit": "kg",
        "urgency": "high",
        "location": "Northside",
        **changes,
    }


def test_homepage_and_frontend_assets_are_served(client):
    assert client.get("/").status_code == 200
    assert b"FoodShare AI" in client.get("/").data
    assert client.get("/style.css").status_code == 200
    assert client.get("/script.js").status_code == 200


def test_registration_login_and_password_hash_storage(client, app):
    headers = csrf(client)
    result = register(client, "Donor", "donor@example.test", "donor", headers)
    assert result["role"] == "donor"
    stored = client.application
    with stored.app_context():
        import sqlite3

        connection = sqlite3.connect(stored.config["DATABASE"])
        password_hash = connection.execute(
            "SELECT password_hash FROM users WHERE email=?", ("donor@example.test",)
        ).fetchone()[0]
        connection.close()
    assert password_hash != "test-password-123"
    client.post("/api/logout", headers=csrf(client))
    login = client.post(
        "/api/login", json={"email": "donor@example.test", "password": "test-password-123"},
        headers=csrf(client),
    )
    assert login.status_code == 200
    assert login.json["user"]["id"] == result["id"]


def test_donation_request_match_acceptance_and_persisted_dashboard(client):
    donor_headers = csrf(client)
    donor = register(client, "Donor", "donor@example.test", "donor", donor_headers)
    created_donation = client.post(
        "/api/donations", json=donation_payload(), headers=csrf(client)
    )
    assert created_donation.status_code == 201
    donation_id = created_donation.json["donation"]["id"]
    assert client.get("/api/donations").json["donations"][0]["food_name"] == "Garden tomatoes"

    client.post("/api/logout", headers=csrf(client))
    register(client, "Recipient", "recipient@example.test", "recipient", csrf(client))
    created_request = client.post(
        "/api/requests", json=request_payload(), headers=csrf(client)
    )
    assert created_request.status_code == 201
    request_id = created_request.json["food_request"]["id"]
    match = client.get(f"/api/matches?request_id={request_id}")
    assert match.status_code == 200
    assert len(match.json["recommendations"]) == 1
    assert match.json["recommendations"][0]["compatibility_score"] > 0
    assert match.json["recommendations"][0]["match_reasons"]
    assert client.post(
        f"/api/matches/{donation_id}/{request_id}/accept", headers=csrf(client)
    ).status_code == 403

    client.post("/api/logout", headers=csrf(client))
    login = client.post(
        "/api/login", json={"email": "donor@example.test", "password": "test-password-123"},
        headers=csrf(client),
    )
    assert login.status_code == 200
    accepted = client.post(
        f"/api/matches/{donation_id}/{request_id}/accept", headers=csrf(client)
    )
    assert accepted.status_code == 201, accepted.json
    assert client.post(
        f"/api/matches/{donation_id}/{request_id}/accept", headers=csrf(client)
    ).status_code == 409

    client.post("/api/logout", headers=csrf(client))
    register(client, "Admin", "admin@example.test", "recipient", csrf(client))
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json["statistics"]["quantity_reserved_by_unit"] == {"kg": 3}
    assert dashboard.json["statistics"]["quantity_collected_by_unit"] == {}


def test_empty_admin_dashboard_uses_zero_counts_not_null(client):
    register(client, "Admin", "admin@example.test", "recipient", csrf(client))
    result = client.get("/api/dashboard")
    assert result.status_code == 200
    statistics = result.json["statistics"]
    assert statistics["total_donations"] == 0
    assert statistics["reserved_donations"] == 0
    assert statistics["expired_donations"] == 0
    assert statistics["reserved_requests"] == 0
    assert statistics["collected_requests"] == 0
    assert statistics["quantity_reserved_by_unit"] == {}
    assert statistics["quantity_collected_by_unit"] == {}


def test_available_donation_search_and_category_filters(client):
    register(client, "Donor", "filter@example.test", "donor", csrf(client))
    first = client.post("/api/donations", json=donation_payload(), headers=csrf(client))
    second = client.post(
        "/api/donations",
        json=donation_payload(food_name="Fresh bread", category="Bakery", unit="loaf"),
        headers=csrf(client),
    )
    assert first.status_code == second.status_code == 201
    assert [item["food_name"] for item in client.get("/api/donations?q=bread").json["donations"]] == ["Fresh bread"]
    assert [item["category"] for item in client.get("/api/donations?category=produce").json["donations"]] == ["produce"]
    assert client.get("/api/donations?status=unknown").status_code == 400


def test_two_requests_cannot_overallocate_the_same_donation(client, app):
    register(client, "Donor", "competition-donor@example.test", "donor", csrf(client))
    created = client.post(
        "/api/donations", json=donation_payload(quantity=5), headers=csrf(client)
    )
    donation_id = created.json["donation"]["id"]

    client.post("/api/logout", headers=csrf(client))
    register(client, "Recipient One", "first@example.test", "recipient", csrf(client))
    first = client.post("/api/requests", json=request_payload(quantity=4), headers=csrf(client))
    first_id = first.json["food_request"]["id"]

    client.post("/api/logout", headers=csrf(client))
    register(client, "Recipient Two", "second@example.test", "recipient", csrf(client))
    second = client.post("/api/requests", json=request_payload(quantity=4), headers=csrf(client))
    second_id = second.json["food_request"]["id"]

    client.post("/api/logout", headers=csrf(client))
    client.post(
        "/api/login",
        json={"email": "competition-donor@example.test", "password": "test-password-123"},
        headers=csrf(client),
    )
    first_acceptance = client.post(
        f"/api/matches/{donation_id}/{first_id}/accept", headers=csrf(client)
    )
    second_acceptance = client.post(
        f"/api/matches/{donation_id}/{second_id}/accept", headers=csrf(client)
    )
    assert first_acceptance.status_code == 201
    assert second_acceptance.status_code == 409

    with app.app_context():
        import sqlite3

        connection = sqlite3.connect(app.config["DATABASE"])
        remaining, allocation_count, second_status = connection.execute(
            "SELECT d.remaining_quantity, (SELECT COUNT(*) FROM allocations), "
            "(SELECT status FROM food_requests WHERE id=?) FROM donations d WHERE d.id=?",
            (second_id, donation_id),
        ).fetchone()
        connection.close()
    assert remaining == 1
    assert allocation_count == 1
    assert second_status == "open"


def test_donation_expiring_after_recommendation_cannot_be_accepted(client, app):
    register(client, "Donor", "expiry-donor@example.test", "donor", csrf(client))
    created = client.post("/api/donations", json=donation_payload(), headers=csrf(client))
    donation_id = created.json["donation"]["id"]
    client.post("/api/logout", headers=csrf(client))
    register(client, "Recipient", "expiry-recipient@example.test", "recipient", csrf(client))
    submitted = client.post("/api/requests", json=request_payload(), headers=csrf(client))
    request_id = submitted.json["food_request"]["id"]
    assert client.get(f"/api/matches?request_id={request_id}").json["recommendations"]

    with app.app_context():
        import sqlite3

        connection = sqlite3.connect(app.config["DATABASE"])
        connection.execute(
            "UPDATE donations SET expires_at=? WHERE id=?",
            ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), donation_id),
        )
        connection.commit()
        connection.close()

    client.post("/api/logout", headers=csrf(client))
    client.post(
        "/api/login",
        json={"email": "expiry-donor@example.test", "password": "test-password-123"},
        headers=csrf(client),
    )
    acceptance = client.post(
        f"/api/matches/{donation_id}/{request_id}/accept", headers=csrf(client)
    )
    assert acceptance.status_code == 409
    assert "no longer satisfies" in acceptance.json["error"].lower()


def test_collection_requires_request_owner_and_cannot_be_confirmed_twice(client):
    register(client, "Donor", "collect-donor@example.test", "donor", csrf(client))
    donation = client.post("/api/donations", json=donation_payload(), headers=csrf(client)).json["donation"]
    donation_id = donation["id"]
    client.post("/api/logout", headers=csrf(client))
    register(client, "Recipient", "collect-recipient@example.test", "recipient", csrf(client))
    request_id = client.post("/api/requests", json=request_payload(), headers=csrf(client)).json["food_request"]["id"]
    client.post("/api/logout", headers=csrf(client))
    client.post("/api/login", json={"email": "collect-donor@example.test", "password": "test-password-123"}, headers=csrf(client))
    acceptance = client.post(f"/api/matches/{donation_id}/{request_id}/accept", headers=csrf(client))
    assert acceptance.status_code == 201
    allocation_id = acceptance.json["allocation"]["id"]
    assert acceptance.json["allocation"]["status"] == "reserved"

    forbidden = client.post(f"/api/allocations/{allocation_id}/collect", headers=csrf(client))
    assert forbidden.status_code == 403
    client.post("/api/logout", headers=csrf(client))
    register(client, "Admin", "admin@example.test", "recipient", csrf(client))
    before_collection = client.get("/api/dashboard").json["statistics"]
    assert before_collection["reserved_requests"] == 1
    assert before_collection["collected_requests"] == 0
    assert before_collection["quantity_reserved_by_unit"] == {"kg": 3}
    client.post("/api/logout", headers=csrf(client))
    client.post("/api/login", json={"email": "collect-recipient@example.test", "password": "test-password-123"}, headers=csrf(client))
    collected = client.post(f"/api/allocations/{allocation_id}/collect", headers=csrf(client))
    assert collected.status_code == 200
    assert collected.json["allocation"]["status"] == "collected"
    duplicate = client.post(f"/api/allocations/{allocation_id}/collect", headers=csrf(client))
    assert duplicate.status_code == 409
    client.post("/api/logout", headers=csrf(client))
    client.post(
        "/api/login",
        json={"email": "admin@example.test", "password": "test-password-123"},
        headers=csrf(client),
    )
    after_collection = client.get("/api/dashboard").json["statistics"]
    assert after_collection["reserved_requests"] == 0
    assert after_collection["collected_requests"] == 1
    assert after_collection["quantity_reserved_by_unit"] == {}
    assert after_collection["quantity_collected_by_unit"] == {"kg": 3}


def test_fully_collected_donation_changes_to_completed(client):
    register(client, "Donor", "full-donor@example.test", "donor", csrf(client))

    donation = client.post(
        "/api/donations",
        json=donation_payload(quantity=3),
        headers=csrf(client),
    ).json["donation"]

    client.post("/api/logout", headers=csrf(client))

    register(client, "Recipient", "full-recipient@example.test", "recipient", csrf(client))

    request_id = client.post(
        "/api/requests",
        json=request_payload(quantity=3),
        headers=csrf(client),
    ).json["food_request"]["id"]

    client.post("/api/logout", headers=csrf(client))

    client.post(
        "/api/login",
        json={"email": "full-donor@example.test", "password": "test-password-123"},
        headers=csrf(client),
    )

    accepted = client.post(
        f"/api/matches/{donation['id']}/{request_id}/accept",
        headers=csrf(client),
    )

    assert accepted.status_code == 201

    client.post("/api/logout", headers=csrf(client))

    client.post(
        "/api/login",
        json={"email": "full-recipient@example.test", "password": "test-password-123"},
        headers=csrf(client),
    )

    collected = client.post(
        f"/api/allocations/{accepted.json['allocation']['id']}/collect",
        headers=csrf(client),
    )

    assert collected.status_code == 200
    assert client.get("/api/donations").json["donations"] == []

    client.post("/api/logout", headers=csrf(client))

    client.post(
        "/api/login",
        json={"email": "full-donor@example.test", "password": "test-password-123"},
        headers=csrf(client),
    )

    donations = client.get("/api/my/donations").json["donations"]
    assert donations[0]["status"] == "completed"

def test_cancelling_reserved_request_restores_inventory_once(client, app):
    register(client, "Donor", "cancel-donor@example.test", "donor", csrf(client))
    donation = client.post("/api/donations", json=donation_payload(), headers=csrf(client)).json["donation"]
    donation_id = donation["id"]
    client.post("/api/logout", headers=csrf(client))
    register(client, "Recipient", "cancel-recipient@example.test", "recipient", csrf(client))
    request_id = client.post("/api/requests", json=request_payload(), headers=csrf(client)).json["food_request"]["id"]
    client.post("/api/logout", headers=csrf(client))
    client.post("/api/login", json={"email": "cancel-donor@example.test", "password": "test-password-123"}, headers=csrf(client))
    accepted = client.post(f"/api/matches/{donation_id}/{request_id}/accept", headers=csrf(client))
    assert accepted.status_code == 201

    client.post("/api/logout", headers=csrf(client))
    client.post("/api/login", json={"email": "cancel-recipient@example.test", "password": "test-password-123"}, headers=csrf(client))
    cancelled = client.post(f"/api/requests/{request_id}/cancel", json={}, headers=csrf(client))
    assert cancelled.status_code == 200
    again = client.post(f"/api/requests/{request_id}/cancel", json={}, headers=csrf(client))
    assert again.status_code == 409
    with app.app_context():
        db = sqlite3.connect(app.config["DATABASE"])
        remaining, reserved, request_status, allocation_status = db.execute(
            "SELECT d.remaining_quantity,d.reserved_quantity,r.status,a.status "
            "FROM donations d JOIN allocations a ON a.donation_id=d.id "
            "JOIN food_requests r ON r.id=a.request_id WHERE d.id=?", (donation_id,)
        ).fetchone()
        db.close()
    assert remaining == 5
    assert reserved == 0
    assert request_status == allocation_status == "cancelled"
    client.post("/api/logout", headers=csrf(client))
    register(client, "Admin", "admin@example.test", "recipient", csrf(client))
    statistics = client.get("/api/dashboard").json["statistics"]
    assert statistics["cancelled_requests"] == 1
    assert statistics["cancelled_allocations"] == 1
    assert statistics["quantity_available_by_unit"] == {"kg": 5}
    assert statistics["quantity_reserved_by_unit"] == {}
    assert statistics["quantity_cancelled_by_unit"] == {"kg": 3}


def test_expired_reservation_cannot_be_confirmed_and_cancelled_stock_stays_hidden(client, app):
    register(client, "Donor", "stale-donor@example.test", "donor", csrf(client))
    donation = client.post("/api/donations", json=donation_payload(), headers=csrf(client)).json["donation"]
    donation_id = donation["id"]
    client.post("/api/logout", headers=csrf(client))
    register(client, "Recipient", "stale-recipient@example.test", "recipient", csrf(client))
    request_id = client.post("/api/requests", json=request_payload(), headers=csrf(client)).json["food_request"]["id"]
    client.post("/api/logout", headers=csrf(client))
    client.post("/api/login", json={"email": "stale-donor@example.test", "password": "test-password-123"}, headers=csrf(client))
    acceptance = client.post(f"/api/matches/{donation_id}/{request_id}/accept", headers=csrf(client))
    allocation_id = acceptance.json["allocation"]["id"]
    with app.app_context():
        db = sqlite3.connect(app.config["DATABASE"])
        db.execute(
            "UPDATE donations SET expires_at=? WHERE id=?",
            ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), donation_id),
        )
        db.commit()
        db.close()
    client.post("/api/logout", headers=csrf(client))
    client.post("/api/login", json={"email": "stale-recipient@example.test", "password": "test-password-123"}, headers=csrf(client))
    collection = client.post(f"/api/allocations/{allocation_id}/collect", headers=csrf(client))
    assert collection.status_code == 409
    assert "expired" in collection.json["error"].lower()
    cancelled = client.post(f"/api/requests/{request_id}/cancel", json={}, headers=csrf(client))
    assert cancelled.status_code == 200
    assert client.get("/api/donations").json["donations"] == []


def test_database_trigger_prevents_inventory_above_original_quantity(client, app):
    register(client, "Donor", "inventory-guard@example.test", "donor", csrf(client))
    donation = client.post("/api/donations", json=donation_payload(quantity=5), headers=csrf(client)).json["donation"]
    with app.app_context():
        db = sqlite3.connect(app.config["DATABASE"])
        with pytest.raises(sqlite3.IntegrityError, match="exceeds original quantity"):
            db.execute(
                "UPDATE donations SET reserved_quantity=6 WHERE id=?",
                (donation["id"],),
            )
        db.rollback()
        db.close()


def test_legacy_migration_preserves_records_and_marks_allocations_reserved(tmp_path):
    database = tmp_path / "legacy-copy.sqlite3"
    db = sqlite3.connect(database)
    db.executescript(SCHEMA)
    db.execute("INSERT INTO users VALUES (1,'Old Donor','old@example.test','hashed','donor','2026-01-01T00:00:00Z')")
    db.execute("INSERT INTO users VALUES (2,'Old Recipient','recipient@example.test','hashed','recipient','2026-01-01T00:00:00Z')")
    db.execute(
        "INSERT INTO donations (id,donor_id,food_name,category,quantity,remaining_quantity,unit,prepared_at,expires_at,location,storage_info,condition_info,donor_contact,food_safe,status,created_at) VALUES (10,1,'Beans','produce',5,0,'kg','2026-01-01T00:00:00Z','2099-01-01T00:00:00Z','North','cool','good','old@example.test',1,'completed','2026-01-01T00:00:00Z')"
    )
    db.execute("INSERT INTO food_requests VALUES (20,2,'produce',5,'kg','high','North','completed','2026-01-01T00:00:00Z')")
    db.execute("INSERT INTO allocations VALUES (30,10,20,5,90,'2026-01-01T00:00:00Z')")
    db.commit()
    db.close()

    migrated_app = create_app({"TESTING": True, "DATABASE": str(database), "SECRET_KEY": "migration-test"})
    with migrated_app.app_context():
        db = sqlite3.connect(database)
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM donations").fetchone()[0] == 1
        request_status = db.execute("SELECT status FROM food_requests WHERE id=20").fetchone()[0]
        allocation = db.execute("SELECT status,quantity FROM allocations WHERE id=30").fetchone()
        donation_status, remaining_quantity, reserved_quantity = db.execute(
            "SELECT status,remaining_quantity,reserved_quantity FROM donations WHERE id=10"
        ).fetchone()
        db.close()
    assert request_status == "reserved"
    assert allocation == ("reserved", 5)
    assert donation_status == "available"
    assert remaining_quantity == 0
    assert reserved_quantity == 5

    rerun_app = create_app({"TESTING": True, "DATABASE": str(database), "SECRET_KEY": "migration-test"})
    with rerun_app.app_context():
        db = sqlite3.connect(database)
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM allocations").fetchone()[0] == 1
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        db.close()


def test_migration_of_temporary_copy_preserves_existing_database_rows(tmp_path):
    source_path = Path(__file__).resolve().parents[1] / "instance" / "foodshare.sqlite3"
    if not source_path.exists():
        pytest.skip("No local demo database is present to copy")
    source_uri = "file:" + source_path.resolve().as_posix() + "?mode=ro"
    source = sqlite3.connect(source_uri, uri=True)
    source_version = source.execute("PRAGMA user_version").fetchone()[0]
    tables = [
        row[0]
        for row in source.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('users','donations','food_requests','allocations') ORDER BY name"
        )
    ]
    original_counts = {
        table: source.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in tables
    }
    copied_path = tmp_path / "existing-database-copy.sqlite3"
    copy = sqlite3.connect(copied_path)
    source.backup(copy)
    copy.close()
    source.close()

    migrated_app = create_app(
        {"TESTING": True, "DATABASE": str(copied_path), "SECRET_KEY": "copy-migration-test"}
    )
    with migrated_app.app_context():
        migrated = sqlite3.connect(copied_path)
        migrated_counts = {
            table: migrated.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in original_counts
        }
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == 1
        assert migrated.execute("PRAGMA foreign_key_check").fetchall() == []
        migrated.close()

    source = sqlite3.connect(source_uri, uri=True)
    assert source.execute("PRAGMA user_version").fetchone()[0] == source_version
    assert {
        table: source.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in tables
    } == original_counts
    source.close()
    assert migrated_counts == original_counts


def test_malformed_preparation_timestamp_is_rejected(client):
    register(client, "Donor", "date@example.test", "donor", csrf(client))
    response = client.post(
        "/api/donations",
        json=donation_payload(prepared_at="yesterday-ish"),
        headers=csrf(client),
    )
    assert response.status_code == 400
    assert "preparation" in response.json["error"].lower()


def test_blank_optional_donor_contact_uses_account_email(client):
    register(client, "Donor", "contact@example.test", "donor", csrf(client))
    response = client.post(
        "/api/donations",
        json=donation_payload(donor_contact=""),
        headers=csrf(client),
    )
    assert response.status_code == 201
    assert response.json["donation"]["donor_contact"] == "contact@example.test"


def test_hard_constraints_are_not_returned_as_recommendations(client):
    register(client, "Donor", "donor@example.test", "donor", csrf(client))
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    response = client.post(
        "/api/donations",
        json=donation_payload(expires_at=expired),
        headers=csrf(client),
    )
    assert response.status_code == 400

    response = client.post(
        "/api/donations",
        json=donation_payload(food_safe=False),
        headers=csrf(client),
    )
    assert response.status_code == 400


def test_request_validation_and_unauthorized_routes(client):
    headers = csrf(client)
    assert client.post("/api/donations", json=donation_payload(), headers=headers).status_code == 401
    assert client.post("/api/requests", json=request_payload(), headers=headers).status_code == 401
    register(client, "Recipient", "recipient@example.test", "recipient", csrf(client))
    assert client.get("/api/dashboard").status_code == 403
    bad = client.post(
        "/api/requests", json=request_payload(quantity=-1), headers=csrf(client)
    )
    assert bad.status_code == 400
    assert "quantity" in bad.json["error"].lower()


def test_users_cannot_change_another_donors_record(client):
    register(client, "Donor A", "a@example.test", "donor", csrf(client))
    response = client.post("/api/donations", json=donation_payload(), headers=csrf(client))
    donation_id = response.json["donation"]["id"]
    client.post("/api/logout", headers=csrf(client))
    register(client, "Donor B", "b@example.test", "donor", csrf(client))
    change = client.patch(
        f"/api/donations/{donation_id}/status",
        json={"status": "unavailable"},
        headers=csrf(client),
    )
    assert change.status_code == 403


def test_owner_can_hide_listing_and_expired_food_is_not_available(client, app):
    register(client, "Donor", "owner@example.test", "donor", csrf(client))
    created = client.post("/api/donations", json=donation_payload(), headers=csrf(client))
    donation_id = created.json["donation"]["id"]
    changed = client.patch(
        f"/api/donations/{donation_id}/status",
        json={"status": "unavailable"},
        headers=csrf(client),
    )
    assert changed.status_code == 200
    assert client.get("/api/donations").json["donations"] == []
    client.patch(
        f"/api/donations/{donation_id}/status",
        json={"status": "available"},
        headers=csrf(client),
    )
    with app.app_context():
        import sqlite3

        connection = sqlite3.connect(app.config["DATABASE"])
        connection.execute(
            "UPDATE donations SET expires_at=? WHERE id=?",
            ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), donation_id),
        )
        connection.commit()
        connection.close()
    assert client.get("/api/donations").json["donations"] == []
    unavailable = client.patch(
        f"/api/donations/{donation_id}/status",
        json={"status": "available"},
        headers=csrf(client),
    )
    assert unavailable.status_code == 409
    assert "Expired" in unavailable.json["error"]


def test_admin_all_status_filter_includes_completed_zero_stock(client, app):
    register(client, "Donor", "donor@example.test", "donor", csrf(client))
    created = client.post("/api/donations", json=donation_payload(), headers=csrf(client))
    donation_id = created.json["donation"]["id"]
    with app.app_context():
        import sqlite3

        connection = sqlite3.connect(app.config["DATABASE"])
        connection.execute(
            "UPDATE donations SET status='completed', remaining_quantity=0 WHERE id=?",
            (donation_id,),
        )
        connection.commit()
        connection.close()
    client.post("/api/logout", headers=csrf(client))
    register(client, "Admin", "admin@example.test", "recipient", csrf(client))
    response = client.get("/api/donations?status=all")
    assert response.status_code == 200
    assert len(response.json["donations"]) == 1
    assert response.json["donations"][0]["status"] == "completed"


def test_match_api_excludes_unavailable_pairs_and_returns_rejection_reason(client):
    register(client, "Donor", "donor@example.test", "donor", csrf(client))
    created = client.post("/api/donations", json=donation_payload(), headers=csrf(client))
    donation_id = created.json["donation"]["id"]
    client.patch(
        f"/api/donations/{donation_id}/status",
        json={"status": "unavailable"},
        headers=csrf(client),
    )
    client.post("/api/logout", headers=csrf(client))
    register(client, "Recipient", "recipient@example.test", "recipient", csrf(client))
    request_result = client.post("/api/requests", json=request_payload(), headers=csrf(client))
    request_id = request_result.json["food_request"]["id"]
    matches = client.get(f"/api/matches?request_id={request_id}")
    assert matches.status_code == 200
    assert matches.json["recommendations"] == []
    assert matches.json["rejected_candidate_count"] == 1
    assert "Donation is not available" in matches.json["rejected_candidates"][0]["rejected_constraints"]
def test_missing_csrf_token_blocks_mutation(client):
    client.get("/api/csrf")
    response = client.post(
        "/api/register",
        json={"name": "Donor", "email": "d@example.test", "password": "test-password-123", "role": "donor"},
    )
    assert response.status_code == 400