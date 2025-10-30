admisiones-chatbot backend

Setup

1. Create a virtualenv and install requirements:

   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

2. Run the app:

   uvicorn app.main:app --reload

3. How to ingest data

```
   curl -X POST "http://localhost:8000/ingest/run?bot_id=public-admisiones&source=all" \
     -H "x-api-key: cambia-esto" | jq .
```

```
curl -X POST "http://localhost:8000/ingest/run?bot_id=interno-academico&source=docs" \
  -H "x-api-key: cambia-esto" | jq .
```

Preview:
```
curl "http://localhost:8000/ingest/preview?bot_id=interno-academico&source=docs&sample_size=12" \
  | jq '.sample[] | {file:.metadata.fuente_archivo, org:.metadata.org_unit, is_table:.metadata.is_table, page:.metadata.page_from, domain:.metadata.domain, has_numbers:(.metadata.numbers!=null)}'
```

4. Chat
```
curl -s -X POST "http://localhost:8000/chat/" \
  -H "Content-Type: application/json" \
  -H "X-Org-Units: rrhh,general" \
  -d '{
    "message": "¿Cómo me inscribo a una adscripción? requisitos y plazos",
    "bot_id": "interno-academico",
    "session_id": "sess-rrhh",
    "debug": true
  }' | jq '{answer, debug:.retrieval_debug}'
```

* Notemos que le pasamos rrhh, general, esto es para filtrar por contexto cuando se haga el retriever (EL BOT PUBLICO NO NECESITA)

