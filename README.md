admisiones-chatbot monorepo

Estructura creada automáticamente. Contiene un servicio `back` con FastAPI y un `docker-compose.yml` que levanta `back` y `qdrant`.

* Para levantarlo usar `docker compose up --build` en una consola

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
