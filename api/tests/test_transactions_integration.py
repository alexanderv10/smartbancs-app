from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.main import DATABASE_URL, app


TEST_SCHEMA = os.getenv("TEST_DB_SCHEMA", "test_smartbancs")


@pytest.fixture(autouse=True)
def reset_database():
    pgoptions = os.getenv("PGOPTIONS", "")
    if os.getenv("APP_ENV") != "test" or TEST_SCHEMA not in pgoptions:
        pytest.fail(
            "Integration tests require APP_ENV=test and PGOPTIONS pointing to the isolated test schema."
        )

    with psycopg.connect(DATABASE_URL) as conn:
        conn.autocommit = True
        conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {TEST_SCHEMA}")

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.transaction():
            conn.execute(f"SET search_path TO {TEST_SCHEMA}, public")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id BIGSERIAL PRIMARY KEY,
                    account_number VARCHAR(32) UNIQUE NOT NULL,
                    owner_name VARCHAR(120) NOT NULL,
                    balance NUMERIC(14, 2) NOT NULL CHECK (balance >= 0),
                    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    from_account_id BIGINT NOT NULL REFERENCES accounts(id),
                    to_account_id BIGINT NOT NULL REFERENCES accounts(id),
                    amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
                    status VARCHAR(20) NOT NULL,
                    failure_reason TEXT,
                    trace_id UUID NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );

                CREATE TABLE IF NOT EXISTS outbox_events (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    transaction_id UUID NOT NULL REFERENCES transactions(id),
                    event_type VARCHAR(80) NOT NULL,
                    payload JSONB NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
                    attempts INT NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    processed_at TIMESTAMPTZ
                );

                CREATE TABLE IF NOT EXISTS recommendations (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    transaction_id UUID NOT NULL REFERENCES transactions(id),
                    recommendation TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );

                CREATE TABLE IF NOT EXISTS bancs_sync_log (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    transaction_id UUID NOT NULL REFERENCES transactions(id),
                    status VARCHAR(20) NOT NULL,
                    detail TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                """
            )
            conn.execute(
                """
                TRUNCATE TABLE
                    recommendations,
                    bancs_sync_log,
                    outbox_events,
                    transactions,
                    accounts
                RESTART IDENTITY CASCADE
                """
            )
            conn.execute(
                """
                INSERT INTO accounts (account_number, owner_name, balance)
                VALUES
                    ('001-000001', 'Alice Candidate', 1000.00),
                    ('001-000002', 'Bob Reviewer', 500.00),
                    ('001-000003', 'Carol Tester', 100.00)
                """
            )


@pytest.fixture
def client():
    return TestClient(app)


def get_account_balance(account_id: int) -> Decimal:
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute("SELECT balance FROM accounts WHERE id = %s", (account_id,)).fetchone()
    return row[0]


def test_approved_transaction_moves_money_and_creates_outbox_event(client):
    response = client.post(
        "/transactions",
        json={"from_account_id": 1, "to_account_id": 2, "amount": "100.00"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "APPROVED"
    assert get_account_balance(1) == Decimal("900.00")
    assert get_account_balance(2) == Decimal("600.00")

    with psycopg.connect(DATABASE_URL) as conn:
        outbox = conn.execute(
            """
            SELECT event_type, status, attempts
            FROM outbox_events
            WHERE transaction_id = %s
            """,
            (body["transaction_id"],),
        ).fetchone()

    assert outbox == ("TRANSACTION_APPROVED", "PENDING", 0)


def test_insufficient_funds_rejects_transaction_without_outbox_event(client):
    response = client.post(
        "/transactions",
        json={"from_account_id": 3, "to_account_id": 2, "amount": "500.00"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "REJECTED"
    assert body["message"] == "Insufficient funds"
    assert get_account_balance(3) == Decimal("100.00")

    with psycopg.connect(DATABASE_URL) as conn:
        outbox_count = conn.execute(
            "SELECT COUNT(*) FROM outbox_events WHERE transaction_id = %s",
            (body["transaction_id"],),
        ).fetchone()[0]

    assert outbox_count == 0


def test_invalid_amount_is_rejected_by_validation(client):
    response = client.post(
        "/transactions",
        json={"from_account_id": 1, "to_account_id": 2, "amount": "0"},
    )

    assert response.status_code == 422


def test_missing_account_returns_not_found(client):
    response = client.post(
        "/transactions",
        json={"from_account_id": 999, "to_account_id": 2, "amount": "10.00"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "One or both accounts do not exist"


def test_concurrent_transactions_do_not_overdraw_same_account():
    def submit_transfer(to_account_id: int):
        local_client = TestClient(app)
        return local_client.post(
            "/transactions",
            json={"from_account_id": 3, "to_account_id": to_account_id, "amount": "80.00"},
        ).json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(submit_transfer, [1, 2]))

    statuses = sorted(result["status"] for result in results)

    assert statuses == ["APPROVED", "REJECTED"]
    assert get_account_balance(3) == Decimal("20.00")
