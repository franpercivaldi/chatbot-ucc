# Admisiones UCC - Chatbot

Chatbot RAG para consultas de admisiones de la Universidad Católica de Córdoba.

## Arquitectura

- **Backend**: FastAPI + Python 3.11
- **Vector DB**: Qdrant
- **LLM**: Google Gemini (embeddings + generación)
- **Reranker**: BGE-reranker-base (cross-encoder)
- **Frontend**: React + Vite + TailwindCSS

## Requisitos

- Docker y Docker Compose
- Variable de entorno `GOOGLE_API_KEY` con tu API key de Google AI

---

## 🚀 Inicio rápido

### 1. Configurar variables de entorno

Crear archivo `.env` en la raíz o en `back/`:

```bash
GOOGLE_API_KEY=tu-api-key-de-google
ADMIN_API_KEY=tu-clave-admin-segura
```

### 2. Levantar los servicios

**Terminal 1** - Iniciar Docker:

```bash
docker compose up --build
```

Esto levanta:
- `back` en http://localhost:8000 (API FastAPI)
- `qdrant` en http://localhost:6333 (Vector DB)
- `front` en http://localhost:5173 (React app)

Esperá a ver los logs de warmup:
```
[warmup] cache schema ok
[warmup] qdrant ok
[warmup] embedder=ok reranker=ok
```

### 3. Ingestar datos

**Terminal 2** - Crear colección e indexar documentos:

```bash
# Bot público (admisiones)
curl -X POST "http://localhost:8000/ingest/xlsx?bot_id=public-admisiones" \
  -H "x-api-key: cambia-esto"

# Bot interno (académico) - opcional
curl -X POST "http://localhost:8000/ingest/xlsx?bot_id=interno-academico" \
  -H "x-api-key: cambia-esto"
```

Ver reporte de ingesta:
```bash
curl -s "http://localhost:8000/ingest/report?bot_id=public-admisiones" \
  -H "x-api-key: cambia-esto" | jq
```

---

## 💬 Usar el chat

### Consulta básica

```bash
curl -s -X POST http://localhost:8000/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "¿Cuánto cuesta la carrera de Odontología?",
    "bot_id": "public-admisiones",
    "session_id": "mi-sesion-1"
  }' | jq '.answer'
```

### Consulta con debug (ver retrieval)

```bash
curl -s -X POST http://localhost:8000/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Dame info de Odontología 2026",
    "bot_id": "public-admisiones",
    "session_id": "sess-debug",
    "debug": true
  }' | jq '{answer, intent: .retrieval_debug.intent, domains: .retrieval_debug.domains}'
```

### Conversación con contexto (multi-turno)

```bash
# Turno 1: establecer carrera
curl -s -X POST http://localhost:8000/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Quiero info de Abogacía",
    "bot_id": "public-admisiones",
    "session_id": "conv-123"
  }' | jq '.answer'

# Turno 2: pregunta de seguimiento (recuerda la carrera)
curl -s -X POST http://localhost:8000/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "¿Cuánto cuesta?",
    "bot_id": "public-admisiones",
    "session_id": "conv-123"
  }' | jq '.answer'

# Turno 3: otra pregunta sobre la misma carrera
curl -s -X POST http://localhost:8000/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "¿Y las fechas de inscripción?",
    "bot_id": "public-admisiones",
    "session_id": "conv-123"
  }' | jq '.answer'
```

### Streaming (Server-Sent Events)

```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Describime la carrera de Medicina",
    "bot_id": "public-admisiones",
    "session_id": "stream-1"
  }'
```

---

## 🤖 Bots disponibles

| Bot ID | Descripción | Dominios |
|--------|-------------|----------|
| `public-admisiones` | Bot público para futuros estudiantes | aranceles, becas, carreras, fechas, perfiles |
| `interno-academico` | Bot interno para personal UCC | reglamentos, RRHH, unidades académicas |

### Usar bot interno

```bash
curl -s -X POST http://localhost:8000/chat/ \
  -H "Content-Type: application/json" \
  -H "x-org-units: general,rrhh" \
  -d '{
    "message": "¿Cuál es el régimen de licencias?",
    "bot_id": "interno-academico",
    "session_id": "interno-1"
  }' | jq '.answer'
```

---

## 📊 Endpoints de métricas

```bash
# Top carreras consultadas
curl -s "http://localhost:8000/admin/metrics/top-carreras?days=30" | jq

# Dominios más consultados
curl -s "http://localhost:8000/admin/metrics/dominios" | jq

# Consultas sin respuesta (para mejorar)
curl -s "http://localhost:8000/admin/metrics/unanswered?limit=20" | jq

# Cache de embeddings (hit rate)
curl -s "http://localhost:8000/admin/metrics/embeddings-cache" | jq

# Cache de respuestas
curl -s "http://localhost:8000/admin/metrics/response-cache" | jq

# Query rewriter stats
curl -s "http://localhost:8000/admin/metrics/query-rewriter" | jq
```

---

## 🔧 Administración

### Borrar colección y re-ingestar

```bash
# Borrar colección de Qdrant
curl -X DELETE "http://localhost:6333/collections/admisiones"

# Re-ingestar
curl -X POST "http://localhost:8000/ingest/xlsx?bot_id=public-admisiones" \
  -H "x-api-key: tu-clave-admin-segura"
```

### Purgar cache de respuestas

```bash
# Ver stats
curl -s "http://localhost:8000/admin/metrics/response-cache" | jq

# Purgar todo el cache
curl -X DELETE "http://localhost:8000/admin/metrics/response-cache" | jq

# Purgar solo un bot
curl -X DELETE "http://localhost:8000/admin/metrics/response-cache?bot_id=public-admisiones" | jq
```

### Health check

```bash
curl -s http://localhost:8000/health/ | jq
```

---

## 📁 Estructura de datos

```
data/
├── xlsx/
│   └── public-admisiones/     # Excel para bot público
│       ├── aranceles.xlsx
│       ├── carreras.xlsx
│       └── ...
├── docs/
│   └── interno-academico/     # PDFs/docs para bot interno
│       ├── reglamentos/
│       └── rrhh/
└── normalized/                 # CSVs normalizados
    ├── carreras.csv
    └── aranceles_carreras.csv
```

---

## 🐛 Debugging

### Ver logs en tiempo real

```bash
docker compose logs -f back
```

### Consulta con debug completo

```bash
curl -s -X POST http://localhost:8000/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "¿Cuánto sale Medicina?",
    "bot_id": "public-admisiones",
    "session_id": "debug-1",
    "debug": true
  }' | jq '.retrieval_debug'
```

Campos útiles en `retrieval_debug`:
- `intent`: intención detectada (montos, fechas, info_carrera, etc.)
- `domains`: dominios de los documentos recuperados
- `search_query`: query reescrita para búsqueda
- `fallback_used`: si se relajaron filtros por pocos resultados
- `cache_hit`: si la respuesta vino de cache

---

## ⚙️ Configuración

Variables de entorno principales (en `back/.env` o docker-compose):

| Variable | Default | Descripción |
|----------|---------|-------------|
| `GOOGLE_API_KEY` | - | API key de Google AI (requerida) |
| `ADMIN_API_KEY` | `cambia-esto` | Clave para endpoints admin |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Modelo de generación |
| `RAG_TOP_K` | `30` | Docs a recuperar de Qdrant |
| `RAG_RERANK_K` | `5` | Docs finales post-rerank |
| `ENABLE_RESPONSE_CACHE` | `true` | Cache de respuestas |
| `ENABLE_RERANKER` | `true` | Usar cross-encoder reranker |
