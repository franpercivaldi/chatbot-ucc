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
   curl -X POST "http://localhost:8000/ingest/xlsx?bot_id=public-admisiones" \
   -H "x-api-key: <ADMIN_API_KEY>"

```