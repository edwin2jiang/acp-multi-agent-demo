import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from acp_demo.pool_client import StickyConversationPool, WorkerHandle


class StickyConversationPoolTests(unittest.TestCase):
    def setUp(self):
        self.processes = []
        self.workers = []
        for index in [1, 2]:
            worker_id = f"worker-{index}"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(SRC)
            env["ACP_WORKER_ID"] = worker_id
            env["ACP_PROMPT_DELAY"] = "0.01"
            env["REGISTRY_URL"] = "http://127.0.0.1:9"
            process = subprocess.Popen(
                [sys.executable, "-m", "acp_demo.worker_agent"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
            )
            self.processes.append(process)
            self.workers.append(WorkerHandle(worker_id, process))
        time.sleep(0.2)

    def tearDown(self):
        for process in self.processes:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe:
                    pipe.close()

    def test_conversation_is_sticky_to_original_worker(self):
        pool = StickyConversationPool(self.workers, cwd=str(ROOT))

        first = pool.prompt("chat-a", "第一轮")
        second = pool.prompt("chat-b", "另一个会话")
        third = pool.prompt("chat-a", "第二轮")

        self.assertEqual(first["worker_id"], "worker-1")
        self.assertEqual(second["worker_id"], "worker-2")
        self.assertEqual(third["worker_id"], "worker-1")
        self.assertEqual(first["acp_session_id"], third["acp_session_id"])
        self.assertEqual(pool.assignment_snapshot(), {
            "chat-a": "worker-1",
            "chat-b": "worker-2",
        })


if __name__ == "__main__":
    unittest.main()
