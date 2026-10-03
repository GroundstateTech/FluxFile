import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def test_cli_batches_multiple_same_named_files_without_collision(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a").mkdir()
            (root / "b").mkdir()
            first = root / "a" / "same.txt"
            second = root / "b" / "same.txt"
            first.write_text("alpha")
            second.write_text("beta")
            output = root / "out"

            proc = subprocess.run(
                [
                    sys.executable,
                    "fluxfile_cli.py",
                    str(first),
                    str(second),
                    "--to",
                    "txt",
                    "--output-dir",
                    str(output),
                    "--workers",
                    "2",
                    "--json",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            summary = json.loads(proc.stdout)
            self.assertEqual(summary["counts"].get("Done"), 2)
            self.assertEqual((output / "same.txt").read_text(), "alpha")
            self.assertEqual((output / "same_2.txt").read_text(), "beta")

    def test_engines_command_is_json(self):
        proc = subprocess.run(
            [sys.executable, "fluxfile_cli.py", "--engines"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertIn("pillow", payload)
        self.assertIn("pandas", payload)


if __name__ == "__main__":
    unittest.main()
