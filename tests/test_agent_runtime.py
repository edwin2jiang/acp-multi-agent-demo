import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from acp_demo.agent_runtime import StdioAgentRuntime
from acp_demo.demo_config import build_worker_manifest


class CapturingRuntime(StdioAgentRuntime):
    def __init__(self, manifest):
        super().__init__(manifest)
        self.messages = []

    def write_message(self, message):
        self.messages.append(message)


class AgentRuntimeTests(unittest.TestCase):
    def test_prompt_emits_worker_identity_and_session_state(self):
        runtime = CapturingRuntime(build_worker_manifest("worker-7"))

        init_response = runtime.handle_request({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        })
        self.assertEqual(init_response["result"]["agentInfo"]["name"], "ACP Worker 7")

        session_response = runtime.handle_request({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/new",
            "params": {"cwd": str(ROOT)},
        })
        session_id = session_response["result"]["sessionId"]

        final_response = runtime.handle_request({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "session/prompt",
            "params": {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "继续这个会话"}],
            },
        })

        self.assertEqual(final_response["result"]["stopReason"], "end_turn")
        self.assertEqual(len(runtime.messages), 1)
        update = runtime.messages[0]
        self.assertEqual(update["method"], "session/update")
        text = update["params"]["update"]["content"]["text"]
        self.assertIn("worker_id=worker-7", text)
        self.assertIn(f"session_id={session_id}", text)
        self.assertIn("已处理轮次: 1", text)


if __name__ == "__main__":
    unittest.main()
