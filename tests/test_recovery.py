import tempfile
import unittest
from pathlib import Path

from fluxfile_core import Engine, create_job
from fluxfile_recovery import (
    RECOVERY_FILENAME,
    clear_recovery,
    load_recovery,
    recovery_exists,
    recovery_path,
    save_recovery,
)


class RecoveryTests(unittest.TestCase):
    def test_linux_recovery_path_uses_xdg_state_home(self):
        path = recovery_path(
            env={"XDG_STATE_HOME": "/tmp/state"},
            home=Path("/home/tester"),
            platform="linux",
        )
        self.assertEqual(path, Path("/tmp/state/fluxfile") / RECOVERY_FILENAME)

    def test_linux_recovery_path_falls_back_to_home_state(self):
        path = recovery_path(env={}, home=Path("/home/tester"), platform="linux")
        self.assertEqual(path, Path("/home/tester/.local/state/fluxfile") / RECOVERY_FILENAME)

    def test_windows_recovery_path_uses_localappdata(self):
        path = recovery_path(
            env={"LOCALAPPDATA": r"C:\Users\Tester\AppData\Local"},
            home=Path("C:/Users/Tester"),
            platform="win32",
        )
        self.assertEqual(path, Path(r"C:\Users\Tester\AppData\Local") / "FluxFile" / RECOVERY_FILENAME)

    def test_recovery_round_trip_and_clear(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "input.txt"
            source.write_text("hello")
            recovery = root / "state" / RECOVERY_FILENAME
            engine = Engine()
            job = create_job(source, "txt", engine)

            saved = save_recovery(
                [job],
                {
                    "output_dir": str(root / "converted"),
                    "source_choice": "any",
                    "target_choice": "txt",
                    "conflict": "suffix",
                    "recursive": False,
                    "layout": "flat",
                },
                recovery,
            )
            self.assertEqual(saved, recovery.resolve(strict=False))
            self.assertTrue(recovery_exists(recovery))

            jobs, settings = load_recovery(recovery)
            self.assertEqual(len(jobs), 1)
            self.assertEqual(Path(jobs[0].source).resolve(), source.resolve())
            self.assertEqual(settings["target_choice"], "txt")

            self.assertTrue(clear_recovery(recovery))
            self.assertFalse(recovery_exists(recovery))

    def test_empty_queue_removes_existing_recovery(self):
        with tempfile.TemporaryDirectory() as td:
            recovery = Path(td) / RECOVERY_FILENAME
            recovery.write_text("placeholder")
            self.assertIsNone(save_recovery([], {}, recovery))
            self.assertFalse(recovery.exists())


if __name__ == "__main__":
    unittest.main()
