# Arquitectura SmartBancs App

## Objetivo

SmartBancs App es un MVP para procesar transferencias financieras y generar recomendaciones mediante un servicio de IA mock sin afectar el tiempo de respuesta del flujo transaccional principal.

La idea central es separar dos caminos:

- flujo critico: validar la transferencia, mover el saldo y responder rapido;
- flujo secundario: generar recomendacion de IA despues de aprobada la transferencia.

## Alcance del MVP

El proyecto demuestra:

- API transaccional con FastAPI;
- persistencia en PostgreSQL;
- control de concurrencia sobre saldos;
- patron outbox para tareas asincronas;
- worker en segundo plano;
- servicio de IA mock avanzado;
- logs estructurados con `trace_id`;
- metricas tipo Prometheus en `/metrics`;
- ETL simple para limpiar transacciones historicas;
- pruebas automatizadas de validacion y flujo transaccional.

## Componentes

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

### API de transacciones

La API es el punto de entrada principal. Expone endpoints para:

- revisar salud del servicio con `GET /health`;
- consultar cuentas con `GET /accounts/{account_id}`;
- crear transferencias con `POST /transactions`;
- consultar una transaccion con `GET /transactions/{transaction_id}`;
- consultar el procesamiento asincrono con `GET /transactions/{transaction_id}/processing-status`;
- ver metricas con `GET /metrics`.

Su responsabilidad principal es proteger el flujo financiero. Por eso valida datos, bloquea las cuentas involucradas, mueve saldos y registra la transaccion dentro de una transaccion de base de datos.

### PostgreSQL

PostgreSQL es la fuente de verdad del MVP. Guarda:

- `accounts`: cuentas y saldos actuales;
- `transactions`: historial de transferencias aprobadas y rechazadas;
- `outbox_events`: eventos pendientes o procesados por el worker;
- `recommendations`: recomendaciones generadas por IA mock.

### Worker asincrono

El worker revisa periodicamente la tabla `outbox_events`. Cuando encuentra un evento pendiente, ejecuta la tarea que no debe bloquear al usuario:

1. llama al servicio de IA mock;
2. guarda la recomendacion;
3. marca el evento como `PROCESSED`.

Este diseno demuestra que la API puede responder rapido mientras el procesamiento de IA ocurre en segundo plano.

### IA mock

El servicio de IA mock simula una recomendacion financiera. En un ambiente real podria reemplazarse por un modelo real o por una API externa.

En este MVP la recomendacion se basa en el monto de la transferencia. El mock devuelve:

- mensaje de recomendacion;
- categoria de transferencia;
- `risk_score`;
- `model_version`;
- `next_action`;
- senales usadas para la decision.

Esto permite demostrar una integracion mas cercana a un servicio de IA real sin depender de un proveedor externo.

## Estrategia teorica de integracion con Bancs

El enunciado menciona Bancs como un core bancario legado robusto, pero sensible a un alto volumen de consultas directas. En este MVP no se implementa un servicio `bancs-mock`, porque la parte practica se enfoca en el backend transaccional, la IA asincrona, el ETL y la observabilidad.

La estrategia propuesta para un ambiente real seria no llamar a Bancs dentro del flujo principal de `POST /transactions`. En su lugar, SmartBancs procesaria la transferencia en su propia base operativa y dejaria un evento persistido para sincronizacion posterior.

Flujo teorico:

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

Esta estrategia evita saturar Bancs porque:

- la respuesta al usuario no depende de la latencia del core legado;
- los eventos quedan persistidos y pueden reintentarse si Bancs no esta disponible;
- se puede controlar la velocidad de sincronizacion hacia Bancs;
- se puede monitorear el backlog de eventos pendientes;
- se reduce el riesgo de degradar el sistema legado durante picos transaccionales.

En una implementacion productiva, la sincronizacion con Bancs podria hacerse con un worker dedicado, una cola de mensajes o un bus de eventos. Tambien seria necesario definir idempotencia para evitar duplicados, reintentos con backoff, alertas por fallos de sincronizacion y conciliacion periodica de saldos.

## Ciclo de vida del modelo de IA

En este MVP la IA es un mock funcional basado en reglas. Sin embargo, en produccion el ciclo de vida del modelo deberia incluir:

1. Alimentacion de datos: usar datos historicos limpios, como los generados por el ETL, junto con informacion transaccional validada.
2. Entrenamiento y versionamiento: entrenar modelos en ambientes controlados y registrar versiones como `model_version`.
3. Validacion: medir calidad del modelo antes de publicarlo, revisando precision, sesgos, falsos positivos y comportamiento por segmentos.
4. Despliegue controlado: publicar nuevas versiones gradualmente para reducir riesgo.
5. Monitoreo de data drift: comparar datos actuales contra datos usados en entrenamiento para detectar cambios en patrones de transaccion.
6. Monitoreo operativo: revisar latencia, errores, consumo de CPU/memoria y tiempos de respuesta del servicio IA.
7. Reentrenamiento: actualizar el modelo cuando el drift o la perdida de calidad lo justifiquen.
8. Auditoria: guardar version del modelo, senales usadas, categoria y score para explicar por que se genero una recomendacion.

El MVP ya refleja algunas de estas ideas mediante `model_version`, `category`, `risk_score`, `next_action`, `features_used` y logs del servicio IA.

## Flujo de transferencia aprobada

1. El cliente envia `POST /transactions`.
2. La API genera un `trace_id`.
3. La API valida que el monto sea positivo.
4. La API abre una transaccion de PostgreSQL.
5. La API bloquea las cuentas involucradas con `SELECT ... FOR UPDATE`.
6. Las cuentas se bloquean en orden por `account_id` para reducir riesgo de deadlocks.
7. La API valida que las cuentas existan y esten activas.
8. La API valida que la cuenta origen tenga saldo suficiente.
9. La API descuenta el saldo de la cuenta origen.
10. La API acredita el saldo en la cuenta destino.
11. La API guarda la transaccion como `APPROVED`.
12. La API crea un evento `TRANSACTION_APPROVED` en `outbox_events`.
13. La API responde al cliente sin esperar a la IA.
14. El worker toma el evento y ejecuta la IA mock en segundo plano.
15. El worker guarda la recomendacion y marca el evento como `PROCESSED`.

## Flujo de transferencia rechazada

Si la transferencia no cumple una regla, por ejemplo fondos insuficientes:

1. La API recibe la solicitud.
2. La API genera un `trace_id`.
3. La API valida las cuentas y el saldo.
4. La API guarda la transaccion como `REJECTED`.
5. La API responde con `message: "Insufficient funds"`.
6. No se crea evento en `outbox_events`.
7. El worker no procesa nada para esa transaccion.
8. No se llama a IA mock.

Esto evita trabajo innecesario para operaciones que no fueron aprobadas.

## Concurrencia

El problema de concurrencia aparece cuando dos solicitudes intentan modificar las mismas cuentas al mismo tiempo.

Para proteger el saldo se usan transacciones ACID de PostgreSQL y bloqueo de filas:

```sql
SELECT id, balance, status
FROM accounts
WHERE id = ANY(:account_ids)
ORDER BY id
FOR UPDATE;
```

`FOR UPDATE` bloquea las filas seleccionadas hasta que termina la transaccion. Asi, si dos transferencias quieren tocar la misma cuenta, una espera a que la otra termine antes de leer y modificar el saldo.

El `ORDER BY id` ayuda a que las cuentas siempre se bloqueen en el mismo orden. Esto reduce el riesgo de deadlocks, porque evita que una transaccion bloquee primero la cuenta 1 y otra bloquee primero la cuenta 2 en sentido contrario.

## Alta concurrencia

El enunciado menciona picos altos, por ejemplo 10 000 transacciones por segundo. En este MVP no se demuestra localmente que el computador soporte 10 000 TPS reales.

Lo que se demuestra es el diseno para acercarse a ese objetivo:

- el flujo critico hace solo lo necesario;
- la IA queda fuera del camino principal;
- el worker permite procesar tareas secundarias en paralelo;
- PostgreSQL protege consistencia de saldos;
- las metricas permiten medir latencia, errores y volumen;
- el patron outbox permite no perder eventos aunque el worker falle temporalmente.

En produccion se complementaria con pruebas de carga, escalamiento horizontal de API y workers, pool de conexiones, replicas, particionado o colas dedicadas segun el volumen real.

## Observabilidad

La aplicacion usa tres mecanismos:

- logs estructurados en JSON;
- metricas en `/metrics`;
- identificadores `transaction_id` y `trace_id`.

`transaction_id` identifica la transferencia como operacion de negocio. Sirve como comprobante o llave para consultar esa transferencia.

`trace_id` identifica el recorrido tecnico de una solicitud. Sirve para buscar en logs todo lo que paso con esa peticion entre API, worker e IA.

Metricas principales:

- `transactions_total{status="APPROVED"}`;
- `transactions_total{status="REJECTED"}`;
- `database_errors_total`;
- `transaction_duration_seconds`.

## ETL

El componente ETL limpia un archivo CSV crudo ubicado en:

```text
etl/data/raw_transactions.csv
```

Genera una salida normalizada en:

```text
etl/data/clean_transactions.csv
```

Este proceso representa una version simple de preparacion de datos para analitica o futuros modelos de IA.

## Pruebas

Las pruebas automatizadas cubren:

- validaciones de entrada;
- monto invalido;
- cuenta inexistente;
- fondos insuficientes;
- transferencia aprobada;
- actualizacion de saldos;
- creacion de evento outbox para transferencias aprobadas.

Las pruebas usan un esquema separado de base de datos para no afectar datos de demo.

## Limitaciones del MVP

Al ser un MVP, hay decisiones simplificadas:

- la IA es una simulacion;
- el worker usa polling simple sobre la tabla outbox;
- no hay autenticacion ni autorizacion;
- no hay pruebas de carga reales a 10 000 TPS;
- no hay despliegue cloud ni infraestructura como codigo completa.

Estas limitaciones son aceptables para el alcance del reto, porque el objetivo principal es demostrar arquitectura, consistencia transaccional, asincronia, observabilidad y capacidad de explicacion tecnica.
