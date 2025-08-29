import os
import unittest


class TestServerEndpoints(unittest.TestCase):
    def test_jobs_endpoints_import(self):
        try:
            from fastapi.testclient import TestClient  # type: ignore
            from src.coordination.server import app
        except Exception:
            self.skipTest("FastAPI not installed; skipping server tests")
            return

        if app is None:
            self.skipTest("Server app unavailable")
            return

        client = TestClient(app)

        # Optional auth token
        token = os.getenv("COORD_API_TOKEN")
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        # Create job
        r = client.post("/v1/jobs", json={"kind": "unit", "payload": {"a": 1}}, headers=headers)
        self.assertEqual(r.status_code, 201)
        jid = r.json()["id"]

        # Get job
        r = client.get(f"/v1/jobs/{jid}", headers=headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], jid)

        # Cancel job
        r = client.delete(f"/v1/jobs/{jid}", headers=headers)
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()

