import os
import time
from decimal import Decimal

from fastapi import FastAPI
from pydantic import BaseModel


SERVICE_NAME = os.getenv("SERVICE_NAME", "smartbancs-bancs-mock")
app = FastAPI(title="Bancs Legacy Core Mock", version="0.1.0")


class BancsSyncRequest(BaseModel):
    transaction_id: str
    trace_id: str
    from_account_id: int
    to_account_id: int
    amount: Decimal


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/bancs/sync")
def sync_transaction(request: BancsSyncRequest) -> dict[str, str]:
    # Latencia artificial: recuerda que un sistema legado puede responder mas lento.
    time.sleep(0.25)
    return {
        "transaction_id": request.transaction_id,
        "trace_id": request.trace_id,
        "status": "SYNCED",
        "system": "BANCS_MOCK",
    }
