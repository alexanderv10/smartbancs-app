# Incidente Critico Simulado

## Escenario

Durante un pico transaccional, por ejemplo quincena o pago masivo, usuarios reportan que las transferencias tardan demasiado o no se completan.

El monitoreo muestra:

- aumento de latencia en `POST /transactions`;
- timeouts contra PostgreSQL;
- posibles bloqueos o deadlocks;
- acumulacion de eventos en `outbox_events`;
- quejas de usuarios por transferencias lentas.

## Objetivo operativo

El objetivo principal es proteger el flujo financiero:

1. confirmar si las transferencias se estan aprobando o rechazando correctamente;
2. identificar si el cuello de botella esta en API, base de datos, worker o IA;
3. reducir impacto en usuarios;
4. evitar perdida o duplicidad de transacciones;
5. dejar evidencia para un post mortem.

## Senales a revisar

### API

Revisaria logs de la API:

```bash
docker compose logs --tail=100 api
```

Buscar eventos como:

- `transaction_received`;
- `transaction_approved`;
- `transaction_rejected`;
- `database_error`.

Tambien revisaria si un mismo `trace_id` muestra demora o error.

### Metricas

Revisaria `/metrics`:

```bash
curl http://localhost:8000/metrics
```

Metricas importantes:

- `transactions_total{status="APPROVED"}`;
- `transactions_total{status="REJECTED"}`;
- `database_errors_total`;
- `transaction_duration_seconds`.

Si `database_errors_total` sube, probablemente hay problema de base de datos o conexiones.

### PostgreSQL

Entraria a PostgreSQL:

```bash
docker compose exec postgres psql -U smartbancs -d smartbancs
```

Veria sesiones activas:

```sql
SELECT pid, state, wait_event_type, wait_event, query
FROM pg_stat_activity
WHERE datname = 'smartbancs';
```

Veria bloqueos:

```sql
SELECT locktype, relation::regclass, mode, granted
FROM pg_locks
WHERE database = (SELECT oid FROM pg_database WHERE datname = 'smartbancs');
```

Veria las ultimas transacciones:

```sql
SELECT id, from_account_id, to_account_id, amount, status, failure_reason
FROM transactions
ORDER BY created_at DESC
LIMIT 10;
```

Veria eventos asincronos pendientes:

```sql
SELECT transaction_id, event_type, status, attempts, last_error
FROM outbox_events
ORDER BY created_at DESC
LIMIT 10;
```

## Diagnostico inicial

Si la API tarda mucho antes de aprobar o rechazar, el problema probablemente esta en el flujo critico:

- bloqueo de cuentas;
- conexion a PostgreSQL;
- queries lentas;
- pool saturado;
- deadlocks.

Si la API responde bien, pero `processing-status` queda incompleto, el problema probablemente esta en el flujo secundario:

- worker detenido;
- IA mock lenta o caida;
- eventos acumulados en `outbox_events`.

## Acciones inmediatas

1. Confirmar si hay errores de base de datos en logs y metricas.
2. Revisar si hay consultas bloqueadas en PostgreSQL.
3. Revisar si el worker esta corriendo.
4. Revisar si los eventos en `outbox_events` estan en `PENDING`, `PROCESSING` o `PROCESSED`.
5. Pausar temporalmente tareas no criticas si estan afectando el sistema.
6. Priorizar que el endpoint `POST /transactions` siga respondiendo.
7. Comunicar impacto, alcance y avance del incidente.

## Mitigaciones temporales

Segun la causa, aplicaria:

- reiniciar worker si quedo detenido;
- aumentar replicas de worker si hay muchos eventos pendientes;
- reducir llamadas a servicios externos no criticos;
- aumentar recursos de base de datos;
- ajustar el pool de conexiones;
- activar reintentos con backoff;
- limitar temporalmente trafico si el sistema esta saturado.

## Acciones preventivas

Despues del incidente propondria:

- pruebas de carga antes de fechas de alto trafico;
- alertas por latencia alta;
- alertas por `database_errors_total`;
- alertas por eventos `PENDING` acumulados;
- revision de indices;
- revision de queries lentas;
- monitoreo de deadlocks;
- escalamiento horizontal de API y workers;
- separar aun mas trabajos no criticos del flujo transaccional.

## Post Mortem

El reporte incluiria:

- resumen del incidente;
- hora de inicio y fin;
- impacto en usuarios;
- cantidad de transferencias afectadas;
- causa raiz;
- que senales permitieron detectarlo;
- que acciones funcionaron;
- que acciones no funcionaron;
- acciones correctivas;
- responsable y fecha compromiso.

## Ejemplo de causa raiz

Una posible causa raiz seria:

> Durante un pico transaccional, varias solicitudes compitieron por modificar las mismas cuentas. Esto genero esperas en bloqueos de PostgreSQL, aumento de latencia en `POST /transactions` y acumulacion temporal de solicitudes. El sistema mantuvo consistencia de saldos, pero la experiencia de usuario se vio afectada por tiempos de respuesta altos.

La accion correctiva seria reforzar pruebas de carga, revisar estrategia de bloqueo, ajustar pool de conexiones y definir alertas tempranas.
