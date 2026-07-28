import sqlite3

conn = sqlite3.connect("backend/data/rag.sqlite3")
cursor = conn.cursor()

print("=== All Tables ===")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
for table in tables:
    print(f"  - {table[0]}")

print("\n=== Documents Table ===")
cursor.execute("SELECT id, filename, status FROM documents")
docs = cursor.fetchall()
print(f"Total documents: {len(docs)}")
for doc in docs:
    print(f"  {doc[0]}: {doc[1]} (status: {doc[2]})")

print("\n=== Checking services.list_documents() ===")
from backend.app.config import get_settings
from backend.app.database import Database

settings = get_settings()
db = Database(settings.database_path)
db.initialize()

result = db.list_documents()
print(f"db.list_documents() returned: {len(result)} documents")
for doc in result:
    print(f"  {doc}")

conn.close()
