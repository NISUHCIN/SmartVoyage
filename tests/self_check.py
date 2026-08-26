import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.api_server import app

client = TestClient(app)

for message in ["北京三日游", "云南五日游"]:
    print(">>>", message)
    try:
        res = client.post("/api/chat", json={"message": message, "session_id": "self-check"})
        body = res.json()
        print("HTTP", res.status_code)
        print(json.dumps(body, ensure_ascii=False, indent=2)[:2500])
    except Exception as e:
        print("EXCEPTION", repr(e))
