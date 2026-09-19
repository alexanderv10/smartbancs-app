import json
import logging
import os
import time
from typing import Any

import psycopg
import requests


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://smartbancs:smartbancs@localhost:5432/smartbancs")
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8001")
SERVICE_NAME = os.getenv("SERVICE_NAME", "smartbancs-worker")
LOG_FILE = os.getenv("LOG_FILE")


# Configura salida de logs en consola y archivo local para revisar el worker facilmente.
def configure_logging() -> logging.Logger:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if LOG_FILE:
        log_dir = os.path.dirname(LOG_FILE)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        handlers.append(logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=handlers, force=True)
    return logging.getLogger(SERVICE_NAME)


logger = configure_logging()


# Escribe logs JSON del worker con transaction_id y trace_id cuando estan disponibles.
def log_event(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"service": SERVICE_NAME, "event": event, **fields}, default=str))


# Mantiene el worker escuchando eventos pendientes continuamente.
def main() -> None:
    log_event("worker_started")
    while True:
        try:
            processed = process_next_event()
            if not processed:
                time.sleep(2)
        except Exception as exc:
            log_event("worker_loop_error", error=str(exc))
            time.sleep(3)


# Toma un evento outbox pendiente, llama IA y marca el evento como procesado o fallido.
def process_next_event() -> bool:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.transaction():
            event = conn.execute(
                """
                SELECT id, transaction_id, event_type, payload, attempts
                FROM outbox_events
                WHERE status IN ('PENDING', 'FAILED') AND attempts < 5
                ORDER BY created_at
                LIMIT 1
                -- SKIP LOCKED permite que varios workers trabajen sin tomar el mismo evento.
                FOR UPDATE SKIP LOCKED
                """
            ).fetchone()
            if event is None:
                return False

            event_id, transaction_id, event_type, payload, attempts = event
            # Marcamos PROCESSING antes de llamar servicios externos para evitar duplicados inmediatos.
            conn.execute(
                "UPDATE outbox_events SET status = 'PROCESSING', attempts = attempts + 1 WHERE id = %s",
                (event_id,),
            )

    log_event("outbox_event_processing", event_id=event_id, transaction_id=transaction_id, event_type=event_type)
    try:
        # Estas tareas son secundarias: no deben retrasar la respuesta de POST /transactions.
        recommendation = call_ai_service(payload)
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.transaction():
                conn.execute(
                    "INSERT INTO recommendations (transaction_id, recommendation) VALUES (%s, %s)",
                    (transaction_id, recommendation),
                )
                conn.execute(
                    """
                    UPDATE outbox_events
                    SET status = 'PROCESSED', processed_at = now(), last_error = NULL
                    WHERE id = %s
                    """,
                    (event_id,),
                )
        log_event("outbox_event_processed", event_id=event_id, transaction_id=transaction_id)
    except Exception as exc:
        with psycopg.connect(DATABASE_URL) as conn:
            # El evento queda FAILED con last_error para reintentos y diagnostico.
            conn.execute(
                "UPDATE outbox_events SET status = 'FAILED', last_error = %s WHERE id = %s",
                (str(exc), event_id),
            )
            conn.commit()
        log_event("outbox_event_failed", event_id=event_id, transaction_id=transaction_id, error=str(exc), attempts=attempts + 1)
    return True


# Llama al servicio IA mock y registra la categoria, score y accion sugerida.
def call_ai_service(payload: dict[str, Any]) -> str:
    # Servicio separado para demostrar que la IA no bloquea el flujo transaccional principal.
    started = time.monotonic()
    response = requests.post(f"{AI_SERVICE_URL}/recommendations", json=payload, timeout=3)
    response.raise_for_status()
    data = response.json()
    duration = time.monotonic() - started
    log_event(
        "ai_service_called",
        trace_id=payload.get("trace_id"),
        transaction_id=payload.get("transaction_id"),
        model_version=data.get("model_version"),
        category=data.get("category"),
        risk_score=data.get("risk_score"),
        next_action=data.get("next_action"),
        duration_ms=int(duration * 1000),
    )
    return data["recommendation"]


if __name__ == "__main__":
    main()
