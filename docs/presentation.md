# Guion de Defensa Tecnica

Este documento sirve como apoyo para presentar SmartBancs App. No es necesario leerlo completo en la sustentacion. La idea es usarlo como guia para practicar.

## Version corta

SmartBancs App procesa transferencias financieras en tiempo real. La API valida cuentas, valida saldo, mueve el dinero y guarda la transaccion en PostgreSQL.

Cuando una transferencia se aprueba, la API guarda un evento en `outbox_events`. Luego un worker en segundo plano toma ese evento y llama al servicio de IA mock para generar una recomendacion financiera. Asi la IA no bloquea la respuesta principal de la transferencia.

La solucion incluye logs con `trace_id`, metricas en `/metrics`, pruebas automatizadas y un ETL simple para limpiar datos historicos.

## Demo recomendada

### 1. Levantar el sistema

```bash
docker compose up --build -d
```

Explicacion:

> Este comando levanta los servicios principales: API, PostgreSQL, worker e IA mock.

Validar contenedores:

```bash
docker compose ps
```

### 2. Abrir Swagger

Entrar a:

```text
http://localhost:8000/docs
```

Explicacion:

> Swagger permite probar los endpoints de la API desde el navegador.

### 3. Revisar salud

Endpoint:

```text
GET /health
```

Explicacion:

> Este endpoint confirma que la API esta levantada.

### 4. Consultar cuentas antes de transferir

Endpoint:

```text
GET /accounts/{account_id}
```

Probar con cuentas 1, 2 y 3.

Explicacion:

> Estas cuentas son datos ficticios. Sirven para demostrar como cambia el saldo despues de una transferencia aprobada.

### 5. Crear transferencia aprobada

Endpoint:

```text
POST /transactions
```

Ejemplo:

```json
{
  "from_account_id": 1,
  "to_account_id": 2,
  "amount": 30
}
```

Explicacion:

> Esta transferencia deberia aprobarse si la cuenta origen tiene saldo suficiente.

Guardar:

- `transaction_id`;
- `trace_id`.

### 6. Consultar procesamiento asincrono

Endpoint:

```text
GET /transactions/{transaction_id}/processing-status
```

Explicacion:

> Aqui se ve que la transaccion fue aprobada, que el worker proceso el outbox y que se genero una recomendacion de IA.

### 7. Crear transferencia rechazada

Ejemplo:

```json
{
  "from_account_id": 3,
  "to_account_id": 2,
  "amount": 500
}
```

Explicacion:

> Esta transferencia se rechaza por fondos insuficientes. Como no se aprobo, no crea evento outbox y el worker no llama a IA.

### 8. Ver logs de API

```bash
docker compose logs --tail=50 api
```

Explicacion:

> En estos logs se ven eventos como `transaction_received`, `accounts_locked`, `balances_updated`, `outbox_event_created`, `transaction_approved` y `transaction_rejected`. El `trace_id` permite seguir una solicitud.

### 9. Ver logs del worker

```bash
docker compose logs --tail=50 worker
```

Explicacion:

> Aqui solo deberian aparecer transferencias aprobadas, porque solo ellas generan eventos en `outbox_events`.

### 10. Ver logs de IA mock

```bash
docker compose logs --tail=50 ai-service
```

Explicacion:

> Aqui se ve cuando la IA mock genera una recomendacion en espanol. El mock devuelve version de modelo, categoria, score de riesgo, accion sugerida y senales usadas.

### 11. Ver metricas

Abrir:

```text
http://localhost:8000/metrics
```

Explicacion:

> Estas son metricas en formato Prometheus. Permiten observar cuantas transacciones fueron aprobadas o rechazadas, si hubo errores de base de datos y cuanto tarda el procesamiento.

### 12. Revisar base de datos

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
SELECT id, account_number, owner_name, balance, status
FROM accounts
ORDER BY id;
```

Ver transacciones:

```sql
SELECT id, from_account_id, to_account_id, amount, status, failure_reason
FROM transactions
ORDER BY created_at DESC
LIMIT 5;
```

Ver outbox:

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

### 13. Ejecutar pruebas automatizadas

```bash
docker compose run --rm -e APP_ENV=test -e PGOPTIONS="-c search_path=test_smartbancs,public" api pytest -q
```

Explicacion:

> Este comando ejecuta las pruebas en un esquema separado para no danar los datos de la demo.

### 14. Ejecutar ETL

```bash
python etl\transform_transactions.py
```

Ver resultado:

```bash
type etl\data\clean_transactions.csv
```

Explicacion:

> El ETL toma datos crudos, normaliza montos, moneda y fecha, y genera un archivo limpio.

## Preguntas probables

### Que diferencia hay entre `transaction_id` y `trace_id`?

`transaction_id` identifica la transferencia como negocio. Sirve para consultar una transaccion especifica.

`trace_id` identifica el recorrido tecnico de una solicitud. Sirve para buscar logs relacionados con esa peticion.

### Por que usar outbox?

Porque asegura que, si la transferencia se aprueba, queda guardado un evento pendiente para procesar tareas secundarias. Asi no se pierde la tarea aunque el worker este caido temporalmente.

### Por que la IA no se llama directamente desde la API?

Porque eso haria mas lento el flujo principal. Si la IA se demora, el usuario tambien tendria que esperar. Con el worker, la transferencia responde rapido y la recomendacion se procesa despues.

### Que pasa si la transferencia es rechazada?

Se guarda como `REJECTED`, pero no se crea evento outbox. Por eso el worker no llama a IA.

### Como se protege el saldo?

La API usa transacciones de PostgreSQL y bloquea las filas de las cuentas con `FOR UPDATE`. Asi evita que dos transferencias modifiquen el mismo saldo al mismo tiempo sin control.

### El sistema soporta 10 000 transacciones por segundo?

Este MVP no demuestra 10 000 TPS reales en local. Lo que demuestra es un diseno orientado a alta concurrencia: flujo critico corto, tareas secundarias asincronas, control de concurrencia en base de datos, metricas y posibilidad de escalar API y workers.

## Cierre recomendado

> La decision mas importante fue separar lo critico de lo secundario. La transferencia se procesa con consistencia y rapidez, mientras la recomendacion de IA se ejecuta despues con un worker. Esto mejora tiempos de respuesta y deja trazabilidad mediante logs, metricas y base de datos.
