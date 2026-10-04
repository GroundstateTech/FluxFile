import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from fluxfile_batch import BatchRunner
from fluxfile_core import ConversionCancelled, Engine, create_job, discover_folder_files, resolve_output


class ParallelCopyEngine(Engine):
    def __init__(self):
        self._capabilities = {"copy": True}
        self._route_cache = {}
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def capabilities(self):
        return {"copy": True}

    def engine_for(self, source_fmt, target_fmt):
        return "copy"

    def convert(self, source, output, cancel_event=None):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            for _ in range(5):
                if cancel_event and cancel_event.is_set():
                    raise ConversionCancelled("Conversion cancelled")
                time.sleep(0.015)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, output)
            return "copy"
        finally:
            with self.lock:
                self.active -= 1


class BatchTests(unittest.TestCase):
    def test_parallel_runner_uses_multiple_workers_and_unique_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sources = []
            for i in range(8):
                folder = root / f"s{i}"
                folder.mkdir()
                path = folder / "same.txt"
                path.write_text(str(i))
                sources.append(path)

            engine = ParallelCopyEngine()
            jobs = [create_job(path, "txt", engine) for path in sources]
            summary = BatchRunner(engine, workers=4).run(jobs, root / "out", "overwrite")

            self.assertEqual(summary.counts.get("Done"), 8)
            self.assertGreaterEqual(engine.max_active, 2)
            self.assertEqual(len({Path(job.output).name for job in jobs}), 8)
            self.assertTrue(Path(summary.json_report).exists())
            self.assertTrue(Path(summary.csv_report).exists())
            self.assertTrue(all(job.duration_seconds > 0 for job in jobs))

    def test_cancel_marks_pending_and_running_work_cancelled_not_failed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sources = []
            for i in range(12):
                path = root / f"f{i}.txt"
                path.write_text("x")
                sources.append(path)

            engine = ParallelCopyEngine()
            jobs = [create_job(path, "txt", engine) for path in sources]
            runner = BatchRunner(engine, workers=2)
            holder = {}
            thread = threading.Thread(
                target=lambda: holder.setdefault("summary", runner.run(jobs, root / "out"))
            )
            thread.start()

            deadline = time.time() + 2
            while engine.max_active == 0 and time.time() < deadline:
                time.sleep(0.01)
            runner.cancel()
            thread.join(5)

            self.assertFalse(thread.is_alive())
            self.assertGreater(holder["summary"].counts.get("Cancelled", 0), 0)
            self.assertEqual(holder["summary"].counts.get("Failed", 0), 0)
            self.assertEqual(sum(holder["summary"].counts.values()), len(jobs))

    def test_preserve_layout_writes_into_relative_subfolder(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_dir = root / "input" / "nested"
            source_dir.mkdir(parents=True)
            source = source_dir / "note.txt"
            source.write_text("hello")

            engine = ParallelCopyEngine()
            job = create_job(source, "txt", engine, relative_dir="nested")
            summary = BatchRunner(engine, workers=1).run([job], root / "out", layout="preserve")

            self.assertEqual(summary.counts.get("Done"), 1)
            self.assertEqual((root / "out" / "nested" / "note.txt").read_text(), "hello")
            self.assertEqual(Path(job.output), root / "out" / "nested" / "note.txt")

    def test_output_reservation_prevents_parallel_name_collision(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = root / "out"
            out.mkdir()
            reserved = set()

            a = resolve_output(root / "a" / "same.txt", out, "txt", "overwrite", reserved)
            b = resolve_output(root / "b" / "same.txt", out, "txt", "overwrite", reserved)
            c = resolve_output(root / "c" / "same.txt", out, "txt", "overwrite", reserved)

            self.assertEqual([path.name for path in (a, b, c)], ["same.txt", "same_2.txt", "same_3.txt"])

    def test_compound_archive_output_stem_is_clean(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = resolve_output(root / "bundle.tar.gz", root, "zip", "suffix")
            self.assertEqual(output.name, "bundle.zip")

    def test_recursive_discovery_prunes_internal_trees_before_results(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "keep").mkdir()
            (root / "keep" / "a.txt").write_text("a")
            (root / ".venv" / "deep").mkdir(parents=True)
            (root / ".venv" / "deep" / "package.py").write_text("x")
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("x")
            out = root / "converted"
            out.mkdir()
            (out / "old.txt").write_text("x")

            files = discover_folder_files(root, True, out)
            self.assertEqual([path.relative_to(root).as_posix() for path in files], ["keep/a.txt"])


if __name__ == "__main__":
    unittest.main()
