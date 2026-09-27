import tempfile
import unittest
from pathlib import Path

from fluxfile import (
    choose_auto_target,
    compatible_targets,
    normalize_format,
    resolve_output,
    source_format,
)


class CoreTests(unittest.TestCase):
    def test_normalize_format(self):
        self.assertEqual(normalize_format(".DOCX"), "docx")
        self.assertEqual(normalize_format("markdown"), "md")
        self.assertEqual(normalize_format("tif"), "tiff")

    def test_source_format(self):
        self.assertEqual(source_format(Path("report.CSV")), "csv")
        self.assertEqual(source_format(Path("photo.tif")), "tiff")

    def test_auto_profiles(self):
        self.assertEqual(choose_auto_target(Path("notes.md")), "docx")
        self.assertEqual(choose_auto_target(Path("data.csv")), "xlsx")
        self.assertEqual(choose_auto_target(Path("photo.jpg")), "png")
        self.assertEqual(choose_auto_target(Path("report.pdf")), "docx")

    def test_table_matrix_includes_ods(self):
        targets = compatible_targets("csv")
        self.assertIn("ods", targets)
        self.assertIn("xlsx", targets)
        self.assertIn("json", targets)
        self.assertIn("tsv", targets)

    def test_image_matrix(self):
        targets = compatible_targets("png")
        self.assertIn("webp", targets)
        self.assertIn("jpg", targets)
        self.assertIn("pdf", targets)

    def test_pdf_matrix(self):
        self.assertEqual(compatible_targets("pdf"), ["auto", "docx", "txt"])

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
