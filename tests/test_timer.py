"""Exercise the timer CLI using only isolated synthetic homes and sessions."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "claudetools/commands/timer.sh"


class TimerTests(unittest.TestCase):
    def invoke(self, home, project, *args):
        env = dict(os.environ, HOME=str(home))
        result = subprocess.run(["bash", str(SCRIPT), *args], cwd=project, env=env,
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return result

    def read_json(self, path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            self.fail(f"Timer must persist valid JSON for literal names and paths: {exc}")

    def test_name_roundtrips_through_start_status_stop_and_list(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            project = Path(directory) / "project"
            home.mkdir()
            project.mkdir()
            name = 'fix "quoted" paths\\and tabs\tand\nnewlines ☃'
            self.invoke(home, project, "start", name)
            current = home / ".claude/timers/current.json"
            self.assertEqual(self.read_json(current)["name"], name)
            self.assertIn(name, self.invoke(home, project, "status").stdout)
            self.invoke(home, project, "stop")
            self.assertFalse(current.exists())
            history = home / ".claude/timers/history.jsonl"
            entries = history.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(entries), 1, "Embedded newlines must not create additional JSONL records")
            saved = self.read_json(history)
            self.assertEqual(saved["name"], name)
            self.assertEqual(saved["cwd"], str(project))
            self.assertIn(name, self.invoke(home, project, "list").stdout)

    def test_literal_home_and_project_paths_preserve_token_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / 'home "quoted" \\n literal'
            project = Path(directory) / 'project "quoted" \\n literal'
            home.mkdir()
            project.mkdir()
            session_dir = home / ".claude/projects" / str(project).replace("/", "-")
            session_dir.mkdir(parents=True)
            session = session_dir / "synthetic.jsonl"
            def save_usage(input_tokens, output_tokens):
                session.write_text(json.dumps({"type": "assistant", "message": {"usage": {
                    "input_tokens": input_tokens, "output_tokens": output_tokens}}}) + "\n", encoding="utf-8")
            save_usage(11, 7)
            self.invoke(home, project, "start", "literal-path")
            current = self.read_json(home / ".claude/timers/current.json")
            self.assertEqual(current["cwd"], str(project))
            self.assertEqual(current["start_input_tokens"], 11)
            self.assertEqual(current["start_output_tokens"], 7)
            save_usage(31, 12)
            self.invoke(home, project, "stop")
            saved = self.read_json(home / ".claude/timers/history.jsonl")
            self.assertEqual(saved["input_tokens"], 20)
            self.assertEqual(saved["output_tokens"], 5)
            self.assertEqual(saved["total_tokens"], 25)
            self.assertIn("literal-path", self.invoke(home, project, "list").stdout)


if __name__ == "__main__":
    unittest.main()
