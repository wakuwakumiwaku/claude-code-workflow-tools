"""Exercise hooks only in a synthetic HOME; no live Claude process is used."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class QueueCollisionTests(unittest.TestCase):
    def invoke(self, home, hook, prompt):
        result = subprocess.run(["bash", str(ROOT / "claudetools/hooks" / hook)],
                                input=json.dumps({"prompt": prompt}), text=True,
                                capture_output=True, cwd=home,
                                env=dict(os.environ, HOME=str(home)), timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            self.fail("Hook must return valid JSON: " + result.stdout + result.stderr)

    def test_reusing_queue_name_preserves_original_task_and_order(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.invoke(home, "queue-hook.sh", "$queue task original prompt")
            self.invoke(home, "queue-hook.sh", "$queue later second prompt")
            queue = home / ".claude/queue-order.txt"
            original_order = queue.read_bytes()
            response = self.invoke(home, "queue-hook.sh", "$queue task replacement prompt")
            original = home / ".claude/pending-prompts/task.txt"
            self.assertEqual(original.read_text(), "original prompt\n", "Duplicate names must not destroy a queued prompt")
            self.assertEqual(queue.read_bytes(), original_order, "Rejected duplicates must not append dangling queue entries")
            self.assertEqual(response["decision"], "block")
            self.assertIn("already exists", response["reason"])
            result = self.invoke(home, "sendqueue-hook.sh", "$sendqueue")
            self.assertIn("original prompt", result["hookSpecificOutput"]["additionalContext"])
            result = self.invoke(home, "sendqueue-hook.sh", "$sendqueue")
            self.assertIn("second prompt", result["hookSpecificOutput"]["additionalContext"])
            self.assertEqual(queue.read_bytes(), b"")

    def test_existing_pending_prompt_is_not_overwritten_by_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.invoke(home, "pending-hook.sh", "$pending task saved pending text")
            response = self.invoke(home, "queue-hook.sh", "$queue task queued replacement")
            file = home / ".claude/pending-prompts/task.txt"
            self.assertEqual(file.read_text(), "saved pending text\n", "Queue and pending share storage; queue must not clobber pending data")
            self.assertFalse((home / ".claude/queue-order.txt").exists())
            self.assertIn("already exists", response["reason"])

    def test_collision_after_name_sanitization_is_also_non_destructive(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.invoke(home, "queue-hook.sh", "$queue task original")
            self.invoke(home, "queue-hook.sh", '$queue ta"sk replacement')
            self.assertEqual((home / ".claude/pending-prompts/task.txt").read_text(), "original\n")
            self.assertEqual((home / ".claude/queue-order.txt").read_text(), "task\n")


if __name__ == "__main__":
    unittest.main()
