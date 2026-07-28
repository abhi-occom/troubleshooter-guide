import sqlite3
from pathlib import Path

conn = sqlite3.connect("backend/data/rag.sqlite3")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT id, filename, status, created_at FROM documents ORDER BY created_at DESC LIMIT 3")
docs = cursor.fetchall()

print("=== Latest 3 Documents ===")
for doc in docs:
    print(f"\nID: {doc['id']}")
    print(f"  Filename: {doc['filename']}")
    print(f"  Status: {doc['status']}")
    print(f"  Created: {doc['created_at']}")

conn.close()
