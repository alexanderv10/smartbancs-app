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
LOG_FILE = os.getenv("LOG_FILE")
METRICS_FILE = os.getenv("METRICS_FILE")


# Configura logs en consola y archivo para poder auditar el flujo desde Docker o desde logs/*.log.
def configure_logging() -> logging.Logger:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if LOG_FILE:
        log_dir = os.path.dirname(LOG_FILE)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        handlers.append(logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=handlers, force=True)
    return logging.getLogger(SERVICE_NAME)


logger = logging.getLogger(SERVICE_NAME)
logger = configure_logging()

TRANSACTIONS_TOTAL = Counter("transactions_total", "Total transaction requests", ["status"])
DATABASE_ERRORS_TOTAL = Counter("database_errors_total", "Total database errors")
TRANSACTION_DURATION = Histogram("transaction_duration_seconds", "Transaction processing duration")

app = FastAPI(title="SmartBancs Transaction API", version="0.1.0")


# Genera el texto Prometheus y, si existe METRICS_FILE, deja una copia legible en logs/metrics.prom.
def write_metrics_snapshot() -> bytes:
    payload = generate_latest()
    if METRICS_FILE:
        metrics_dir = os.path.dirname(METRICS_FILE)
        if metrics_dir:
            os.makedirs(metrics_dir, exist_ok=True)
        with open(METRICS_FILE, "wb") as metrics_file:
            metrics_file.write(payload)
    return payload


# Centraliza el conteo de transacciones para actualizar tambien el archivo local de metricas.
def mark_transaction_status(status: str) -> None:
    TRANSACTIONS_TOTAL.labels(status=status).inc()
    write_metrics_snapshot()


# Crea el archivo de metricas desde el arranque, aun antes de procesar la primera transaccion.
@app.on_event("startup")
def startup() -> None:
    TRANSACTIONS_TOTAL.labels(status="APPROVED")
    TRANSACTIONS_TOTAL.labels(status="REJECTED")
    write_metrics_snapshot()


class TransactionRequest(BaseModel):
    # valida la entrada antes de tocar la base: IDs positivos y monto mayor que cero.
    from_account_id: int = Field(gt=0)
    to_account_id: int = Field(gt=0)
    amount: Decimal = Field(gt=Decimal("0"))


class TransactionResponse(BaseModel):
    transaction_id: UUID
    trace_id: UUID
    status: str
    message: str


# Escribe eventos JSON con campos comunes para rastrear una operacion por trace_id.
def log_event(event: str, **fields: Any) -> None:
    # Logs estructurados: facilitan rastrear una transaccion por trace_id en API y worker.
    payload = {"service": SERVICE_NAME, "event": event, **fields}
    logger.info(json.dumps(payload, default=str))

# Abre una conexion a PostgreSQL y la cierra automaticamente al salir del bloque.
@contextmanager
def db_connection():
    # Centraliza la conexion para que todos los endpoints usen la misma configuracion.
    with psycopg.connect(DATABASE_URL) as conn:
        yield conn

# Endpoint simple para confirmar que la API esta viva.
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}

# Expone metricas Prometheus de volumen, errores y duracion de transacciones.
@app.get("/metrics")
def metrics() -> Response:
    # Prometheus puede leer este endpoint para monitorear volumen, errores y latencia.
    payload = write_metrics_snapshot()
    return Response(payload, media_type=CONTENT_TYPE_LATEST)

# Consulta una cuenta para validar saldos antes y despues de las transferencias.
@app.get("/accounts/{account_id}")
def get_account(account_id: int) -> dict[str, Any]:
    # Endpoint de consulta usado en la demo para comprobar saldos antes/despues.
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

# Consulta una transaccion especifica por su identificador de negocio.
@app.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: UUID) -> dict[str, Any]:
    # Permite consultar el comprobante tecnico de una transferencia especifica.
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

# Resume el estado completo: transaccion principal, outbox y recomendacion de IA.
@app.get("/transactions/{transaction_id}/processing-status")
def get_processing_status(transaction_id: UUID) -> dict[str, Any]:
    # Endpoint de demo: junta estado principal, outbox e IA para explicar el flujo completo.
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
    }

# Ejecuta el flujo critico: valida, bloquea cuentas, mueve saldo y crea outbox si aprueba.
@app.post("/transactions", response_model=TransactionResponse)
def create_transaction(request: TransactionRequest) -> TransactionResponse:
    started = time.monotonic()
    # trace_id permite seguir la misma operacion entre logs de API, worker e IA.
    trace_id = uuid4()
    log_event(
        "transaction_received",
        trace_id=trace_id,
        from_account_id=request.from_account_id,
        to_account_id=request.to_account_id,
        amount=request.amount,
    )

    if request.from_account_id == request.to_account_id:
        mark_transaction_status("REJECTED")
        raise HTTPException(status_code=400, detail="Origin and destination accounts must be different")

    try:
        with db_connection() as conn:
            with conn.transaction():
                # Orden fijo de bloqueo: reduce el riesgo de deadlocks entre transferencias cruzadas.
                account_ids = sorted([request.from_account_id, request.to_account_id])
                rows = conn.execute(
                    """
                    SELECT id, balance, status
                    FROM accounts
                    WHERE id = ANY(%s)
                    ORDER BY id
                    -- FOR UPDATE bloquea las filas hasta confirmar la transaccion.
                    FOR UPDATE
                    """,
                    (account_ids,),
                ).fetchall()
                log_event("accounts_locked", trace_id=trace_id, account_ids=account_ids)

                accounts = {row[0]: {"balance": row[1], "status": row[2]} for row in rows}
                if request.from_account_id not in accounts or request.to_account_id not in accounts:
                    mark_transaction_status("REJECTED")
                    raise HTTPException(status_code=404, detail="One or both accounts do not exist")

                if accounts[request.from_account_id]["status"] != "ACTIVE" or accounts[request.to_account_id]["status"] != "ACTIVE":
                    # Rechazos de negocio quedan auditados en transactions, pero no generan outbox.
                    transaction_id = insert_rejected_transaction(conn, request, trace_id, "Inactive account")
                    mark_transaction_status("REJECTED")
                    return TransactionResponse(
                        transaction_id=transaction_id,
                        trace_id=trace_id,
                        status="REJECTED",
                        message="Inactive account",
                    )

                if accounts[request.from_account_id]["balance"] < request.amount:
                    # Fondos insuficientes no mueve saldo y tampoco dispara IA.
                    transaction_id = insert_rejected_transaction(conn, request, trace_id, "Insufficient funds")
                    mark_transaction_status("REJECTED")
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
                log_event(
                    "balances_updated",
                    trace_id=trace_id,
                    from_account_id=request.from_account_id,
                    to_account_id=request.to_account_id,
                    amount=request.amount,
                )
                # La transferencia aprobada y el evento outbox se guardan en la misma transaccion DB.
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
                # Outbox: la transaccion queda confirmada y el worker procesa IA despues.
                conn.execute(
                    """
                    INSERT INTO outbox_events (transaction_id, event_type, payload)
                    VALUES (%s, 'TRANSACTION_APPROVED', %s)
                    """,
                    (transaction_id, Jsonb(payload)),
                )
                log_event("outbox_event_created", trace_id=trace_id, transaction_id=transaction_id, event_type="TRANSACTION_APPROVED")

        duration = time.monotonic() - started
        TRANSACTIONS_TOTAL.labels(status="APPROVED").inc()
        TRANSACTION_DURATION.observe(duration)
        write_metrics_snapshot()
        log_event("transaction_approved", trace_id=trace_id, transaction_id=transaction_id, duration_ms=int(duration * 1000))
        return TransactionResponse(
            transaction_id=transaction_id,
            trace_id=trace_id,
            status="APPROVED",
            message="Transaction approved",
        )
    except psycopg.Error as exc:
        # Si PostgreSQL falla, lo registramos como metrica y log para diagnostico operativo.
        DATABASE_ERRORS_TOTAL.inc()
        write_metrics_snapshot()
        log_event("database_error", trace_id=trace_id, error=str(exc))
        raise HTTPException(status_code=503, detail="Database error while processing transaction") from exc


# Guarda rechazos de negocio sin crear outbox ni disparar IA.
def insert_rejected_transaction(conn: psycopg.Connection, request: TransactionRequest, trace_id: UUID, reason: str) -> UUID:
    # Audita rechazos de negocio sin ejecutar tareas secundarias.
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
