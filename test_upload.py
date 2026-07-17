import requests
from pathlib import Path

# Create a simple test PNG file
test_dir = Path("test_files")
test_dir.mkdir(exist_ok=True)

# Create a minimal PNG file
png_bytes = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00'
    b'\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc'
    b'\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\r\xd2d\x00\x00\x00\x00IEND\xaeB`\x82'
)

test_file = test_dir / "test.png"
test_file.write_bytes(png_bytes)

# Test the upload endpoint
with open(test_file, "rb") as f:
    files = {"file": ("test.png", f, "image/png")}
    response = requests.post("http://localhost:8000/api/brs/upload", files=files)

print(f"Status Code: {response.status_code}")
print(f"Response: {response.json()}")
