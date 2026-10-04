import tempfile
import unittest
from pathlib import Path

from fluxfile_core import Engine, create_job
from fluxfile_session import load_session, save_session


class SessionTests(unittest.TestCase):
    def test_queue_session_round_trip_preserves_settings_and_relative_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "input" / "nested" / "note.txt"
            source.parent.mkdir(parents=True)
            source.write_text("hello")
            output = root / "converted" / "nested" / "note.txt"
            output.parent.mkdir(parents=True)
            output.write_text("hello")

            engine = Engine()
            job = create_job(source, "txt", engine, relative_dir="nested")
            job.status = "Done"
            job.output = str(output)
            session = root / "work.fluxqueue.json"
            save_session(session, [job], {
                "output_dir": str(root / "converted"),
                "source_choice": "any",
                "target_choice": "txt",
                "conflict": "suffix",
                "recursive": True,
                "layout": "preserve",
            })

            jobs, settings = load_session(session)
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0].relative_dir, "nested")
            self.assertEqual(jobs[0].status, "Done")
            self.assertEqual(settings["layout"], "preserve")
            self.assertTrue(settings["recursive"])

    def test_missing_session_source_is_marked_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "gone.txt"
            source.write_text("gone")
            engine = Engine()
            job = create_job(source, "txt", engine)
            session = root / "work.fluxqueue.json"
            save_session(session, [job], {"layout": "flat"})
            source.unlink()

            jobs, _settings = load_session(session)
            self.assertEqual(jobs[0].status, "Missing")

    def test_non_terminal_session_work_is_requeued(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.txt"
            source.write_text("hello")
            engine = Engine()
            job = create_job(source, "txt", engine)
            job.status = "Failed"
            job.error = "old failure"
            session = root / "work.fluxqueue.json"
            save_session(session, [job], {"layout": "flat"})

            jobs, _settings = load_session(session)
            self.assertEqual(jobs[0].status, "Queued")
            self.assertEqual(jobs[0].error, "")


if __name__ == "__main__":
    unittest.main()
