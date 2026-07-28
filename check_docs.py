import sqlite3
from pathlib import Path

db_path = Path("backend/data/rag.sqlite3")
if db_path.exists():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT id, filename, status, enrichment_status FROM documents")
    docs = cursor.fetchall()

    print("=== Documents in Database ===")
    if docs:
        for doc in docs:
            print(f"\nID: {doc['id']}")
            print(f"  Filename: {doc['filename']}")
            print(f"  Status: {doc['status']}")
            print(f"  Enrichment Status: {doc['enrichment_status']}")
    else:
        print("No documents found")

    conn.close()
else:
    print("Database not found!")
