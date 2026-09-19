import os
import json
import logging
from decimal import Decimal
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel


SERVICE_NAME = os.getenv("SERVICE_NAME", "smartbancs-ai-service")
MODEL_VERSION = os.getenv("MODEL_VERSION", "mock-rules-v2")
LOG_FILE = os.getenv("LOG_FILE")
app = FastAPI(title="SmartBancs AI Recommendation Mock", version="0.1.0")


# Configura logs del servicio IA en consola y archivo local.
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


class RecommendationRequest(BaseModel):
    # Este contrato simula los datos minimos que un modelo real recibiria para recomendar.
    transaction_id: str
    trace_id: str
    from_account_id: int
    to_account_id: int
    amount: Decimal


# Emite eventos JSON para auditar recomendaciones generadas por la IA mock.
def log_event(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"service": SERVICE_NAME, "event": event, **fields}, default=str))


# Endpoint de salud para confirmar que el servicio IA esta disponible.
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


# Genera una recomendacion mock segun monto, categoria y score simulado.
@app.post("/recommendations")
def create_recommendation(request: RecommendationRequest) -> dict[str, Any]:
    # Mock avanzado pero deterministico: simula score, categoria y explicacion de un modelo real.
    if request.amount >= Decimal("500"):
        category = "HIGH_VALUE"
        risk_score = Decimal("0.82")
        recommendation = "Transferencia de alto valor completada. Revisa el impacto en tu presupuesto mensual y conserva un fondo de emergencia disponible."
        next_action = "Revisar presupuesto mensual"
    elif request.amount >= Decimal("100"):
        category = "MEDIUM_VALUE"
        risk_score = Decimal("0.46")
        recommendation = "Transferencia moderada completada. Revisa si este movimiento se repite para mejorar tu planeacion de flujo de caja."
        next_action = "Revisar transferencias recurrentes"
    else:
        category = "LOW_VALUE"
        risk_score = Decimal("0.18")
        recommendation = "Transferencia de bajo valor completada. Clasifica estos movimientos pequenos para entender mejor tus habitos financieros."
        next_action = "Clasificar movimiento"

    features = {
        "amount": str(request.amount),
        "amount_band": category,
        "source_account": request.from_account_id,
        "destination_account": request.to_account_id,
    }
    log_event(
        "recommendation_created",
        trace_id=request.trace_id,
        transaction_id=request.transaction_id,
        model_version=MODEL_VERSION,
        category=category,
        risk_score=str(risk_score),
        next_action=next_action,
    )
    return {
        "transaction_id": request.transaction_id,
        "trace_id": request.trace_id,
        "model_version": MODEL_VERSION,
        "category": category,
        "risk_score": str(risk_score),
        "recommendation": recommendation,
        "next_action": next_action,
        "features_used": features,
    }
