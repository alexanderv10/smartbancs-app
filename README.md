# SmartBancs App

MVP para el reto tecnico NextGen Engineers. La solucion procesa transferencias financieras, protege el core legado Bancs con procesamiento asincrono, genera recomendaciones mediante un servicio de IA mock y expone logs y metricas basicas para observabilidad.

## Arquitectura

```text
Cliente / Postman
        |
        v
API de Transacciones ---- PostgreSQL
        |
        v
Tabla outbox_events
        |
        v
Worker asincrono ---- IA Mock
        |
        v
       Bancs Mock
```

## Requisitos

- Docker
- Docker Compose

## Ejecutar

```bash
docker compose up --build
```

Servicios:

- API: http://localhost:8000
- IA mock: http://localhost:8001
- Bancs mock: http://localhost:8002
- PostgreSQL: localhost:5432

## Probar una transferencia

```bash
curl -X POST http://localhost:8000/transactions ^
  -H "Content-Type: application/json" ^
  -d "{\"from_account_id\":1,\"to_account_id\":2,\"amount\":100}"
```

Respuesta esperada:

```json
{
  "transaction_id": "...",
  "trace_id": "...",
  "status": "APPROVED",
  "message": "Transaction approved"
}
```

Consultar cuenta:

```bash
curl http://localhost:8000/accounts/1
```

Consultar procesamiento asincrono de una transaccion:

```bash
curl http://localhost:8000/transactions/{transaction_id}/processing-status
```

Metricas:

```bash
curl http://localhost:8000/metrics
```

## Ejecutar ETL

```bash
python etl/transform_transactions.py
```

Entrada:

- `etl/data/raw_transactions.csv`

Salida:

- `etl/data/clean_transactions.csv`

## Detener

```bash
docker compose down
```

## Documentacion

- `docs/architecture.md`: diseno de arquitectura y decisiones tecnicas.
- `docs/incident-response.md`: respuesta al incidente simulado.
- `docs/ai-usage.md`: declaracion de uso de inteligencia artificial.
