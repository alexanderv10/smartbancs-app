# Arquitectura SmartBancs App

## Objetivo

SmartBancs App procesa transferencias en tiempo real y genera recomendaciones financieras sin afectar el tiempo de respuesta del flujo transaccional principal.

## Componentes

La solucion se compone de cinco servicios:

- API de transacciones: recibe, valida y procesa transferencias.
- PostgreSQL: guarda cuentas, transacciones, eventos pendientes, recomendaciones y sincronizaciones con Bancs.
- Worker asincrono: procesa eventos secundarios despues de aprobada la transaccion.
- IA mock: simula recomendaciones financieras personalizadas.
- Bancs mock: simula el core bancario legado.

## Flujo de transferencia

1. El cliente envia `POST /transactions`.
2. La API genera un `trace_id`.
3. La API valida cuentas y monto.
4. La API abre una transaccion de base de datos.
5. La API bloquea las cuentas involucradas con `SELECT ... FOR UPDATE`.
6. Las cuentas se bloquean en orden fijo por `account_id` para reducir riesgo de deadlocks.
7. La API valida saldo, descuenta de la cuenta origen y acredita en la cuenta destino.
8. La API guarda la transaccion como `APPROVED`.
9. La API guarda un evento en `outbox_events`.
10. La API responde al cliente sin esperar a IA ni Bancs.
11. El worker toma el evento y llama a IA y Bancs mock.
12. El worker guarda la recomendacion y registra la sincronizacion.

## Integracion con Bancs

Bancs representa un sistema legado robusto pero sensible a alta carga. Por eso la API no consulta Bancs directamente en cada solicitud. La integracion se realiza de forma asincrona mediante eventos persistidos en `outbox_events`.

Esta decision permite:

- proteger Bancs de picos transaccionales;
- responder al usuario en menos de 2 segundos;
- reintentar sincronizaciones fallidas;
- auditar que transacciones ya fueron enviadas al core legado.

## Concurrencia

El saldo se protege con transacciones ACID de PostgreSQL. Para cada transferencia se bloquean las filas de las cuentas involucradas:

```sql
SELECT id, balance, status
FROM accounts
WHERE id = ANY(:account_ids)
ORDER BY id
FOR UPDATE;
```

El orden fijo de bloqueo evita que dos transferencias tomen las mismas cuentas en orden contrario, que es una causa comun de deadlocks.

## IA

La IA se implementa como un mock funcional separado. En produccion podria reemplazarse por un modelo real o por una API administrada. Su ciclo de vida deberia incluir:

- alimentacion con datos limpios provenientes de procesos ETL;
- monitoreo de calidad, latencia, errores y consumo de recursos;
- monitoreo de data drift para detectar cambios en los patrones de transaccion;
- versionamiento de modelos y despliegues controlados.

## Observabilidad

La API expone:

- logs estructurados en JSON;
- metricas Prometheus en `/metrics`;
- `trace_id` por transaccion.

Eventos clave registrados:

- `transaction_received`;
- `transaction_approved`;
- `transaction_rejected`;
- `database_error`;
- `ai_service_called`;
- `bancs_sync_completed`.
