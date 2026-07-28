from backend.app.main import create_app
from fastapi.testclient import TestClient

app = create_app()
client = TestClient(app)

response = client.get("/api/documents")
print(f"Status Code: {response.status_code}")
print(f"Response: {response.json()}")

# Also try with explicit parameters
response2 = client.get("/api/documents?page=1&page_size=25")
print(f"\nWith parameters:")
print(f"Status Code: {response2.status_code}")
print(f"Response: {response2.json()}")
