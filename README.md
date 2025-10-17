admisiones-chatbot monorepo

Estructura creada automáticamente. Contiene un servicio `back` con FastAPI y un `docker-compose.yml` que levanta `back` y `qdrant`.

* Para levantarlo usar `docker compose up --build` en una consola

# crea colección e indexa
curl -X POST "http://localhost:8000/ingest/xlsx?bot_id=public-admisiones" \
  -H "x-api-key: cambia-esto"

-> Con esto lo que hacemos es la ingesta de la data, el bot_id, puede ser:
* public-admisiones
* interno-academico

Esto para embeber los distintos xlsx, dependiendo a que bot esta dirigida cada data

Desde una segunda consola podemos probar el chat con:
```
# Turno 1 — fija contexto
curl -s -X POST http://localhost:8000/chat/ -H "Content-Type: application/json" -d '{
  "message": "Dame info de Odontología 2026",
  "bot_id": "public-admisiones",
  "session_id": "sess-123",
  "debug": true
}' | jq '{answer, debug:.retrieval_debug}'

# Turno 2 — debería aparecer "aranceles" en debug.domains y citar tu CSV de aranceles
curl -s -X POST http://localhost:8000/chat/ -H "Content-Type: application/json" -d '{
  "message": "¿Qué valor tiene?",
  "bot_id": "public-admisiones",
  "session_id": "sess-123",
  "debug": true
}' | jq '{answer, debug:.retrieval_debug}'
```
