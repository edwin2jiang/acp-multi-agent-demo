import sys
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from acp_demo import registry
from acp_demo.demo_config import WORKER_CAPABILITIES, build_worker_manifest


class RegistryApiTests(unittest.TestCase):
    def setUp(self):
        with registry.agents_lock:
            registry.agents.clear()
        self.server = HTTPServer(("127.0.0.1", 0), registry.RegistryHandler)
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        with registry.agents_lock:
            registry.agents.clear()

    def test_register_lists_identical_workers_and_searches_by_common_capability(self):
        for worker_id in ["worker-1", "worker-2"]:
            manifest = build_worker_manifest(worker_id)
            response = requests.post(f"{self.base_url}/register", json=manifest, timeout=3)
            self.assertEqual(response.status_code, 200)

        agents_response = requests.get(f"{self.base_url}/agents", timeout=3)
        agents = agents_response.json()["agents"]
        self.assertEqual(len(agents), 2)
        self.assertEqual({agent["id"] for agent in agents}, {"worker-1", "worker-2"})
        self.assertTrue(all(agent["capabilities"] == WORKER_CAPABILITIES for agent in agents))

        search_response = requests.post(
            f"{self.base_url}/search",
            json={"capabilities": ["chat"]},
            timeout=3,
        )
        matches = search_response.json()["agents"]
        self.assertEqual({agent["id"] for agent in matches}, {"worker-1", "worker-2"})

    def test_register_accepts_empty_skill_list_for_workers(self):
        manifest = build_worker_manifest("worker-3")
        response = requests.post(f"{self.base_url}/register", json=manifest, timeout=3)
        self.assertEqual(response.status_code, 200)

        skills_response = requests.get(f"{self.base_url}/skills", timeout=3)
        self.assertEqual(skills_response.json(), {"skills": [], "count": 0})

    def test_invalid_json_returns_400(self):
        response = requests.post(
            f"{self.base_url}/register",
            data="{broken",
            headers={"Content-Type": "application/json"},
            timeout=3,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid JSON body", response.json()["error"])


if __name__ == "__main__":
    unittest.main()
