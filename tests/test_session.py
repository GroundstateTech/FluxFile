import json
import tempfile
import unittest
from pathlib import Path

from fluxfile_core import Engine, Job, create_job
from fluxfile_session import (
    SESSION_SCHEMA,
    SESSION_VERSION,
    load_session,
    relink_missing_jobs,
    save_session,
)


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

            payload = json.loads(session.read_text())
            self.assertEqual(payload["version"], SESSION_VERSION)
            self.assertEqual(payload["jobs"][0]["source_ref"]["kind"], "relative")
            self.assertEqual(payload["settings"]["output_dir_ref"]["kind"], "relative")

            jobs, settings = load_session(session)
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0].relative_dir, "nested")
            self.assertEqual(jobs[0].status, "Done")
            self.assertEqual(settings["layout"], "preserve")
            self.assertEqual(settings["session_version"], SESSION_VERSION)
            self.assertTrue(settings["recursive"])

    def test_v2_relative_references_survive_moving_whole_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "workspace"
            source = workspace / "input" / "nested" / "note.txt"
            source.parent.mkdir(parents=True)
            source.write_text("hello")
            output = workspace / "converted" / "nested" / "note.txt"
            output.parent.mkdir(parents=True)
            output.write_text("hello")

            engine = Engine()
            job = create_job(source, "txt", engine, relative_dir="nested")
            job.status = "Done"
            job.output = str(output)
            session = workspace / "work.fluxqueue.json"
            save_session(session, [job], {
                "output_dir": str(workspace / "converted"),
                "layout": "preserve",
            })

            moved = root / "moved-workspace"
            workspace.rename(moved)
            moved_session = moved / "work.fluxqueue.json"
            jobs, settings = load_session(moved_session)

            self.assertEqual(Path(jobs[0].source).resolve(), (moved / "input" / "nested" / "note.txt").resolve())
            self.assertEqual(Path(jobs[0].output).resolve(), (moved / "converted" / "nested" / "note.txt").resolve())
            self.assertEqual(Path(settings["output_dir"]).resolve(), (moved / "converted").resolve())
            self.assertEqual(jobs[0].status, "Done")

    def test_v1_session_remains_loadable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "legacy.txt"
            source.write_text("legacy")
            session = root / "legacy.fluxqueue.json"
            session.write_text(json.dumps({
                "schema": SESSION_SCHEMA,
                "version": 1,
                "settings": {"output_dir": str(root / "out"), "layout": "flat"},
                "jobs": [{
                    "id": "legacy",
                    "source": str(source),
                    "source_format": "txt",
                    "target_format": "txt",
                    "status": "Queued",
                    "engine": "copy",
                    "output": "",
                    "error": "",
                    "duration_seconds": 0,
                    "input_bytes": source.stat().st_size,
                    "output_bytes": 0,
                    "relative_dir": "",
                }],
            }), encoding="utf-8")

            jobs, settings = load_session(session)
            self.assertEqual(len(jobs), 1)
            self.assertEqual(Path(jobs[0].source).resolve(), source.resolve())
            self.assertEqual(jobs[0].status, "Queued")
            self.assertEqual(settings["session_version"], 1)

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

    def test_relink_missing_jobs_uses_relative_directory_structure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            replacement_root = root / "replacement"
            replacement = replacement_root / "nested" / "note.txt"
            replacement.parent.mkdir(parents=True)
            replacement.write_text("replacement")

            job = Job(
                id="missing",
                source=str(root / "old" / "nested" / "note.txt"),
                source_format="txt",
                target_format="txt",
                status="Missing",
                engine="unavailable",
                error="Source file is missing",
                relative_dir="nested",
            )
            relinked, unresolved = relink_missing_jobs([job], replacement_root, Engine())

            self.assertEqual((relinked, unresolved), (1, 0))
            self.assertEqual(Path(job.source).resolve(), replacement.resolve())
            self.assertEqual(job.status, "Queued")
            self.assertEqual(job.error, "")

    def test_relink_understands_windows_source_name_on_any_host(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            replacement = root / "nested" / "note.txt"
            replacement.parent.mkdir(parents=True)
            replacement.write_text("replacement")

            job = Job(
                id="windows-missing",
                source=r"C:\old\nested\note.txt",
                source_format="txt",
                target_format="txt",
                status="Missing",
                engine="unavailable",
                relative_dir="nested",
            )
            relinked, unresolved = relink_missing_jobs([job], root, Engine())

            self.assertEqual((relinked, unresolved), (1, 0))
            self.assertEqual(Path(job.source).resolve(), replacement.resolve())


if __name__ == "__main__":
    unittest.main()
