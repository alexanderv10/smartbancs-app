# Observabilidad SmartBancs

Este documento explica como revisar si el sistema funciona correctamente, donde ver los logs y donde consultar las metricas.

La observabilidad del MVP se apoya en tres partes:

- logs estructurados en JSON;
- metricas en formato Prometheus;
- IDs para rastrear operaciones: `transaction_id` y `trace_id`.

## Donde ver los logs

Logs de la API:

```bash
docker compose logs --tail=50 api
```

Archivo local de la API:

```text
logs/api.log
```

Este archivo se reinicia cada vez que arranca el servicio.

Logs del worker:

```bash
docker compose logs --tail=50 worker
```

Archivo local del worker:

```text
logs/worker.log
```

Este archivo se reinicia cada vez que arranca el servicio.

Logs del servicio de IA:

```bash
docker compose logs --tail=50 ai-service
```

Archivo local del servicio de IA:

```text
logs/ai-service.log
```

Este archivo se reinicia cada vez que arranca el servicio.

En PowerShell tambien se pueden leer asi:

```bash
type logs\api.log
type logs\worker.log
type logs\ai-service.log
```

Y se puede buscar por `trace_id`:

```bash
Select-String -Path logs\*.log -Pattern "e0d7d24e"
```

## Como saber si una transferencia fue exitosa

Una transferencia aprobada deberia verse asi en la API:

```json
{
  "service": "smartbancs-api",
  "event": "transaction_received",
  "trace_id": "...",
  "from_account_id": 1,
  "to_account_id": 2,
  "amount": "30"
}
```

Luego deberian aparecer eventos del flujo de base de datos:

```json
{
  "service": "smartbancs-api",
  "event": "accounts_locked",
  "trace_id": "...",
  "account_ids": [1, 2]
}
```

```json
{
  "service": "smartbancs-api",
  "event": "balances_updated",
  "trace_id": "...",
  "from_account_id": 1,
  "to_account_id": 2,
  "amount": "30"
}
```

```json
{
  "service": "smartbancs-api",
  "event": "outbox_event_created",
  "trace_id": "...",
  "transaction_id": "...",
  "event_type": "TRANSACTION_APPROVED"
}
```

Finalmente debe aparecer:

```json
{
  "service": "smartbancs-api",
  "event": "transaction_approved",
  "trace_id": "...",
  "transaction_id": "...",
  "duration_ms": 15
}
```

Esto significa que:

- la API recibio la solicitud;
- bloqueo las cuentas en PostgreSQL;
- actualizo los saldos;
- creo un evento outbox;
- aprobo la transaccion.

## Como saber si el worker proceso la tarea

Despues de una transferencia aprobada, el worker debe mostrar:

```json
{
  "service": "smartbancs-worker",
  "event": "outbox_event_processing",
  "transaction_id": "...",
  "event_type": "TRANSACTION_APPROVED"
}
```

Luego debe llamar a IA:

```json
{
  "service": "smartbancs-worker",
  "event": "ai_service_called",
  "trace_id": "...",
  "transaction_id": "...",
  "model_version": "mock-rules-v2",
  "category": "LOW_VALUE",
  "risk_score": "0.18",
  "next_action": "Clasificar movimiento",
  "duration_ms": 20
}
```

Finalmente:

```json
{
  "service": "smartbancs-worker",
  "event": "outbox_event_processed",
  "transaction_id": "..."
}
```

Esto significa que el proceso asincrono fue exitoso:

- el worker tomo el evento;
- llamo a la IA mock;
- guardo resultados;
- marco el evento como procesado.

## Como saber si una transferencia fue rechazada

Una transferencia rechazada muestra en API:

```json
{
  "service": "smartbancs-api",
  "event": "transaction_rejected",
  "trace_id": "...",
  "transaction_id": "...",
  "reason": "Insufficient funds"
}
```

En este caso no debe aparecer en el worker.

La razon es que una transferencia rechazada no crea evento en `outbox_events`. Por eso no se llama a IA mock.

## Como rastrear una transaccion

Hay dos identificadores importantes:

- `transaction_id`: identifica la transferencia como operacion de negocio;
- `trace_id`: identifica el recorrido tecnico de la solicitud.

Si quiero buscar una operacion en logs, uso el `trace_id`.

Ejemplo:

```bash
docker compose logs api | findstr e0d7d24e
docker compose logs worker | findstr e0d7d24e
docker compose logs ai-service | findstr e0d7d24e
```

Si quiero consultar una transferencia en la API o base de datos, uso el `transaction_id`.

Ejemplo:

```text
GET /transactions/{transaction_id}/processing-status
```

## Donde ver las metricas

Las metricas se ven en:

```text
http://localhost:8000/metrics
```

La API tambien guarda una copia local en:

```text
logs/metrics.prom
```

Ese archivo se crea al arrancar el servicio `api`, aunque todavia no hayas hecho transacciones. Despues se actualiza automaticamente cada vez que una transaccion queda aprobada o rechazada. Tambien se reescribe cuando consultas `/metrics`.

Tambien se pueden consultar por terminal:

```bash
curl http://localhost:8000/metrics
```

En PowerShell puedes abrir el archivo local asi:

```bash
type logs\metrics.prom
```

## Metricas principales

### Volumen transaccional

```text
transactions_total{status="APPROVED"}
transactions_total{status="REJECTED"}
```

Sirven para saber cuantas transacciones fueron aprobadas y cuantas rechazadas.

### Errores de base de datos

```text
database_errors_total
```

Sirve para saber si hubo errores al procesar transacciones contra PostgreSQL.

Si este numero sube, revisaria inmediatamente logs de API y estado de PostgreSQL.

### Tiempos de respuesta

```text
transaction_duration_seconds
```

Es un histograma. Permite ver cuanto tarda el flujo transaccional principal.

La parte importante es:

```text
transaction_duration_seconds_count
transaction_duration_seconds_sum
```

Una forma simple de estimar el promedio es:

```text
promedio = transaction_duration_seconds_sum / transaction_duration_seconds_count
```

## Que revisar ante un incidente

Si las transferencias estan lentas:

1. Revisar `/metrics`.
2. Revisar si `transaction_duration_seconds` subio.
3. Revisar si `database_errors_total` subio.
4. Revisar logs de API con `transaction_received` y `transaction_approved`.
5. Comparar `duration_ms`.
6. Revisar PostgreSQL por bloqueos.

Si las transferencias se aprueban pero no aparece recomendacion:

1. Revisar logs del worker.
2. Revisar si hay `outbox_event_failed`.
3. Revisar logs de `ai-service`.
4. Revisar la tabla `outbox_events`.

## Consulta util en base de datos

Entrar a PostgreSQL:

```bash
docker compose exec postgres psql -U smartbancs -d smartbancs
```

Ver ultimas transacciones:

```sql
SELECT id, from_account_id, to_account_id, amount, status, failure_reason
FROM transactions
ORDER BY created_at DESC
LIMIT 5;
```

Ver estado del outbox:

```sql
SELECT transaction_id, event_type, status, attempts, last_error
FROM outbox_events
ORDER BY created_at DESC
LIMIT 5;
```

Ver recomendaciones:

```sql
SELECT transaction_id, recommendation, created_at
FROM recommendations
ORDER BY created_at DESC
LIMIT 5;
```

## Justificacion de diseno

Los datos seleccionados ayudan a diagnosticar incidentes porque:

- `trace_id` permite seguir una solicitud entre componentes;
- `transaction_id` permite consultar la operacion financiera;
- `duration_ms` muestra si una operacion fue lenta;
- `database_errors_total` alerta problemas con PostgreSQL;
- `transactions_total` muestra volumen y proporcion de aprobadas/rechazadas;
- `outbox_events.status` muestra si el procesamiento asincrono esta sano;
- `last_error` explica por que fallo una tarea del worker;
- `model_version`, `category` y `risk_score` ayudan a auditar la respuesta del mock de IA.
