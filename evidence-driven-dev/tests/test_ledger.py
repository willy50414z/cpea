"""Contract tests use isolated repositories and real subprocess results."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ledger import Ledger, EddError, read_document, write_document


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-qm", "base"], check=True)
        self.l = Ledger(self.root)
        self.l.init("example", "bugfix", "修正可重現錯誤", ["fixture"], "complex")

    def doc(self):
        return self.l.load("example")

    def test_init_collision_and_multiple(self):
        before = self.doc()
        with self.assertRaises(EddError):
            self.l.init("example", "bugfix", "other", ["x"], "moderate")
        self.assertEqual(before, self.doc())
        self.l.init("other", "feature", "另一任務", ["x"], "moderate")
        self.assertEqual(len(self.l.list_tasks()), 2)
        self.assertTrue(before["base_git_sha"])

    def test_traversal_and_symlink(self):
        for value in ("../escape", "/tmp/escape", "a/b", "..", "a;sh"):
            with self.assertRaises(EddError):
                self.l.load(value)
        outside = self.root / "outside"
        outside.mkdir()
        (self.l.home / "tasks" / "linked").symlink_to(outside)
        with self.assertRaises(EddError):
            self.l.load("linked")

    def test_transition_requires_evidence(self):
        self.l.transition("example", "INVESTIGATING")
        with self.assertRaises(EddError):
            self.l.transition("example", "PLANNING")
        self.l.update("example", {"problem": {"description": "bug", "expected": "正確", "actual": "錯誤",
                    "evidence": ["觀察：fixture 重現"], "hypotheses": [{"id": "H1", "claim": "boundary", "status": "UNCONFIRMED"}]}})
        self.l.transition("example", "PLANNING")
        with self.assertRaises(EddError):
            self.l.transition("example", "COMPLETED")
        self.assertEqual(self.doc()["status"], "PLANNING")

    def test_checkpoint_resume_and_pending_question(self):
        self.l.transition("example", "INVESTIGATING")
        self.l.checkpoint("example", "baseline", "replay", "inspect node", ["input"])
        self.l.ask("example", "Q-001", "main-agent", "業務契約？", "oracle ambiguity", ["A", "B"], "B", "output")
        self.assertEqual(self.doc()["waiting"]["previous_status"], "INVESTIGATING")
        snapshot = self.l.resume("example")
        self.assertIn("inspect node", json.dumps(snapshot))
        self.l.answer("example", "Q-001", "B", "使用者選擇 B")
        self.assertEqual(self.doc()["status"], "INVESTIGATING")
        self.assertEqual(self.doc()["questions"][0]["answer"], "B")

    def test_missing_and_malformed_records_reported(self):
        path = self.l.task_path("example") / "decisions.md"
        path.unlink()
        self.assertTrue(self.l.validate("example"))
        self.assertTrue(self.l.resume("example")["errors"])
        (self.l.task_path("example") / "task.md").write_text("---\ninvalid: [\n---\n", encoding="utf-8")
        with self.assertRaises(EddError):
            self.l.load("example")

    def test_schema_and_history_tampering(self):
        d = self.doc()
        d["status"] = "COMPLETED"
        write_document(self.l.task_path("example") / "task.md", d, "")
        self.assertTrue(self.l.validate("example"))

    def test_main_writer_only(self):
        with self.assertRaises(EddError):
            Ledger(self.root, actor="research").update("example", {"phase": "x"})

    def test_real_evidence_and_staleness(self):
        ev = self.l.run("example", [sys.executable, "-c", "print('ok')"], "focused")
        self.assertEqual(ev["exit_code"], 0)
        self.assertFalse(self.l.evidence_errors("example", [ev["path"]], fresh=True))
        (self.root / "source.py").write_text("change=1\n", encoding="utf-8")
        self.assertTrue(self.l.evidence_errors("example", [ev["path"]], fresh=True))

    def test_evidence_digest_detects_change(self):
        ev = self.l.run("example", [sys.executable, "-c", "print('ok')"], "focused")
        p = self.l.task_path("example") / ev["path"]
        d = json.loads(p.read_text(encoding="utf-8"))
        d["exit_code"] = 9
        p.write_text(json.dumps(d), encoding="utf-8")
        self.assertTrue(self.l.evidence_errors("example", [ev["path"]]))

    def test_timeout_is_not_pass(self):
        ev = self.l.run("example", [sys.executable, "-c", "import time; time.sleep(2)"], "timeout", timeout=0.05)
        self.assertNotEqual(ev["exit_code"], 0)
        self.assertTrue(self.l.evidence_errors("example", [ev["path"]]))

    def test_line_endings_preserved(self):
        p = self.l.task_path("example") / "task.md"
        p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
        self.l.checkpoint("example", "a", "b", "c", [])
        data = p.read_bytes()
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))
        self.assertFalse(data.startswith(b"\xef\xbb\xbf"))

    def test_incomplete_archive_rejected(self):
        with self.assertRaises(EddError):
            self.l.archive("example")


if __name__ == "__main__":
    unittest.main()
