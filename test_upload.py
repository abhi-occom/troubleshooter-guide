import requests
from pathlib import Path

pdf_path = Path(r"c:\Users\IS-ABHISHEK-IN\Desktop\ASUS-AX1800-RT-AX52.pdf")

if not pdf_path.exists():
    print(f"File not found: {pdf_path}")
else:
    print(f"File found: {pdf_path}")
    print(f"File size: {pdf_path.stat().st_size} bytes")

    # Try to upload
    with open(pdf_path, "rb") as f:
        files = {"file": (pdf_path.name, f, "application/pdf")}
        try:
            response = requests.post("http://localhost:8000/api/documents", files=files, timeout=10)
            print(f"\nUpload Response:")
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.json()}")
        except Exception as e:
            print(f"Error: {e}")
