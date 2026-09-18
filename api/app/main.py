import json
import logging
import os
import time
from contextlib import contextmanager
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import psycopg
from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://smartbancs:smartbancs@localhost:5432/smartbancs")
SERVICE_NAME = os.getenv("SERVICE_NAME", "smartbancs-api")

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(SERVICE_NAME)

TRANSACTIONS_TOTAL = Counter("transactions_total", "Total transaction requests", ["status"])
DATABASE_ERRORS_TOTAL = Counter("database_errors_total", "Total database errors")
TRANSACTION_DURATION = Histogram("transaction_duration_seconds", "Transaction processing duration")

app = FastAPI(title="SmartBancs Transaction API", version="0.1.0")


class TransactionRequest(BaseModel):
    from_account_id: int = Field(gt=0)
    to_account_id: int = Field(gt=0)
    amount: Decimal = Field(gt=Decimal("0"))


class TransactionResponse(BaseModel):
    transaction_id: UUID
    trace_id: UUID
    status: str
    message: str


def log_event(event: str, **fields: Any) -> None:
    payload = {"service": SERVICE_NAME, "event": event, **fields}
    logger.info(json.dumps(payload, default=str))


@contextmanager
def db_connection():
    with psycopg.connect(DATABASE_URL) as conn:
        yield conn


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/accounts/{account_id}")
def get_account(account_id: int) -> dict[str, Any]:
    with db_connection() as conn:
        row = conn.execute(
            "SELECT id, account_number, owner_name, balance, status FROM accounts WHERE id = %s",
            (account_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return {
        "id": row[0],
        "account_number": row[1],
        "owner_name": row[2],
        "balance": str(row[3]),
        "status": row[4],
    }


@app.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: UUID) -> dict[str, Any]:
    with db_connection() as conn:
        row = conn.execute(
            """
            SELECT id, from_account_id, to_account_id, amount, status, failure_reason, trace_id, created_at
            FROM transactions
            WHERE id = %s
            """,
            (transaction_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {
        "id": row[0],
        "from_account_id": row[1],
        "to_account_id": row[2],
        "amount": str(row[3]),
        "status": row[4],
        "failure_reason": row[5],
        "trace_id": row[6],
        "created_at": row[7],
    }


@app.get("/transactions/{transaction_id}/processing-status")
def get_processing_status(transaction_id: UUID) -> dict[str, Any]:
    with db_connection() as conn:
        transaction = conn.execute(
            "SELECT id, status, trace_id, created_at FROM transactions WHERE id = %s",
            (transaction_id,),
        ).fetchone()
        if transaction is None:
            raise HTTPException(status_code=404, detail="Transaction not found")

        outbox = conn.execute(
            """
            SELECT status, attempts, last_error, processed_at
            FROM outbox_events
            WHERE transaction_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (transaction_id,),
        ).fetchone()
        recommendation = conn.execute(
            """
            SELECT recommendation, created_at
            FROM recommendations
            WHERE transaction_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (transaction_id,),
        ).fetchone()
        bancs_sync = conn.execute(
            """
            SELECT status, detail, created_at
            FROM bancs_sync_log
            WHERE transaction_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (transaction_id,),
        ).fetchone()

    return {
        "transaction": {
            "id": transaction[0],
            "status": transaction[1],
            "trace_id": transaction[2],
            "created_at": transaction[3],
        },
        "outbox": None
        if outbox is None
        else {
            "status": outbox[0],
            "attempts": outbox[1],
            "last_error": outbox[2],
            "processed_at": outbox[3],
        },
        "recommendation": None
        if recommendation is None
        else {
            "message": recommendation[0],
            "created_at": recommendation[1],
        },
        "bancs_sync": None
        if bancs_sync is None
        else {
            "status": bancs_sync[0],
            "detail": bancs_sync[1],
            "created_at": bancs_sync[2],
        },
    }


@app.post("/transactions", response_model=TransactionResponse)
def create_transaction(request: TransactionRequest) -> TransactionResponse:
    started = time.monotonic()
    trace_id = uuid4()
    log_event(
        "transaction_received",
        trace_id=trace_id,
        from_account_id=request.from_account_id,
        to_account_id=request.to_account_id,
        amount=request.amount,
    )

    if request.from_account_id == request.to_account_id:
        TRANSACTIONS_TOTAL.labels(status="REJECTED").inc()
        raise HTTPException(status_code=400, detail="Origin and destination accounts must be different")

    try:
        with db_connection() as conn:
            with conn.transaction():
                account_ids = sorted([request.from_account_id, request.to_account_id])
                rows = conn.execute(
                    """
                    SELECT id, balance, status
                    FROM accounts
                    WHERE id = ANY(%s)
                    ORDER BY id
                    FOR UPDATE
                    """,
                    (account_ids,),
                ).fetchall()

                accounts = {row[0]: {"balance": row[1], "status": row[2]} for row in rows}
                if request.from_account_id not in accounts or request.to_account_id not in accounts:
                    TRANSACTIONS_TOTAL.labels(status="REJECTED").inc()
                    raise HTTPException(status_code=404, detail="One or both accounts do not exist")

                if accounts[request.from_account_id]["status"] != "ACTIVE" or accounts[request.to_account_id]["status"] != "ACTIVE":
                    transaction_id = insert_rejected_transaction(conn, request, trace_id, "Inactive account")
                    TRANSACTIONS_TOTAL.labels(status="REJECTED").inc()
                    return TransactionResponse(
                        transaction_id=transaction_id,
                        trace_id=trace_id,
                        status="REJECTED",
                        message="Inactive account",
                    )

                if accounts[request.from_account_id]["balance"] < request.amount:
                    transaction_id = insert_rejected_transaction(conn, request, trace_id, "Insufficient funds")
                    TRANSACTIONS_TOTAL.labels(status="REJECTED").inc()
                    return TransactionResponse(
                        transaction_id=transaction_id,
                        trace_id=trace_id,
                        status="REJECTED",
                        message="Insufficient funds",
                    )

                conn.execute(
                    "UPDATE accounts SET balance = balance - %s WHERE id = %s",
                    (request.amount, request.from_account_id),
                )
                conn.execute(
                    "UPDATE accounts SET balance = balance + %s WHERE id = %s",
                    (request.amount, request.to_account_id),
                )
                transaction_id = conn.execute(
                    """
                    INSERT INTO transactions (from_account_id, to_account_id, amount, status, trace_id)
                    VALUES (%s, %s, %s, 'APPROVED', %s)
                    RETURNING id
                    """,
                    (request.from_account_id, request.to_account_id, request.amount, trace_id),
                ).fetchone()[0]
                payload = {
                    "transaction_id": str(transaction_id),
                    "trace_id": str(trace_id),
                    "from_account_id": request.from_account_id,
                    "to_account_id": request.to_account_id,
                    "amount": str(request.amount),
                }
                conn.execute(
                    """
                    INSERT INTO outbox_events (transaction_id, event_type, payload)
                    VALUES (%s, 'TRANSACTION_APPROVED', %s)
                    """,
                    (transaction_id, Jsonb(payload)),
                )

        duration = time.monotonic() - started
        TRANSACTIONS_TOTAL.labels(status="APPROVED").inc()
        TRANSACTION_DURATION.observe(duration)
        log_event("transaction_approved", trace_id=trace_id, transaction_id=transaction_id, duration_ms=int(duration * 1000))
        return TransactionResponse(
            transaction_id=transaction_id,
            trace_id=trace_id,
            status="APPROVED",
            message="Transaction approved",
        )
    except psycopg.Error as exc:
        DATABASE_ERRORS_TOTAL.inc()
        log_event("database_error", trace_id=trace_id, error=str(exc))
        raise HTTPException(status_code=503, detail="Database error while processing transaction") from exc


def insert_rejected_transaction(conn: psycopg.Connection, request: TransactionRequest, trace_id: UUID, reason: str) -> UUID:
    transaction_id = conn.execute(
        """
        INSERT INTO transactions (from_account_id, to_account_id, amount, status, failure_reason, trace_id)
        VALUES (%s, %s, %s, 'REJECTED', %s, %s)
        RETURNING id
        """,
        (request.from_account_id, request.to_account_id, request.amount, reason, trace_id),
    ).fetchone()[0]
    log_event("transaction_rejected", trace_id=trace_id, transaction_id=transaction_id, reason=reason)
    return transaction_id
