from backend.app.config import get_settings

settings = get_settings()
print(f"Data Directory: {settings.data_dir}")
print(f"Database Path: {settings.database_path}")
print(f"Database Exists: {settings.database_path.exists()}")

import sqlite3
if settings.database_path.exists():
    conn = sqlite3.connect(settings.database_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM documents")
    count = cursor.fetchone()[0]
    print(f"Document Count in {settings.database_path}: {count}")
    conn.close()
