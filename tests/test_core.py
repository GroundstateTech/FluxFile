import tempfile
import unittest
from pathlib import Path

from fluxfile import choose_auto_target, normalize_target, resolve_output

class CoreTests(unittest.TestCase):
    def test_normalize_target(self):
        self.assertEqual(normalize_target(".DOCX"), "docx")

    def test_auto_profiles(self):
        self.assertEqual(choose_auto_target(Path("notes.md")), "docx")
        self.assertEqual(choose_auto_target(Path("data.csv")), "xlsx")
        self.assertEqual(choose_auto_target(Path("photo.jpg")), "png")

    def test_conflict_suffix(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "report.pdf").write_text("x")
            out = resolve_output(Path("report.docx"), root, "pdf", "suffix")
            self.assertEqual(out.name, "report_2.pdf")

    def test_conflict_skip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "report.pdf").write_text("x")
            self.assertIsNone(resolve_output(Path("report.docx"), root, "pdf", "skip"))

if __name__ == "__main__":
    unittest.main()
