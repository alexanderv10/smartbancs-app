import os
from decimal import Decimal

from fastapi import FastAPI
from pydantic import BaseModel


SERVICE_NAME = os.getenv("SERVICE_NAME", "smartbancs-ai-service")
app = FastAPI(title="SmartBancs AI Recommendation Mock", version="0.1.0")


class RecommendationRequest(BaseModel):
    transaction_id: str
    trace_id: str
    from_account_id: int
    to_account_id: int
    amount: Decimal


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/recommendations")
def create_recommendation(request: RecommendationRequest) -> dict[str, str]:
    # Mock deterministico: no entrena un modelo, solo demuestra el contrato de integracion de IA.
    if request.amount >= Decimal("500"):
        recommendation = "High-value transfer detected. Review monthly budget impact and keep emergency savings available."
    elif request.amount >= Decimal("100"):
        recommendation = "Moderate transfer completed. Track recurring transfers to improve cash-flow planning."
    else:
        recommendation = "Low-value transfer completed. Keep categorizing small movements for better financial insights."
    return {
        "transaction_id": request.transaction_id,
        "trace_id": request.trace_id,
        "recommendation": recommendation,
    }
