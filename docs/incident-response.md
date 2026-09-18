# Incidente Critico Simulado

## Escenario

Durante un pico transaccional de quincena, usuarios reportan que las transferencias no se completan. El monitoreo muestra incremento severo de latencia, timeouts contra la base de datos y posibles deadlocks.

## Como detectarlo

Revisaria:

- latencia de `POST /transactions`;
- conteo de errores `database_errors_total`;
- logs con `trace_id` para ubicar transacciones lentas;
- consultas bloqueadas en PostgreSQL;
- uso del pool de conexiones;
- eventos `outbox_events` acumulados;
- errores del worker al sincronizar con IA o Bancs.

## Acciones inmediatas

1. Identificar consultas bloqueadas y sesiones con mayor tiempo de espera.
2. Finalizar conexiones bloqueadas si estan afectando el procesamiento principal.
3. Reducir temporalmente procesos no criticos, como recomendaciones de IA.
4. Aumentar replicas de la API si el cuello de botella esta en computo.
5. Ajustar de forma controlada el pool de conexiones.
6. Activar reintentos con backoff para errores transitorios.
7. Comunicar impacto y estado a los interesados.

## Post mortem

El informe post mortem incluiria:

- resumen del incidente;
- impacto en usuarios;
- linea de tiempo;
- causa raiz;
- senales de monitoreo disponibles;
- que funciono;
- que no funciono;
- acciones correctivas;
- responsables y fechas.

## Acciones preventivas

- pruebas de carga antes de fechas de alto trafico;
- indices para consultas criticas;
- limites de concurrencia por servicio;
- alertas tempranas de latencia, deadlocks y pool saturado;
- revision de queries lentas;
- mantener procesos no criticos fuera del flujo transaccional;
- simulacros periodicos de incidentes.
