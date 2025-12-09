
import sys
import os
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

# Hardcode settings for debug to avoid import issues
QDRANT_URL = "http://localhost:6333"
QDRANT_COLLECTION = "admisiones"

print(f"Connecting to {QDRANT_URL}...")
client = QdrantClient(url=QDRANT_URL)

print(f"Checking collection: {QDRANT_COLLECTION}")
try:
    info = client.get_collection(QDRANT_COLLECTION)
    print(f"Points count: {info.points_count}")
except Exception as e:
    print(f"Error getting collection info: {e}")
    sys.exit(1)

# Check specifically for 'perfiles' domain
print("\n--- Searching for domain='perfiles' ---")

f = Filter(
    must=[
        FieldCondition(key="domain", match=MatchValue(value="perfiles"))
    ]
)

try:
    points, _ = client.scroll(
        collection_name=QDRANT_COLLECTION,
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

except Exception as e:
    print(f"Error searching: {e}")
