# Documento Tecnico SmartBancs App

## 1. Objetivo de la solucion

SmartBancs App es un MVP para procesar transferencias financieras en tiempo real y generar recomendaciones financieras mediante un servicio de IA mock, sin retrasar el flujo transaccional principal.

El reto plantea tres restricciones importantes:

- alta concurrencia;
- integracion teorica con un core legado llamado Bancs;
- recomendaciones de IA que no bloqueen transferencias.

## 2. Arquitectura general

Componentes del MVP:

```text
Cliente / Swagger / Postman / Menu terminal
        |
        v
API de Transacciones ---- PostgreSQL
        |
        v
Tabla outbox_events
        |
        v
Worker asincrono ---- Servicio IA Mock
```

### Componentes

- `api`: microservicio principal en FastAPI. Expone endpoints para cuentas, transacciones, estado de procesamiento y metricas.
- `postgres`: base de datos principal. Guarda cuentas, transacciones, eventos outbox y recomendaciones.
- `worker`: proceso en segundo plano. Lee eventos pendientes y llama al servicio de IA.
- `ai-service`: mock avanzado de IA. Clasifica transferencias y genera recomendaciones.
- `logs`: archivos de evidencia para observabilidad.

### Justificacion

- FastAPI: permite construir una API REST liviana, facil de documentar con Swagger y adecuada para MVPs.
- PostgreSQL: ofrece transacciones ACID, bloqueo de filas y consistencia fuerte para saldos.
- Docker Compose: permite levantar API, base de datos, worker e IA con un solo comando.
- Patron outbox: evita perder eventos secundarios y permite procesarlos despues sin bloquear al usuario.
- Worker asincrono: separa la aprobacion de la transferencia de la generacion de recomendaciones.
- Prometheus format: expone metricas de manera estandar y facil de leer.

## 3.1. Infraestructura, Base de Datos y Desarrollo del Backend

Se implemento una API REST en FastAPI con endpoints principales:

- `GET /health`: valida que la API este viva.
- `GET /accounts/{account_id}`: consulta una cuenta.
- `POST /transactions`: crea una transferencia.
- `GET /transactions/{transaction_id}`: consulta una transferencia.
- `GET /transactions/{transaction_id}/processing-status`: consulta estado transaccional, outbox y recomendacion.
- `GET /metrics`: expone metricas.

La base de datos PostgreSQL contiene:

- `accounts`: cuentas y saldos.
- `transactions`: transferencias aprobadas y rechazadas.
- `outbox_events`: eventos para procesamiento asincrono.
- `recommendations`: recomendaciones generadas por IA.

Docker Compose levanta:

- API principal;
- PostgreSQL;
- worker;
- servicio de IA mock.

Comando principal:

```bash
docker compose up --build -d
```

### Manejo de concurrencia

Para evitar condiciones de carrera al actualizar saldos, la API usa transacciones de PostgreSQL y bloqueo de filas:

```sql
SELECT id, balance, status
FROM accounts
WHERE id = ANY(:account_ids)
ORDER BY id
FOR UPDATE;
```

`FOR UPDATE` bloquea las cuentas involucradas hasta terminar la transaccion. Esto evita que dos solicitudes modifiquen el mismo saldo al mismo tiempo.

El `ORDER BY id` hace que las cuentas se bloqueen siempre en el mismo orden. Esto reduce el riesgo de deadlocks porque evita que dos transacciones bloqueen las mismas cuentas en orden contrario.

## 3.2. Bancs: Manejo, Utilizacion e Integracion de Datos

### Estrategia Sincronización

Bancs representa el core legado del banco. Es robusto, pero no debe recibir demasiadas consultas directas porque podria degradarse.

La estrategia propuesta seria:

```text
Transferencia aprobada en SmartBancs
        |
        v
Evento persistido en outbox_events
        |
        v
Proceso asincrono de sincronizacion
        |
        v
Core legado Bancs
```

SmartBancs no llamaria a Bancs dentro del flujo principal de `POST /transactions`. Primero aprobaria la transferencia en su propia base operativa y luego dejaria un evento persistido para sincronizacion posterior.

La estrategia evita saturar Bancs porque la respuesta al usuario no depende de la latencia del core legado. Además, los eventos quedan guardados si Bancs esta temporalmente caido y se puede controlar la velocidad de sincronizacion hacia Bancs. Por otro lado, se puede monitorear el backlog de eventos pendientes.

En produccion, esta sincronizacion podria implementarse con un worker dedicado, una cola de mensajes o un bus de eventos. Tambien se necesitaria idempotencia para evitar duplicados y conciliacion periodica contra el core legado.

### ETL practico

Se implemento un script ETL en Python:

```bash
python etl/transform_transactions.py
```

Entrada:

```text
etl/data/raw_transactions.csv
```

Salida:

```text
etl/data/clean_transactions.csv
```

El ETL limpia datos crudos, estandariza montos, monedas y fechas, y genera un archivo mas confiable para analisis o consumo futuro por IA.

## 3.3. Inteligencia Artificial: Implementacion y Despliegue

Se implemento un servicio independiente llamado `ai-service`.

El servicio de IA actual no aprueba transferencias, no mueve dinero y no modifica saldos. Su responsabilidad es analizar una transferencia aprobada y generar una recomendacion financiera.

Actualmente el mock devuelve:

- `model_version`: version del modelo mock.
- `category`: clasificacion de la transferencia.
- `risk_score`: puntaje simulado de atencion o importancia.
- `next_action`: accion sugerida.
- `features_used`: senales usadas para decidir.
- `message`: recomendacion en lenguaje natural.

Ejemplo conceptual:

```json
{
  "model_version": "mock-rules-v2",
  "category": "LOW_VALUE",
  "risk_score": "0.18",
  "next_action": "Clasificar movimiento",
  "message": "Transferencia de bajo valor completada. Clasifica estos movimientos pequenos para entender mejor tus habitos financieros."
}
```

### Proposito actual del servicio IA

El proposito actual no es demostrar precision de machine learning, sino demostrar la arquitectura de integracion.

El servicio IA permite mostrar que:

- la IA esta separada de la API principal;
- la transferencia no espera a que termine la IA;
- el worker puede llamar a IA despues de aprobada la transferencia;
- el resultado queda guardado y se puede consultar;
- en el futuro el mock puede reemplazarse por un modelo real.

### Consumo asincrono

La API principal no llama directamente a IA durante `POST /transactions`.

Flujo:

1. La API aprueba la transferencia.
2. La API crea un evento en `outbox_events`.
3. La API responde al usuario.
4. El worker toma el evento.
5. El worker llama al servicio IA.
6. El worker guarda la recomendacion.

### Manejo del modelo en produccion

En produccion, el mock podria reemplazarse por:

- modelo de recomendacion financiera - Random Forest

Para una primera versión del modelo de recomendación usaría Random Forest como clasificador supervisado. El modelo recibiría variables de la transacción y del historial del usuario, y devolvería una acción recomendada.

El ciclo de vida del modelo incluiria:

1. Alimentacion de datos: usar datos historicos limpios del ETL y datos transaccionales validados.
2. Entrenamiento: entrenar el modelo en un ambiente separado.
3. Validacion: medir calidad, falsos positivos, sesgos y estabilidad.
4. Versionamiento: registrar la version del modelo usada en cada recomendacion.
5. Despliegue gradual: publicar nuevas versiones de forma controlada.
6. Monitoreo de data drift: comparar datos actuales contra datos historicos de entrenamiento.
7. Monitoreo operativo: medir latencia, errores, CPU, memoria y costo.
8. Reentrenamiento: actualizar el modelo cuando cambien los patrones o baje la calidad.
9. Auditoria: guardar senales usadas, categoria, score y version.

## 3.4. Observabilidad

La solucion usa:

- logs estructurados en JSON;
- metricas en formato Prometheus;
- archivo local de metricas;
- `transaction_id`;
- `trace_id`.

Archivos principales:

```text
logs/api.log
logs/worker.log
logs/ai-service.log
logs/metrics.prom
```

Endpoint de metricas:

```text
http://localhost:8000/metrics
```

### Logs de la API

La API registra eventos como:

- `transaction_received`: la API recibio la transferencia.
- `accounts_locked`: se bloquearon cuentas en PostgreSQL.
- `balances_updated`: se actualizaron saldos.
- `outbox_event_created`: se creo evento asincrono.
- `transaction_approved`: transferencia aprobada.
- `transaction_rejected`: transferencia rechazada.
- `database_error`: error de base de datos.

Estos logs permiten saber en que paso se encuentra una operacion.

### Logs del worker

El worker registra:

- `worker_started`: el worker esta corriendo.
- `outbox_event_processing`: empezo a procesar un evento.
- `ai_service_called`: llamo al servicio de IA.
- `outbox_event_processed`: termino correctamente.
- `outbox_event_failed`: fallo el procesamiento.

Esto permite diferenciar si un problema esta en el flujo principal o en el flujo secundario.

### Logs del servicio IA

El servicio IA registra:

- creacion de recomendaciones;
- `trace_id`;
- `transaction_id`;
- `model_version`;
- `category`;
- `risk_score`;
- `next_action`.

Esto permite auditar que recomendacion genero la IA mock.

### Metricas

Metricas principales:

```text
transactions_total{status="APPROVED"}
transactions_total{status="REJECTED"}
database_errors_total
transaction_duration_seconds
```

### Justificacion de observabilidad

Los datos seleccionados ayudan a diagnosticar problemas porque:

- `trace_id` permite seguir la solicitud entre componentes;
- `transaction_id` permite consultar la operacion financiera;
- `duration_ms` indica si una operacion fue lenta;
- `database_errors_total` muestra problemas con PostgreSQL;
- `transactions_total` muestra volumen transaccional;
- `outbox_events.status` muestra si el procesamiento asincrono esta sano;
- `last_error` explica por que fallo una tarea;
- `model_version`, `category` y `risk_score` ayudan a auditar IA.

## 3.5. Operaciones: Incidente Critico Simulado

### Monitoreo practico implementado

El monitoreo practico se encuentra en:

- `logs/api.log`;
- `logs/worker.log`;
- `logs/ai-service.log`;
- `logs/metrics.prom`;
- endpoint `/metrics`.

Para detectar lentitud:

- revisar `transaction_duration_seconds`;
- revisar `duration_ms` en `transaction_approved`;
- comparar eventos `transaction_received` y `transaction_approved`.

Para detectar problemas de base de datos:

- revisar `database_errors_total`;
- buscar `database_error` en `logs/api.log`;
- revisar logs del contenedor `postgres`.

Para detectar problemas asincronos:

- revisar `outbox_event_failed`;
- revisar eventos pendientes en `outbox_events`;
- revisar si el worker esta corriendo.

### Consultas utiles durante el incidente

Entrar a PostgreSQL:

```bash
docker compose exec postgres psql -U smartbancs -d smartbancs
```

Ver sesiones activas:

```sql
SELECT pid, state, wait_event_type, wait_event, query
FROM pg_stat_activity
WHERE datname = 'smartbancs';
```

Ver bloqueos:

```sql
SELECT locktype, relation::regclass, mode, granted
FROM pg_locks
WHERE database = (SELECT oid FROM pg_database WHERE datname = 'smartbancs');
```

Ver ultimas transacciones:

```sql
SELECT id, from_account_id, to_account_id, amount, status, failure_reason
FROM transactions
ORDER BY created_at DESC
LIMIT 10;
```

Ver eventos asincronos:

```sql
SELECT transaction_id, event_type, status, attempts, last_error
FROM outbox_events
ORDER BY created_at DESC
LIMIT 10;
```

### Acciones inmediatas teoricas

Si ocurre el incidente, las acciones inmediatas serian:

1. Confirmar impacto: revisar metricas, logs y cantidad de errores.
2. Identificar si el problema esta en API, PostgreSQL, worker o IA.
3. Si hay conexiones bloqueadas, identificar sesiones en PostgreSQL.
4. Cancelar consultas bloqueadas o procesos problematicos si es necesario.
5. Ajustar temporalmente pool de conexiones o recursos de base de datos.
6. Reiniciar worker si el problema esta en procesamiento asincrono.
7. Aumentar replicas de worker si hay backlog.
8. Reducir temporalmente tareas no criticas.
9. Priorizar que `POST /transactions` siga respondiendo.
10. Comunicar avance e impacto del incidente.

## 3.6. Operaciones: Gestion de Incidentes TI

### Estructura propuesta de post mortem

El informe incluiria:

- resumen del incidente;
- fecha y hora de inicio;
- fecha y hora de cierre;
- impacto en usuarios;
- cantidad de transacciones afectadas;
- servicios afectados;
- causa raiz;
- senales que permitieron detectarlo;
- acciones ejecutadas;
- que funciono;
- que no funciono;
- acciones correctivas;
- responsable;
- fecha compromiso.

### Acciones preventivas de infraestructura

- alertas por latencia;
- alertas por errores de base de datos;
- monitoreo de locks/deadlocks;
- revisar pool de conexiones;
- escalar API;
- escalar workers;
- pruebas de carga.

### Acciones preventivas de codigo

- mantener bloqueos en orden consistente;
- optimizar consultas;
- agregar índices;
- reintentos con backoff;
- idempotencia;
- pruebas de concurrencia;
- monitoreo de eventos PENDING o FAILED.