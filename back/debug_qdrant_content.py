
import sys
import os
from qdrant_client import QdrantClient

# Add back/app to path to import config if needed, or just hardcode
sys.path.append(os.path.join(os.getcwd(), 'back'))

from app.config import settings

client = QdrantClient(url=settings.QDRANT_URL)
collection_name = settings.QDRANT_COLLECTION

print(f"Checking collection: {collection_name}")
try:
    info = client.get_collection(collection_name)
    print(f"Points count: {info.points_count}")
except Exception as e:
    print(f"Error getting collection info: {e}")
    sys.exit(1)

# Scroll some points
print("\n--- Sample Points ---")
points, next_page = client.scroll(
    collection_name=collection_name,
    limit=5,
    with_payload=True,
    with_vectors=False
)

for p in points:
    print(f"ID: {p.id}")
    print(f"Payload: {p.payload}")
    print("-" * 20)

# Check specifically for 'perfiles' domain
print("\n--- Searching for domain='perfiles' ---")
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

f = Filter(
    must=[
        FieldCondition(key="domain", match=MatchValue(value="perfiles"))
    ]
)

points, _ = client.scroll(
    collection_name=collection_name,
    scroll_filter=f,
    limit=5,
    with_payload=True
)

if points:
    print(f"Found {len(points)} points in 'perfiles'")
    for p in points:
        print(f"ID: {p.id}")
        print(f"Payload keys: {list(p.payload.keys())}")
        print(f"Carrera: {p.payload.get('carrera')}")
else:
    print("No points found in 'perfiles'")
