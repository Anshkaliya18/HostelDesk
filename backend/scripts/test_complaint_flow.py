"""Ad-hoc end-to-end test: submit a complaint as the seeded demo student (id 1)."""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

BASE = "http://127.0.0.1:8000"

# 1x1 transparent PNG
PNG = base64_png = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6260000000060002"
    "3021b0210000000049454e44ae426082"
)

print("GET /health:", end=" ")
r = httpx.get(f"{BASE}/health", timeout=10)
print(r.status_code, r.json())

print("GET /v1/models (to confirm it stays 404):", end=" ")
try:
    r = httpx.get(f"{BASE}/v1/models", timeout=10)
    print(r.status_code, r.json())
except Exception as exc:
    print(exc)

print("GET /complaints (would need warden):", end=" ")
try:
    r = httpx.get(f"{BASE}/complaints", headers={"X-User-Id": "1"}, timeout=10)
    print(r.status_code, r.json())
except Exception as exc:
    print(exc)

# Multipart submit exactly like browser FormData (no manual content-type)
files = [("photo", ("fan-test.png", io.BytesIO(PNG), "image/png"))]
data = {
    "description": "Fan is not working - automated test submission",
    "block": "A",
    "room": "101",
}
print("POST /complaints:", end=" ")
r = httpx.post(
    f"{BASE}/complaints",
    data=data,
    files=files,
    headers={"X-User-Id": "1", "Accept": "application/json"},
    timeout=180,
)
print(r.status_code)
body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
print(body)
