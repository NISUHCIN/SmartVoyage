import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.api_server import app


class ApiServerTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)

    def test_cities(self):
        res = self.client.get("/api/cities")
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(len(data), 34)
        self.assertTrue(any("北京" in item["cities"] for item in data))

    def test_agents(self):
        res = self.client.get("/api/agents")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["data"]), 5)

    def test_chat(self):
        res = self.client.post("/api/chat", json={"message": "北京今天天气", "session_id": "verify"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["code"], 0)
        self.assertTrue(body["data"]["reply"])


if __name__ == "__main__":
    unittest.main()
