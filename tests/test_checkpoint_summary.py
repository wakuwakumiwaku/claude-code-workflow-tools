"""Execute only installed hooks against synthetic checkpoint files."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CheckpointSummaryTests(unittest.TestCase):
    def invoke(self, home, summary=None, raw=None, project="synthetic project"):
        installed = home / ".claude"
        env = dict(os.environ, HOME=str(home))
        install = subprocess.run(["bash", str(ROOT / "claudetools/install.sh")],
                                 cwd=home, env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(install.returncode, 0, install.stdout + install.stderr)
        source = ROOT / "claudetools/hooks/cc-hook.sh"
        target = installed / "hooks/cc-hook.sh"
        self.assertEqual(target.read_bytes(), source.read_bytes())
        print("INSTALLED_SOURCE", source, target)
        enabled = installed / "hooks/enabled"
        enabled.mkdir()
        (enabled / "cc-hook.sh").symlink_to(target)
        checkpoints = installed / "checkpoints"
        checkpoints.mkdir()
        (checkpoints / "fixture.meta.json").write_text(json.dumps({
            "created": "2026-01-02T03:04:05", "project_path": project}), encoding="utf-8")
        if summary is not None:
            (checkpoints / "fixture.md").write_text(summary, encoding="utf-8")
        if raw is not None:
            (checkpoints / "fixture.jsonl").write_text(raw, encoding="utf-8")
        result = subprocess.run(["bash", str(installed / "hooks/dispatcher-hook.sh")],
                                input=json.dumps({"prompt": "$cc-resume fixture"}),
                                cwd=home, env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_summary_preserves_code_backslashes_and_following_text(self):
        summary = 'Use `r"C:\\new\\test\\capture"` and regex `\\bword\\b`.\nKeep this final line.'
        project = r'C:\new\test\capture'
        with tempfile.TemporaryDirectory() as directory:
            context = self.invoke(Path(directory), summary=summary, project=project)
        self.assertIn(summary, context, "Resume must include literal saved Markdown, not echo-decoded code")
        self.assertIn(project, context)
        self.assertIn("**Instructions:**", context)
        self.assertIn("\n\n## Checkpoint Summary\n\n", context)

    def test_plain_summary_control(self):
        with tempfile.TemporaryDirectory() as directory:
            context = self.invoke(Path(directory), summary="Plain checkpoint summary")
        self.assertIn("Plain checkpoint summary", context)
        self.assertIn("# Resume from Checkpoint: fixture\n\n", context)

    def test_raw_checkpoint_control(self):
        raw = '{"type":"user","message":"literal \\\\n escape"}\n'
        with tempfile.TemporaryDirectory() as directory:
            context = self.invoke(Path(directory), raw=raw)
        self.assertIn(raw.rstrip("\n"), context)
        self.assertIn("## Raw Checkpoint Data", context)


if __name__ == "__main__":
    unittest.main()
