import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from acp_demo.hermes_acp_client import HermesAcpClient, text_from_updates


class HermesAcpClientTests(unittest.TestCase):
    def test_client_launches_acp_agent_and_prompts_over_stdio(self):
        client = HermesAcpClient(
            command=[sys.executable, "-m", "acp_demo.worker_agent"],
            cwd=str(ROOT),
        )
        try:
            init = client.initialize()
            self.assertEqual(init.response["result"]["agentInfo"]["name"], "ACP Worker 1")

            session = client.new_session()
            session_id = session.response["result"]["sessionId"]

            result = client.prompt(session_id, "通过 ACP client 发送")
            self.assertEqual(result.response["result"]["stopReason"], "end_turn")
            self.assertIn("通过 ACP client 发送", text_from_updates(result.updates))
        finally:
            client.stop()

if __name__ == "__main__":
    unittest.main()
