# SmartBancs App

MVP para el reto tecnico NextGen Engineers. La solucion procesa transferencias financieras, genera recomendaciones con un servicio de IA mock mediante procesamiento asincrono y expone logs y metricas basicas para observabilidad.

## Arquitectura

```text
Cliente / Swagger / Postman
        |
        v
API de Transacciones ---- PostgreSQL
        |
        v
Tabla outbox_events
        |
        v
Worker asincrono ---- IA Mock
```

## Componentes

- `api`: servicio principal. Recibe transferencias, valida saldo, actualiza cuentas y crea eventos outbox.
- `postgres`: base de datos PostgreSQL. Guarda cuentas, transacciones, eventos y recomendaciones.
- `worker`: proceso en segundo plano. Lee eventos outbox y llama IA mock.
- `ai-service`: servicio mock que genera recomendaciones financieras.
- `etl`: script para limpiar datos transaccionales crudos.

## Requisitos

- Docker Desktop
- Docker Compose
- Python 3.12 o superior, solo para ejecutar el ETL localmente

## Ejecutar La Solucion

Desde la carpeta del proyecto:

Si venias de una ejecucion anterior, primero puedes limpiar contenedores viejos:

```bash
docker compose down --remove-orphans
```

```bash
docker compose up --build
```

Para ejecutarlo en segundo plano:

```bash
docker compose up --build -d
```

Ver servicios activos:

```bash
docker compose ps
```

Servicios disponibles:

- API principal: http://localhost:8000
- Swagger API principal: http://localhost:8000/docs
- IA mock: http://localhost:8001/docs
- PostgreSQL: localhost:5432

## Probar Desde Swagger

Abrir:

```text
http://localhost:8000/docs
```

### 1. Verificar Salud

Ejecutar:

```text
GET /health
```

Respuesta esperada:

```json
{
  "status": "ok",
  "service": "smartbancs-api"
}
```

### 2. Consultar Cuentas

Ejecutar:

```text
GET /accounts/1
GET /accounts/2
GET /accounts/3
```

Las cuentas iniciales son:

```text
Cuenta 1: 1000.00
Cuenta 2: 500.00
Cuenta 3: 100.00
```

Si ya se hicieron pruebas, los saldos pueden ser distintos.

### 3. Crear Transferencia Aprobada

Ejecutar:

```text
POST /transactions
```

Body:

```json
{
  "from_account_id": 1,
  "to_account_id": 2,
  "amount": 50
}
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

Luego consultar nuevamente:

```text
GET /accounts/1
GET /accounts/2
```

La cuenta origen debe disminuir y la cuenta destino debe aumentar.

### 4. Ver Procesamiento Asincrono

Con el `transaction_id` de una transferencia aprobada, ejecutar:

```text
GET /transactions/{transaction_id}/processing-status
```

Respuesta esperada:

```json
{
  "transaction": {
    "status": "APPROVED"
  },
  "outbox": {
    "status": "PROCESSED",
    "attempts": 1
  },
  "recommendation": {
    "message": "..."
  }
}
```

Esto demuestra que la transferencia se proceso rapido y que el worker genero la recomendacion en segundo plano.

### 5. Crear Transferencia Rechazada

Ejemplo:

```json
{
  "from_account_id": 3,
  "to_account_id": 2,
  "amount": 100
}
```

Si la cuenta 3 no tiene saldo suficiente, la respuesta sera:

```json
{
  "status": "REJECTED",
  "message": "Insufficient funds"
}
```

Para una transferencia rechazada, el `processing-status` debe mostrar:

```json
{
  "outbox": null,
  "recommendation": null
}
```

Esto ocurre porque solo las transferencias aprobadas generan tareas asincronas.

## Conceptos Clave

### Outbox

`outbox_events` es una tabla de tareas pendientes. Cuando una transferencia se aprueba, la API guarda un evento. El worker lee ese evento y ejecuta tareas secundarias.

```text
Transferencia aprobada
        |
        v
Evento en outbox_events
        |
        v
Worker procesa IA
```

### Worker

El worker es el encargado de las tareas en segundo plano. En este MVP:

- llama al servicio de IA mock para generar una recomendacion;
- marca el evento outbox como `PROCESSED`.

### Bancs

El core legado Bancs se aborda como estrategia teorica de arquitectura, no como servicio practico en este MVP. La explicacion esta en `docs/architecture.md`.

La idea propuesta es que, en produccion, SmartBancs no consulte Bancs directamente dentro del flujo principal de la transferencia. En su lugar, usaria eventos asincronos para sincronizar sin saturar el sistema legado.

## Observabilidad

### Logs

Ver logs de la API:

```bash
docker compose logs --tail=30 api
```

Tambien quedan guardados en archivo:

```text
logs/api.log
```

Eventos importantes:

- `transaction_received`
- `transaction_approved`
- `transaction_rejected`

Ver logs del worker:

```bash
docker compose logs --tail=30 worker
```

Tambien quedan guardados en archivo:

```text
logs/worker.log
```

Ver logs del servicio de IA:

```text
logs/ai-service.log
```

Eventos importantes:

- `outbox_event_processing`
- `ai_service_called`
- `outbox_event_processed`

Los logs incluyen `transaction_id` y `trace_id` para rastrear una operacion entre componentes.

### Metricas

Abrir:

```text
http://localhost:8000/metrics
```

Metricas relevantes:

- `transactions_total{status="APPROVED"}`
- `transactions_total{status="REJECTED"}`
- `database_errors_total`
- `transaction_duration_seconds`

Estas metricas permiten observar volumen transaccional, errores y tiempos de respuesta.

## Base De Datos

Entrar a PostgreSQL:

```bash
docker compose exec postgres psql -U smartbancs -d smartbancs
```

Listar tablas:

```sql
\dt
```

Ver cuentas:

```sql
SELECT * FROM accounts;
```

Ver ultimas transacciones:

```sql
SELECT id, from_account_id, to_account_id, amount, status, failure_reason
FROM transactions
ORDER BY created_at DESC
LIMIT 5;
```

Ver eventos outbox:

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

Salir de PostgreSQL:

```sql
\q
```

## Concurrencia

La API usa transacciones de PostgreSQL y bloqueo de filas con `FOR UPDATE` para evitar race conditions.

La idea es:

```text
1. Ordenar cuentas involucradas por ID.
2. Bloquearlas en PostgreSQL.
3. Validar saldo.
4. Actualizar saldos.
5. Guardar transaccion.
6. Liberar bloqueo al confirmar la transaccion.
```

El orden fijo reduce riesgo de deadlocks y `FOR UPDATE` evita que dos transferencias modifiquen el mismo saldo al mismo tiempo.

## Pruebas

Reconstruir la imagen de la API:

```bash
docker compose build api
```

Ejecutar pruebas en un esquema aislado de PostgreSQL:

```bash
docker compose run --rm -e APP_ENV=test -e PGOPTIONS="-c search_path=test_smartbancs,public" api pytest -q
```

Las pruebas cubren:

- validacion de monto;
- transferencia aprobada;
- rechazo por fondos insuficientes;
- cuenta inexistente;
- creacion de evento outbox;
- concurrencia sobre una misma cuenta.

## ETL

Ver datos crudos:

```bash
type etl\data\raw_transactions.csv
```

Ejecutar transformacion:

```bash
python etl\transform_transactions.py
```

Ver datos limpios:

```bash
type etl\data\clean_transactions.csv
```

El ETL normaliza:

- montos con simbolos, espacios o comas;
- monedas en minuscula;
- fechas en distintos formatos;
- valores nulos.

## Detener Servicios

Detener contenedores:

```bash
docker compose down
```

Detener y borrar datos de PostgreSQL:

```bash
docker compose down -v
```

Usar `-v` solo si se quiere reiniciar la base desde cero.

## Documentacion Adicional

- `docs/architecture.md`: diseno de arquitectura y decisiones tecnicas.
- `docs/incident-response.md`: respuesta al incidente simulado.
- `docs/observability.md`: guia para leer logs, rastrear transacciones y revisar metricas.
- `docs/ai-usage.md`: declaracion de uso de inteligencia artificial.
- `docs/presentation.md`: guion breve para defensa tecnica.
