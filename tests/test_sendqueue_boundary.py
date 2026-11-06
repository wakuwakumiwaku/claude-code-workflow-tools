"""Installed dispatcher proof in disposable HOME; no Claude process is launched."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SendQueueBoundaryTests(unittest.TestCase):
    def fixture(self, home):
        env = dict(os.environ, HOME=str(home))
        result = subprocess.run(["bash", str(ROOT / "claudetools/install.sh")], cwd=home, env=env,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        hooks = home / ".claude/hooks"
        for name in ("queue-hook.sh", "sendqueue-hook.sh", "dispatcher-hook.sh"):
            self.assertEqual((hooks / name).read_bytes(), (ROOT / "claudetools/hooks" / name).read_bytes())
        enabled = hooks / "enabled"
        enabled.mkdir()
        for name in ("queue-hook.sh", "sendqueue-hook.sh"):
            (enabled / name).symlink_to(hooks / name)
        return env, hooks / "dispatcher-hook.sh"

    def invoke(self, env, dispatcher, prompt):
        result = subprocess.run(["bash", str(dispatcher)], cwd=env["HOME"], env=env,
                                input=json.dumps({"prompt": prompt}), text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout

    def test_unrelated_prefix_does_not_consume_a_queued_prompt(self):
        for prompt in ("$sendqueue-status", "$sendqueued", "$sendqueue_name", "$sendqueue.json"):
            with self.subTest(prompt=prompt), tempfile.TemporaryDirectory(prefix="sendqueue-prefix-") as directory:
                home = Path(directory)
                env, dispatcher = self.fixture(home)
                self.invoke(env, dispatcher, "$queue first original prompt")
                self.invoke(env, dispatcher, "$queue second later prompt")
                files = [home / ".claude/queue-order.txt", home / ".claude/pending-prompts/first.txt",
                         home / ".claude/pending-prompts/second.txt"]
                before = {p: p.read_bytes() for p in files}
                output = self.invoke(env, dispatcher, prompt)
                self.assertTrue(all(p.exists() and p.read_bytes() == data for p, data in before.items()),
                                "Unrelated command prefixes must preserve queue order and prompt files")
                self.assertEqual(output, "", "A different command token must pass through, not dequeue saved work")

    def test_unrelated_prefix_is_not_blocked_when_queue_is_empty(self):
        with tempfile.TemporaryDirectory(prefix="sendqueue-empty-") as directory:
            env, dispatcher = self.fixture(Path(directory))
            self.assertEqual(self.invoke(env, dispatcher, "$sendqueue-status"), "",
                             "Only the sendqueue command may report an empty queue")

    def test_bare_command_and_whitespace_boundary_still_execute_next_item(self):
        for command in ("$sendqueue", "$sendqueue ", "$sendqueue\t"):
            with self.subTest(command=repr(command)), tempfile.TemporaryDirectory(prefix="sendqueue-valid-") as directory:
                home = Path(directory)
                env, dispatcher = self.fixture(home)
                self.invoke(env, dispatcher, "$queue first original prompt")
                self.invoke(env, dispatcher, "$queue second later prompt")
                response = json.loads(self.invoke(env, dispatcher, command))
                self.assertIn("original prompt", response["hookSpecificOutput"]["additionalContext"])
                self.assertEqual((home / ".claude/queue-order.txt").read_text(), "second\n")
                self.assertFalse((home / ".claude/pending-prompts/first.txt").exists())
                self.assertEqual((home / ".claude/pending-prompts/second.txt").read_text(), "later prompt\n")


if __name__ == "__main__":
    unittest.main()
