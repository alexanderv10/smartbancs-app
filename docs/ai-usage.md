# Declaracion de Uso de Inteligencia Artificial

Durante el desarrollo del reto se utilizo asistencia de inteligencia artificial como apoyo tecnico y pedagogico.

La IA se uso para:

- interpretar el enunciado del reto;
- organizar los requisitos tecnicos;
- proponer una arquitectura inicial;
- generar una primera version del codigo;
- explicar conceptos como outbox, worker, IA mock, Prometheus y concurrencia;
- preparar pruebas automatizadas;
- redactar documentacion tecnica;
- preparar posibles respuestas para la sustentacion.

La IA no reemplazo la revision del candidato. La solucion fue ejecutada, probada y revisada localmente antes de considerarse terminada.

No se usaron datos reales de clientes, credenciales productivas ni informacion bancaria sensible. Los datos utilizados son ficticios y forman parte del ambiente de prueba del reto.

## Responsabilidad del candidato

El candidato es responsable de:

- entender y defender las decisiones tecnicas;
- explicar el flujo transaccional;
- demostrar el sistema funcionando;
- validar que el codigo ejecuta correctamente;
- reconocer las limitaciones del MVP.

## Consideracion etica

El uso de IA se hizo como herramienta de apoyo, similar a documentacion, busqueda tecnica o asistencia de desarrollo. La implementacion final, las pruebas y la defensa deben ser comprendidas por el candidato.

## Manejo del modelo de IA en produccion

En el MVP se usa una IA mock basada en reglas, no un modelo entrenado real. Aun asi, el diseno deja la separacion necesaria para reemplazar el mock por un servicio de IA productivo.

En produccion, el modelo deberia manejarse asi:

- Alimentacion de datos: usar datos transaccionales limpios y validados, incluyendo salidas del ETL.
- Versionamiento: registrar que version del modelo genero cada recomendacion.
- Data drift: monitorear si los datos actuales cambian frente a los datos historicos usados para entrenar.
- Calidad del modelo: medir si las recomendaciones siguen siendo utiles y coherentes.
- Recursos: monitorear latencia, errores, CPU, memoria y costo de ejecucion.
- Reentrenamiento: actualizar el modelo cuando los datos cambien o baje la calidad.
- Auditoria: guardar senales usadas, categoria, score y accion recomendada.

En el mock actual se simulan algunas de estas practicas con:

- `model_version`;
- `category`;
- `risk_score`;
- `next_action`;
- `features_used`;
- logs en `logs/ai-service.log`.
