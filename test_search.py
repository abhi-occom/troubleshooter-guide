from backend.app.config import get_settings
from backend.app.database import Database

settings = get_settings()
db = Database(settings.database_path)
db.initialize()

result = db.search_documents(
    search="",
    status=None,
    enrichment_status=None,
    feature=None,
    topic=None,
    sort="created_at",
    direction="desc",
    page=1,
    page_size=25,
)

print(f"search_documents() returned:")
print(f"  total: {result['total']}")
print(f"  items count: {len(result['items'])}")
print(f"  total_pages: {result['total_pages']}")
print(f"\nItems:")
for item in result['items']:
    print(f"  - {item['id']}: {item['filename']} (status: {item['status']})")
