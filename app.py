"""Flask API and SQLite storage for the FoodShare AI demonstration."""

from __future__ import annotations

import os
import re
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import Flask, g, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

from matching_agent import evaluate_candidates, recommend


ROOT = Path(__file__).resolve().parent
SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('donor', 'recipient', 'admin')),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS donations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    donor_id INTEGER NOT NULL REFERENCES users(id),
    food_name TEXT NOT NULL,
    category TEXT NOT NULL,
    quantity REAL NOT NULL CHECK (quantity > 0),
    remaining_quantity REAL NOT NULL CHECK (remaining_quantity >= 0),
    unit TEXT NOT NULL,
    prepared_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    location TEXT NOT NULL,
    storage_info TEXT NOT NULL,
    condition_info TEXT NOT NULL,
    donor_contact TEXT NOT NULL,
    food_safe INTEGER NOT NULL CHECK (food_safe IN (0, 1)),
    status TEXT NOT NULL CHECK (status IN ('available', 'completed', 'unavailable')),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS food_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requester_id INTEGER NOT NULL REFERENCES users(id),
    category TEXT NOT NULL,
    quantity REAL NOT NULL CHECK (quantity > 0),
    unit TEXT NOT NULL,
    urgency TEXT NOT NULL CHECK (urgency IN ('low', 'medium', 'high')),
    location TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'completed', 'cancelled')),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    donation_id INTEGER NOT NULL REFERENCES donations(id),
    request_id INTEGER NOT NULL UNIQUE REFERENCES food_requests(id),
    quantity REAL NOT NULL CHECK (quantity > 0),
    compatibility_score REAL NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (donation_id, request_id)
);
CREATE INDEX IF NOT EXISTS idx_donations_status_expiry ON donations(status, expires_at);
CREATE INDEX IF NOT EXISTS idx_requests_status ON food_requests(status);
CREATE INDEX IF NOT EXISTS idx_allocations_donation ON allocations(donation_id);
"""

SCHEMA_VERSION = 1


def migrate_database(db: sqlite3.Connection) -> None:
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise RuntimeError(f"Database schema version {version} is newer than this application supports")
    if version == SCHEMA_VERSION:
        return

    db.commit()
    db.execute("PRAGMA foreign_keys = OFF")
    try:
        db.execute("BEGIN IMMEDIATE")
        donation_columns = {row[1] for row in db.execute("PRAGMA table_info(donations)")}
        if "reserved_quantity" not in donation_columns:
            db.execute(
                "ALTER TABLE donations ADD COLUMN reserved_quantity REAL NOT NULL DEFAULT 0 "
                "CHECK (reserved_quantity >= 0)"
            )

        db.execute(
            """CREATE TABLE food_requests_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                requester_id INTEGER NOT NULL REFERENCES users(id),
                category TEXT NOT NULL,
                quantity REAL NOT NULL CHECK (quantity > 0),
                unit TEXT NOT NULL,
                urgency TEXT NOT NULL CHECK (urgency IN ('low', 'medium', 'high')),
                location TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('open', 'reserved', 'collected', 'cancelled', 'completed')),
                created_at TEXT NOT NULL
            )"""
        )
        db.execute(
            """INSERT INTO food_requests_new
               (id, requester_id, category, quantity, unit, urgency, location, status, created_at)
               SELECT r.id, r.requester_id, r.category, r.quantity, r.unit, r.urgency, r.location,
                      CASE WHEN EXISTS
                          (SELECT 1 FROM allocations a WHERE a.request_id=r.id)
                           THEN 'reserved' ELSE r.status END,
                      r.created_at
               FROM food_requests r"""
        )
        db.execute(
            """CREATE TABLE allocations_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                donation_id INTEGER NOT NULL REFERENCES donations(id),
                request_id INTEGER NOT NULL REFERENCES food_requests_new(id),
                quantity REAL NOT NULL CHECK (quantity > 0),
                compatibility_score REAL NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('reserved', 'collected', 'cancelled')),
                reserved_at TEXT NOT NULL,
                collected_at TEXT,
                collected_by INTEGER REFERENCES users(id),
                cancelled_at TEXT,
                cancelled_by INTEGER REFERENCES users(id),
                cancellation_reason TEXT
            )"""
        )
        db.execute(
            """INSERT INTO allocations_new
               (id, donation_id, request_id, quantity, compatibility_score, created_at,
                status, reserved_at)
               SELECT id, donation_id, request_id, quantity, compatibility_score, created_at,
                      'reserved', created_at
               FROM allocations"""
        )
        db.execute("DROP TABLE allocations")
        db.execute("DROP TABLE food_requests")
        db.execute("ALTER TABLE food_requests_new RENAME TO food_requests")
        db.execute("ALTER TABLE allocations_new RENAME TO allocations")
        db.execute(
            """CREATE UNIQUE INDEX uq_allocations_active_request
               ON allocations(request_id) WHERE status IN ('reserved', 'collected')"""
        )
        db.execute("CREATE INDEX idx_allocations_donation ON allocations(donation_id)")
        db.execute(
            """UPDATE donations
               SET reserved_quantity = COALESCE(
                   (SELECT SUM(a.quantity) FROM allocations a
                    WHERE a.donation_id=donations.id AND a.status='reserved'), 0)"""
        )
        db.execute(
            """UPDATE donations SET status='available'
               WHERE status='completed' AND reserved_quantity > 0"""
        )
        invalid_inventory = db.execute(
            "SELECT id FROM donations WHERE remaining_quantity+reserved_quantity>quantity+0.000000001 LIMIT 1"
        ).fetchone()
        if invalid_inventory:
            raise RuntimeError("Database migration stopped: donation inventory exceeds its original quantity")
        db.execute(
            """CREATE TRIGGER IF NOT EXISTS trg_donation_inventory_insert
               BEFORE INSERT ON donations
               WHEN NEW.remaining_quantity + NEW.reserved_quantity > NEW.quantity + 0.000000001
               BEGIN SELECT RAISE(ABORT, 'Donation inventory exceeds original quantity'); END"""
        )
        db.execute(
            """CREATE TRIGGER IF NOT EXISTS trg_donation_inventory_update
               BEFORE UPDATE OF quantity, remaining_quantity, reserved_quantity ON donations
               WHEN NEW.remaining_quantity + NEW.reserved_quantity > NEW.quantity + 0.000000001
               BEGIN SELECT RAISE(ABORT, 'Donation inventory exceeds original quantity'); END"""
        )
        db.execute("PRAGMA user_version = 1")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute("PRAGMA foreign_keys = ON")

    violations = db.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError("Database migration produced foreign-key violations")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(
        DATABASE=os.environ.get("FOODSHARE_DATABASE", str(ROOT / "instance" / "foodshare.sqlite3")),
        SECRET_KEY=os.environ.get("FOODSHARE_SECRET_KEY", "local-demo-key-change-before-deployment"),
        ENVIRONMENT=os.environ.get("FOODSHARE_ENV", "development"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("FOODSHARE_ENV") == "production",
        ADMIN_EMAILS={
            email.strip().casefold()
            for email in os.environ.get("FOODSHARE_ADMIN_EMAILS", "").split(",")
            if email.strip()
        },
        MAX_CONTENT_LENGTH=32 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    if app.config["ENVIRONMENT"] == "production" and app.config["SECRET_KEY"] == "local-demo-key-change-before-deployment":
        raise RuntimeError("Set FOODSHARE_SECRET_KEY before running in production")

    @app.errorhandler(413)
    def request_too_large(_error: Exception):
        return jsonify(error="Request is too large"), 413

    @app.errorhandler(404)
    def not_found(_error: Exception):
        if request.path.startswith("/api/"):
            return jsonify(error="API route not found"), 404
        return send_from_directory(ROOT, "index.html")

    @app.errorhandler(500)
    def internal_error(_error: Exception):
        app.logger.exception("Unhandled application error")
        return jsonify(error="An unexpected server error occurred"), 500

    @app.before_request
    def protect_mutations_with_csrf():
        if request.method in {"POST", "PATCH", "DELETE"} and request.path.startswith("/api/"):
            expected = session.get("csrf_token")
            supplied = request.headers.get("X-CSRF-Token")
            if not expected or not supplied or not secrets.compare_digest(expected, supplied):
                return jsonify(error="Security token missing or invalid. Refresh and try again."), 400
        return None

    def login_required(function: Callable):
        @wraps(function)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                return jsonify(error="Please log in to continue"), 401
            return function(*args, **kwargs)

        return wrapped

    def roles_required(*roles: str):
        def decorator(function: Callable):
            @wraps(function)
            @login_required
            def wrapped(*args, **kwargs):
                if session.get("role") not in roles:
                    return jsonify(error="You are not allowed to perform this action"), 403
                return function(*args, **kwargs)

            return wrapped

        return decorator

    def json_body() -> dict[str, Any] | None:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else None

    def text_field(data: dict[str, Any], name: str, label: str, maximum: int = 180) -> str | None:
        value = data.get(name)
        if not isinstance(value, str) or not value.strip():
            return f"{label} is required"
        if len(value.strip()) > maximum:
            return f"{label} must be {maximum} characters or fewer"
        return None

    def numeric_field(data: dict[str, Any], name: str, label: str) -> tuple[float | None, str | None]:
        value = data.get(name)
        if isinstance(value, bool):
            return None, f"{label} must be a positive number"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None, f"{label} must be a positive number"
        if not (0 < number < 1_000_000):
            return None, f"{label} must be greater than 0 and less than 1,000,000"
        return number, None

    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            path = Path(app.config["DATABASE"])
            path.parent.mkdir(parents=True, exist_ok=True)
            g.db = sqlite3.connect(path, timeout=10)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
            g.db.execute("PRAGMA busy_timeout = 10000")
        return g.db

    @app.teardown_appcontext
    def close_db(_error: Exception | None = None) -> None:
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def init_db() -> None:
        db = get_db()
        db.executescript(SCHEMA)
        db.commit()
        migrate_database(db)
        migrate_database(db)

    app.extensions["foodshare_init_db"] = init_db
    init_on_request = bool(app.config.get("INITIALIZE_DATABASE_ON_FIRST_REQUEST", False))
    initialization_lock = threading.Lock()
    initialized = not init_on_request

    if not init_on_request:
        with app.app_context():
            init_db()

    @app.before_request
    def initialize_database_if_needed():
        nonlocal initialized
        if initialized:
            return None
        with initialization_lock:
            if not initialized:
                init_db()
                initialized = True
        return None

    def current_user() -> dict[str, Any] | None:
        user_id = session.get("user_id")
        if not user_id:
            return None
        row = get_db().execute(
            "SELECT id, name, email, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None

    def donation_record(row: sqlite3.Row, *, include_contact: bool = False) -> dict[str, Any]:
        result = dict(row)
        result["food_safe"] = bool(result["food_safe"])
        result["quantity_available"] = result.pop("remaining_quantity")
        result["quantity_reserved"] = result.get("reserved_quantity", 0)
        try:
            expiry = datetime.fromisoformat(result["expires_at"].replace("Z", "+00:00"))
            is_expired = expiry.tzinfo is None or expiry.astimezone(timezone.utc) <= datetime.now(timezone.utc)
        except (TypeError, ValueError):
            is_expired = True
        if is_expired:
            lifecycle = "expired"
        elif result["status"] == "unavailable":
            lifecycle = "unavailable"
        elif result["status"] == "completed":
            lifecycle = "collected"
        elif result["quantity_available"] > 0 and result["quantity_reserved"] > 0:
            lifecycle = "partially_reserved"
        elif result["quantity_available"] > 0:
            lifecycle = "available"
        elif result["quantity_reserved"] > 0:
            lifecycle = "reserved"
        else:
            lifecycle = "available"
        result["lifecycle_status"] = lifecycle
        if not include_contact:
            result.pop("donor_contact", None)
            result.pop("donor_id", None)
        return result

    def request_record(row: sqlite3.Row, *, include_contact: bool = False) -> dict[str, Any]:
        result = dict(row)
        keys = set(row.keys())
        allocation_id = result.pop("allocation_id", None) if "allocation_id" in keys else None
        allocation_fields = (
            "allocation_donation_id", "allocation_food_name", "allocation_quantity",
            "allocation_unit", "allocation_status", "allocation_reserved_at",
            "allocation_collected_at",
        )
        if allocation_id is not None:
            result["allocation"] = {
                "id": allocation_id,
                "donation_id": result.pop("allocation_donation_id"),
                "food_name": result.pop("allocation_food_name"),
                "quantity": result.pop("allocation_quantity"),
                "unit": result.pop("allocation_unit"),
                "status": result.pop("allocation_status"),
                "reserved_at": result.pop("allocation_reserved_at"),
                "collected_at": result.pop("allocation_collected_at"),
            }
        else:
            result["allocation"] = None
            for field in allocation_fields:
                result.pop(field, None)
        if not include_contact:
            result.pop("requester_id", None)
            result.pop("requester_contact", None)
        return result

    def select_donations(*, include_all: bool = False) -> list[dict[str, Any]]:
        db = get_db()
        if include_all:
            rows = db.execute(
                "SELECT d.*, u.name AS donor_name FROM donations d JOIN users u ON u.id=d.donor_id ORDER BY d.created_at DESC"
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT d.*, u.name AS donor_name FROM donations d JOIN users u ON u.id=d.donor_id WHERE d.status='available' AND d.remaining_quantity > 0 AND d.expires_at > ? ORDER BY d.created_at DESC",
                (utc_now(),),
            ).fetchall()
        return [donation_record(row, include_contact=include_all) for row in rows]

    @app.get("/")
    def homepage():
        return send_from_directory(ROOT, "index.html")

    @app.get("/<path:asset>")
    def frontend_asset(asset: str):
        if asset in {"index.html", "script.js", "style.css"}:
            return send_from_directory(ROOT, asset)
        return jsonify(error="Not found"), 404

    @app.get("/favicon.ico")
    def favicon():
        return "", 204

    @app.get("/api/csrf")
    def csrf_token():
        session.setdefault("csrf_token", secrets.token_urlsafe(32))
        return jsonify(csrf_token=session["csrf_token"])

    @app.get("/api/session")
    def session_info():
        return jsonify(user=current_user())

    @app.post("/api/register")
    def register():
        data = json_body()
        if data is None:
            return jsonify(error="Send registration details as JSON"), 400
        for field, label, maximum in (("name", "Name", 100), ("email", "Email", 254)):
            error = text_field(data, field, label, maximum)
            if error:
                return jsonify(error=error), 400
        email = data["email"].strip().casefold()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            return jsonify(error="Enter a valid email address"), 400
        password = data.get("password")
        if not isinstance(password, str) or len(password) < 8 or len(password) > 128:
            return jsonify(error="Password must be between 8 and 128 characters"), 400
        role = data.get("role")
        if role not in {"donor", "recipient"}:
            return jsonify(error="Choose donor or recipient account type"), 400
        if email in app.config["ADMIN_EMAILS"]:
            role = "admin"
        db = get_db()
        try:
            cursor = db.execute(
                "INSERT INTO users (name,email,password_hash,role,created_at) VALUES (?,?,?,?,?)",
                (data["name"].strip(), email, generate_password_hash(password), role, utc_now()),
            )
            db.commit()
        except sqlite3.IntegrityError:
            return jsonify(error="An account with this email already exists"), 409
        session.clear()
        session["user_id"] = cursor.lastrowid
        session["role"] = role
        session["csrf_token"] = secrets.token_urlsafe(32)
        return jsonify(user=current_user()), 201

    @app.post("/api/login")
    def login():
        data = json_body()
        if data is None or not isinstance(data.get("email"), str) or not isinstance(data.get("password"), str):
            return jsonify(error="Email and password are required"), 400
        user = get_db().execute(
            "SELECT id, email, password_hash, role FROM users WHERE email = ? COLLATE NOCASE",
            (data["email"].strip(),),
        ).fetchone()
        if user is None or not check_password_hash(user["password_hash"], data["password"]):
            return jsonify(error="Email or password is incorrect"), 401
        session.clear()
        session["user_id"] = user["id"]
        session["role"] = user["role"]
        session["csrf_token"] = secrets.token_urlsafe(32)
        return jsonify(user=current_user())

    @app.post("/api/logout")
    @login_required
    def logout():
        session.clear()
        return jsonify(message="You are signed out")

    @app.get("/api/donations")
    def list_donations():
        query = request.args.get("q", "").strip()[:100]
        category = request.args.get("category", "").strip()[:80]
        status = request.args.get("status", "available").strip().casefold()
        db = get_db()
        params: list[Any] = []
        conditions: list[str] = []
        user = current_user()
        if status == "all":
            if not user or user["role"] != "admin":
                return jsonify(error="Only administrators can view all statuses"), 403
        else:
            if status not in {"available", "completed", "unavailable"}:
                return jsonify(error="Unknown donation status filter"), 400
            conditions.append("d.status = ?")
            params.append(status)
            if status == "available":
                conditions.append("d.remaining_quantity > 0")
                conditions.append("julianday(d.expires_at) > julianday(?)")
                params.append(utc_now())
        if query:
            conditions.append("d.food_name LIKE ? ESCAPE '\\'")
            params.append("%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
        if category:
            conditions.append("d.category = ? COLLATE NOCASE")
            params.append(category)
        rows = db.execute(
            "SELECT d.*, u.name AS donor_name FROM donations d JOIN users u ON u.id=d.donor_id"
            + (" WHERE " + " AND ".join(conditions) if conditions else "")
            + " ORDER BY d.created_at DESC",
            params,
        ).fetchall()
        return jsonify(donations=[donation_record(row) for row in rows])

    @app.post("/api/donations")
    @roles_required("donor", "admin")
    def create_donation():
        data = json_body()
        if data is None:
            return jsonify(error="Send donation details as JSON"), 400
        required = {
            "food_name": ("Food name", 120), "category": ("Category", 80),
            "unit": ("Unit", 30), "prepared_at": ("Preparation time", 40),
            "expires_at": ("Best-before time", 40), "location": ("Pickup location", 160),
            "storage_info": ("Storage information", 300),
            "condition_info": ("Food condition", 300),
        }
        for field, (label, maximum) in required.items():
            error = text_field(data, field, label, maximum)
            if error:
                return jsonify(error=error), 400
        quantity, error = numeric_field(data, "quantity", "Quantity")
        if error:
            return jsonify(error=error), 400
        prepared = data["prepared_at"].strip()
        try:
            prepared_date = datetime.fromisoformat(prepared.replace("Z", "+00:00"))
        except ValueError:
            return jsonify(error="Preparation time must be an ISO date/time"), 400
        if prepared_date.tzinfo is None:
            return jsonify(error="Preparation time must include a timezone"), 400
        if prepared_date.astimezone(timezone.utc) > datetime.now(timezone.utc):
            return jsonify(error="Preparation time cannot be in the future"), 400
        prepared = prepared_date.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        expires = data["expires_at"].strip()
        try:
            expiry_date = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        except ValueError:
            return jsonify(error="Best-before time must be an ISO date/time"), 400
        if expiry_date.tzinfo is None:
            return jsonify(error="Best-before time must include a timezone"), 400
        if expiry_date.astimezone(timezone.utc) <= datetime.now(timezone.utc):
            return jsonify(error="Food must not be expired when listed"), 400
        expires = expiry_date.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        if data.get("food_safe") is not True:
            return jsonify(error="Only food confirmed safe for sharing can be listed"), 400
        user = current_user()
        contact = data.get("donor_contact")
        if contact is None or (isinstance(contact, str) and not contact.strip()):
            contact = user["email"]
        if not isinstance(contact, str) or not contact.strip() or len(contact) > 160:
            return jsonify(error="A valid donor contact is required"), 400
        db = get_db()
        cursor = db.execute(
            "INSERT INTO donations (donor_id,food_name,category,quantity,remaining_quantity,unit,prepared_at,expires_at,location,storage_info,condition_info,donor_contact,food_safe,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (user["id"], data["food_name"].strip(), data["category"].strip(), quantity,
             quantity, data["unit"].strip(), prepared, expires,
             data["location"].strip(), data["storage_info"].strip(),
             data["condition_info"].strip(), contact.strip(), 1, "available", utc_now()),
        )
        db.commit()
        saved = db.execute("SELECT * FROM donations WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return jsonify(donation=donation_record(saved, include_contact=True)), 201

    @app.get("/api/my/donations")
    @roles_required("donor", "admin")
    def my_donations():
        user = current_user()
        rows = get_db().execute(
            "SELECT * FROM donations WHERE donor_id=? ORDER BY created_at DESC",
            (user["id"],),
        ).fetchall()
        return jsonify(donations=[donation_record(row, include_contact=True) for row in rows])

    @app.patch("/api/donations/<int:donation_id>/status")
    @roles_required("donor", "admin")
    def update_donation_status(donation_id: int):
        data = json_body()
        status = data.get("status") if data else None
        if status not in {"available", "unavailable"}:
            return jsonify(error="Status must be available or unavailable"), 400
        user = current_user()
        db = get_db()
        donation = db.execute("SELECT * FROM donations WHERE id = ?", (donation_id,)).fetchone()
        if donation is None:
            return jsonify(error="Donation not found"), 404
        if user["role"] != "admin" and donation["donor_id"] != user["id"]:
            return jsonify(error="You can only change your own donation"), 403
        if donation["status"] == "completed":
            return jsonify(error="Completed donations cannot be reopened"), 409
        if status == "available":
            try:
                expiry = datetime.fromisoformat(donation["expires_at"].replace("Z", "+00:00"))
            except ValueError:
                return jsonify(error="This donation has an invalid expiry and cannot be made available"), 409
            if expiry.tzinfo is None or expiry.astimezone(timezone.utc) <= datetime.now(timezone.utc):
                return jsonify(error="Expired food cannot be made available again"), 409
        db.execute("UPDATE donations SET status = ? WHERE id = ?", (status, donation_id))
        db.commit()
        return jsonify(message="Donation status updated", donation_id=donation_id, status=status)

    @app.get("/api/requests")
    @login_required
    def list_requests():
        user = current_user()
        if user["role"] == "admin":
            rows = get_db().execute(
                "SELECT r.*, u.name AS requester_name, u.email AS requester_contact, "
                "a.id AS allocation_id, a.donation_id AS allocation_donation_id, "
                "d.food_name AS allocation_food_name, a.quantity AS allocation_quantity, "
                "d.unit AS allocation_unit, a.status AS allocation_status, "
                "a.reserved_at AS allocation_reserved_at, a.collected_at AS allocation_collected_at "
                "FROM food_requests r JOIN users u ON u.id=r.requester_id "
                "LEFT JOIN allocations a ON a.id=(SELECT ax.id FROM allocations ax WHERE ax.request_id=r.id ORDER BY ax.id DESC LIMIT 1) "
                "LEFT JOIN donations d ON d.id=a.donation_id ORDER BY r.created_at DESC"
            ).fetchall()
        else:
            rows = get_db().execute(
                "SELECT r.*, u.name AS requester_name, a.id AS allocation_id, "
                "a.donation_id AS allocation_donation_id, d.food_name AS allocation_food_name, "
                "a.quantity AS allocation_quantity, d.unit AS allocation_unit, "
                "a.status AS allocation_status, a.reserved_at AS allocation_reserved_at, "
                "a.collected_at AS allocation_collected_at "
                "FROM food_requests r JOIN users u ON u.id=r.requester_id "
                "LEFT JOIN allocations a ON a.id=(SELECT ax.id FROM allocations ax WHERE ax.request_id=r.id ORDER BY ax.id DESC LIMIT 1) "
                "LEFT JOIN donations d ON d.id=a.donation_id WHERE r.requester_id=? ORDER BY r.created_at DESC",
                (user["id"],),
            ).fetchall()
        return jsonify(requests=[request_record(row, include_contact=user["role"] == "admin") for row in rows])

    @app.post("/api/requests")
    @roles_required("recipient", "admin")
    def create_request():
        data = json_body()
        if data is None:
            return jsonify(error="Send request details as JSON"), 400
        for field, label, maximum in (("category", "Category", 80), ("unit", "Unit", 30), ("location", "Pickup location", 160)):
            error = text_field(data, field, label, maximum)
            if error:
                return jsonify(error=error), 400
        quantity, error = numeric_field(data, "quantity", "Requested quantity")
        if error:
            return jsonify(error=error), 400
        urgency = data.get("urgency")
        if urgency not in {"low", "medium", "high"}:
            return jsonify(error="Choose low, medium, or high urgency"), 400
        user = current_user()
        db = get_db()
        cursor = db.execute(
            "INSERT INTO food_requests (requester_id,category,quantity,unit,urgency,location,status,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (user["id"], data["category"].strip(), quantity, data["unit"].strip(), urgency,
             data["location"].strip(), "open", utc_now()),
        )
        db.commit()
        row = db.execute("SELECT * FROM food_requests WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return jsonify(food_request=request_record(row)), 201

    @app.get("/api/matches")
    @login_required
    def get_matches():
        user = current_user()
        request_id = request.args.get("request_id", type=int)
        db = get_db()
        if request_id is not None:
            food_request = db.execute("SELECT * FROM food_requests WHERE id = ?", (request_id,)).fetchone()
            if food_request is None:
                return jsonify(error="Request not found"), 404
            if user["role"] not in {"admin", "recipient"} or (
                user["role"] == "recipient" and food_request["requester_id"] != user["id"]
            ):
                return jsonify(error="You can only view matches for your own request"), 403
            request_rows = [food_request]
            donation_query = "SELECT * FROM donations"
            donation_params: tuple[Any, ...] = ()
            if user["role"] == "donor":
                return jsonify(error="Donor accounts should request matches for their own donations"), 403
        elif user["role"] in {"donor", "admin"}:
            request_rows = db.execute(
                "SELECT * FROM food_requests WHERE status='open' ORDER BY created_at"
            ).fetchall()
            donation_query = "SELECT * FROM donations WHERE 1=1"
            donation_params = ()
            if user["role"] == "donor":
                donation_query += " AND donor_id=?"
                donation_params = (user["id"],)
        else:
            return jsonify(error="A request_id is required for recipient accounts"), 400
        donation_rows = db.execute(donation_query + " ORDER BY created_at DESC", donation_params).fetchall()
        donations = []
        for row in donation_rows:
            entry = donation_record(row, include_contact=True)
            entry["quantity"] = entry["quantity_available"]
            donations.append(entry)
        request_data = [dict(row) for row in request_rows]
        recommendations = recommend(donations, request_data)
        diagnostics = evaluate_candidates(donations, request_data)
        return jsonify(
            recommendations=[candidate.as_dict() for candidate in recommendations],
            rejected_candidate_count=sum(not candidate.compatible for candidate in diagnostics),
            rejected_candidates=[
                {
                    "donation_id": candidate.donation_id,
                    "request_id": candidate.request_id,
                    "rejected_constraints": list(candidate.rejected_constraints),
                }
                for candidate in diagnostics
                if not candidate.compatible
            ],
            message="No safe, available donation satisfies this request" if not recommendations else None,
        )

    @app.post("/api/matches/<int:donation_id>/<int:request_id>/accept")
    @roles_required("donor", "admin")
    def accept_match(donation_id: int, request_id: int):
        user = current_user()
        db = get_db()
        try:
            db.execute("BEGIN IMMEDIATE")
            donation = db.execute("SELECT * FROM donations WHERE id = ?", (donation_id,)).fetchone()
            food_request = db.execute("SELECT * FROM food_requests WHERE id = ?", (request_id,)).fetchone()
            if donation is None or food_request is None:
                db.rollback()
                return jsonify(error="Donation or request not found"), 404
            if user["role"] != "admin" and donation["donor_id"] != user["id"]:
                db.rollback()
                return jsonify(error="Only the donation owner or an administrator can accept this match"), 403
            donation_data = donation_record(donation, include_contact=True)
            donation_data["quantity"] = donation_data["quantity_available"]
            candidate = recommend([donation_data], [dict(food_request)])
            if not candidate:
                db.rollback()
                return jsonify(error="This pair no longer satisfies the safety, status, category, or quantity rules"), 409
            selected = candidate[0]
            quantity = float(food_request["quantity"])
            remaining = float(donation["remaining_quantity"]) - quantity
            reserved_at = utc_now()
            inventory_update = db.execute(
                "UPDATE donations SET remaining_quantity=remaining_quantity-?, "
                "reserved_quantity=reserved_quantity+? "
                "WHERE id=? AND status='available' AND remaining_quantity>=? "
                "AND julianday(expires_at)>julianday(?) "
                "AND remaining_quantity+reserved_quantity<=quantity+0.000000001",
                (quantity, quantity, donation_id, quantity, reserved_at),
            )
            if inventory_update.rowcount != 1:
                db.rollback()
                return jsonify(error="Donation inventory or availability changed. Refresh matches."), 409
            db.execute(
                "INSERT INTO allocations "
                "(donation_id,request_id,quantity,compatibility_score,created_at,status,reserved_at) "
                "VALUES (?,?,?,?,?,'reserved',?)",
                (donation_id, request_id, quantity, selected.score, reserved_at, reserved_at),
            )
            request_update = db.execute(
                "UPDATE food_requests SET status='reserved' WHERE id=? AND status='open'",
                (request_id,),
            )
            if request_update.rowcount != 1:
                db.rollback()
                return jsonify(error="Request is no longer open"), 409
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            return jsonify(error="This request was already allocated or inventory changed. Refresh the matches."), 409
        return jsonify(
            message="Match accepted and quantity reserved",
            allocation={
                "id": db.execute(
                    "SELECT id FROM allocations WHERE request_id=? AND status='reserved'",
                    (request_id,),
                ).fetchone()[0],
                "donation_id": donation_id,
                "request_id": request_id,
                "quantity": quantity,
                "compatibility_score": selected.score,
                "status": "reserved",
            },
        ), 201

    @app.post("/api/allocations/<int:allocation_id>/collect")
    @roles_required("recipient", "admin")
    def confirm_collection(allocation_id: int):
        user = current_user()
        db = get_db()
        try:
            db.execute("BEGIN IMMEDIATE")
            allocation = db.execute(
                "SELECT a.*, r.requester_id, r.status AS request_status, d.expires_at "
                "FROM allocations a JOIN food_requests r ON r.id=a.request_id "
                "JOIN donations d ON d.id=a.donation_id WHERE a.id=?",
                (allocation_id,),
            ).fetchone()
            if allocation is None:
                db.rollback()
                return jsonify(error="Reservation not found"), 404
            if user["role"] != "admin" and allocation["requester_id"] != user["id"]:
                db.rollback()
                return jsonify(error="Only the requesting recipient or an administrator can confirm collection"), 403
            if allocation["status"] != "reserved" or allocation["request_status"] != "reserved":
                db.rollback()
                return jsonify(error="Only an active reservation can be confirmed as collected"), 409
            try:
                expiry = datetime.fromisoformat(allocation["expires_at"].replace("Z", "+00:00"))
            except (TypeError, ValueError):
                db.rollback()
                return jsonify(error="This reservation has an invalid expiry and cannot be confirmed collected"), 409
            if expiry.tzinfo is None or expiry.astimezone(timezone.utc) <= datetime.now(timezone.utc):
                db.rollback()
                return jsonify(error="This reservation has expired. Cancel it instead of confirming collection."), 409
            collected_at = utc_now()
            stock_update = db.execute(
                "UPDATE donations SET reserved_quantity=reserved_quantity-?, "
                "status=CASE WHEN status='unavailable' THEN status "
                "WHEN remaining_quantity<=0.000000001 AND reserved_quantity-?<=0.000000001 "
                "THEN 'completed' ELSE status END "
                "WHERE id=? AND reserved_quantity>=?",
                (allocation["quantity"], allocation["quantity"], allocation["donation_id"], allocation["quantity"]),
            )
            if stock_update.rowcount != 1:
                db.rollback()
                return jsonify(error="Reserved inventory changed. Refresh the request status."), 409
            allocation_update = db.execute(
                "UPDATE allocations SET status='collected', collected_at=?, collected_by=? "
                "WHERE id=? AND status='reserved'",
                (collected_at, user["id"], allocation_id),
            )
            request_update = db.execute(
                "UPDATE food_requests SET status='collected' WHERE id=? AND status='reserved'",
                (allocation["request_id"],),
            )
            if allocation_update.rowcount != 1 or request_update.rowcount != 1:
                db.rollback()
                return jsonify(error="Reservation status changed. Refresh and try again."), 409
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            return jsonify(error="Collection status could not be saved"), 409
        return jsonify(
            message="Collection confirmed by the recipient",
            allocation={"id": allocation_id, "status": "collected", "collected_at": collected_at},
        )

    @app.post("/api/requests/<int:request_id>/cancel")
    @roles_required("recipient", "admin")
    def cancel_request(request_id: int):
        data = json_body() or {}
        reason = data.get("reason", "")
        if not isinstance(reason, str) or len(reason) > 240:
            return jsonify(error="Cancellation reason must be 240 characters or fewer"), 400
        user = current_user()
        db = get_db()
        try:
            db.execute("BEGIN IMMEDIATE")
            food_request = db.execute(
                "SELECT id, requester_id, status FROM food_requests WHERE id=?", (request_id,)
            ).fetchone()
            if food_request is None:
                db.rollback()
                return jsonify(error="Request not found"), 404
            if user["role"] != "admin" and food_request["requester_id"] != user["id"]:
                db.rollback()
                return jsonify(error="You can only cancel your own request"), 403
            if food_request["status"] not in {"open", "reserved"}:
                db.rollback()
                return jsonify(error="Only open or reserved requests can be cancelled"), 409

            if food_request["status"] == "reserved":
                allocation = db.execute(
                    "SELECT * FROM allocations WHERE request_id=? AND status='reserved'",
                    (request_id,),
                ).fetchone()
                if allocation is None:
                    db.rollback()
                    return jsonify(error="Reserved request has no active allocation"), 409
                stock_update = db.execute(
                    "UPDATE donations SET remaining_quantity=remaining_quantity+?, "
                    "reserved_quantity=reserved_quantity-? "
                    "WHERE id=? AND reserved_quantity>=? "
                    "AND remaining_quantity+reserved_quantity<=quantity+0.000000001",
                    (allocation["quantity"], allocation["quantity"], allocation["donation_id"], allocation["quantity"]),
                )
                if stock_update.rowcount != 1:
                    db.rollback()
                    return jsonify(error="Inventory limits would be exceeded; reservation was not cancelled"), 409
                allocation_update = db.execute(
                    "UPDATE allocations SET status='cancelled', cancelled_at=?, cancelled_by=?, cancellation_reason=? "
                    "WHERE id=? AND status='reserved'",
                    (utc_now(), user["id"], reason.strip() or None, allocation["id"]),
                )
                if allocation_update.rowcount != 1:
                    db.rollback()
                    return jsonify(error="Reservation status changed. Refresh and try again."), 409

            request_update = db.execute(
                "UPDATE food_requests SET status='cancelled' WHERE id=? AND status IN ('open','reserved')",
                (request_id,),
            )
            if request_update.rowcount != 1:
                db.rollback()
                return jsonify(error="Request status changed. Refresh and try again."), 409
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            return jsonify(error="Cancellation could not be saved"), 409
        return jsonify(message="Request cancelled; any reserved quantity was returned safely", request_id=request_id)

    @app.get("/api/dashboard")
    @roles_required("admin")
    def dashboard():
        db = get_db()
        counts = db.execute(
            "SELECT COUNT(*) AS total_donations, "
            "SUM(CASE WHEN status='available' AND remaining_quantity>0 AND julianday(expires_at)>julianday(?) THEN 1 ELSE 0 END) AS available_donations, "
            "SUM(CASE WHEN reserved_quantity>0 THEN 1 ELSE 0 END) AS reserved_donations, "
            "SUM(CASE WHEN julianday(expires_at)<=julianday(?) AND remaining_quantity+reserved_quantity>0 THEN 1 ELSE 0 END) AS expired_donations, "
            "SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed_donations "
            "FROM donations",
            (utc_now(), utc_now()),
        ).fetchone()
        request_counts = db.execute(
            "SELECT SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) AS open_requests, "
            "SUM(CASE WHEN status='reserved' THEN 1 ELSE 0 END) AS reserved_requests, "
            "SUM(CASE WHEN status='collected' THEN 1 ELSE 0 END) AS collected_requests, "
            "SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) AS cancelled_requests, "
            "SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS legacy_completed_requests "
            "FROM food_requests"
        ).fetchone()
        allocation_counts = db.execute(
            "SELECT SUM(CASE WHEN status='reserved' THEN 1 ELSE 0 END) AS reserved_allocations, "
            "SUM(CASE WHEN status='collected' THEN 1 ELSE 0 END) AS collected_allocations, "
            "SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) AS cancelled_allocations "
            "FROM allocations"
        ).fetchone()

        def quantities_by_unit(sql: str, params: tuple[Any, ...] = ()) -> dict[str, float]:
            return {
                row["unit"]: row["quantity"]
                for row in db.execute(sql, params).fetchall()
            }

        quantity_available = quantities_by_unit(
            "SELECT unit, SUM(remaining_quantity) AS quantity FROM donations "
            "WHERE status='available' AND remaining_quantity>0 AND julianday(expires_at)>julianday(?) GROUP BY unit",
            (utc_now(),),
        )
        quantity_reserved = quantities_by_unit(
            "SELECT d.unit, SUM(a.quantity) AS quantity FROM allocations a "
            "JOIN donations d ON d.id=a.donation_id WHERE a.status='reserved' GROUP BY d.unit"
        )
        quantity_collected = quantities_by_unit(
            "SELECT d.unit, SUM(a.quantity) AS quantity FROM allocations a "
            "JOIN donations d ON d.id=a.donation_id WHERE a.status='collected' GROUP BY d.unit"
        )
        quantity_cancelled = quantities_by_unit(
            "SELECT d.unit, SUM(a.quantity) AS quantity FROM allocations a "
            "JOIN donations d ON d.id=a.donation_id WHERE a.status='cancelled' GROUP BY d.unit"
        )
        quantity_expired_available = quantities_by_unit(
            "SELECT unit, SUM(remaining_quantity) AS quantity FROM donations "
            "WHERE julianday(expires_at)<=julianday(?) AND remaining_quantity>0 GROUP BY unit",
            (utc_now(),),
        )
        quantity_expired_reserved = quantities_by_unit(
            "SELECT unit, SUM(reserved_quantity) AS quantity FROM donations "
            "WHERE julianday(expires_at)<=julianday(?) AND reserved_quantity>0 GROUP BY unit",
            (utc_now(),),
        )
        recent_donations = db.execute(
            "SELECT d.id,d.food_name,d.category,d.quantity,d.unit,d.status,d.created_at,u.name AS donor_name FROM donations d JOIN users u ON u.id=d.donor_id ORDER BY d.created_at DESC LIMIT 8"
        ).fetchall()
        recent_requests = db.execute(
            "SELECT r.id,r.category,r.quantity,r.unit,r.status,r.created_at,u.name AS requester_name FROM food_requests r JOIN users u ON u.id=r.requester_id ORDER BY r.created_at DESC LIMIT 8"
        ).fetchall()
        return jsonify(
            statistics={
                "total_donations": counts["total_donations"] or 0,
                "available_donations": counts["available_donations"] or 0,
                "reserved_donations": counts["reserved_donations"] or 0,
                "expired_donations": counts["expired_donations"] or 0,
                "completed_donations": counts["completed_donations"] or 0,
                "open_requests": request_counts["open_requests"] or 0,
                "reserved_requests": request_counts["reserved_requests"] or 0,
                "collected_requests": request_counts["collected_requests"] or 0,
                "cancelled_requests": request_counts["cancelled_requests"] or 0,
                "legacy_completed_requests": request_counts["legacy_completed_requests"] or 0,
                "reserved_allocations": allocation_counts["reserved_allocations"] or 0,
                "collected_allocations": allocation_counts["collected_allocations"] or 0,
                "cancelled_allocations": allocation_counts["cancelled_allocations"] or 0,
                "quantity_available_by_unit": quantity_available,
                "quantity_reserved_by_unit": quantity_reserved,
                "quantity_collected_by_unit": quantity_collected,
                "quantity_cancelled_by_unit": quantity_cancelled,
                "quantity_expired_available_by_unit": quantity_expired_available,
                "quantity_expired_reserved_by_unit": quantity_expired_reserved,
            },
            recent_donations=[dict(row) for row in recent_donations],
            recent_requests=[dict(row) for row in recent_requests],
            note="Counts use saved application records. Only recipient-confirmed collected quantities are reported as collected; these counts are not independently verified environmental impact.",
        )

    return app


app = create_app({"INITIALIZE_DATABASE_ON_FIRST_REQUEST": True})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)