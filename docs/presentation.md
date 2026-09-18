# Guion de Defensa Tecnica

## 0:00 a 0:30 Problema

SmartBancs App procesa transferencias en tiempo real y genera recomendaciones financieras. El reto principal es responder rapido sin saturar Bancs, que representa el core bancario legado.

## 0:30 a 1:20 Arquitectura

La solucion separa el flujo critico del flujo secundario. La API procesa la transferencia con PostgreSQL y guarda un evento en `outbox_events`. Luego un worker asincrono consume ese evento para llamar al servicio de IA y sincronizar con Bancs mock.

## 1:20 a 2:10 Demo

Mostrar:

- `docker compose up --build`;
- `POST /transactions`;
- consulta de cuenta actualizada;
- logs con `trace_id`;
- worker procesando IA y Bancs;
- endpoint `/metrics`.

## 2:10 a 2:40 Observabilidad e incidente

La solucion registra eventos criticos, expone metricas y usa `trace_id` para seguir una transaccion. En un incidente de latencia o deadlocks revisaria metricas, logs, conexiones bloqueadas y queries lentas.

## 2:40 a 3:00 Cierre

La decision tecnica principal fue proteger el flujo transaccional: las transferencias se procesan de forma consistente y rapida, mientras IA y Bancs se ejecutan de forma asincrona para evitar bloqueos y saturacion del sistema legado.
