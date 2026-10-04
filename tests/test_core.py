import tempfile
import unittest
from pathlib import Path

from fluxfile import (
    Engine,
    choose_auto_target,
    compatible_targets,
    discover_folder_files,
    normalize_format,
    resolve_output,
    should_skip_intake_path,
    source_format,
    safe_relative_dir,
)


class CoreTests(unittest.TestCase):
    def test_normalize_format(self):
        self.assertEqual(normalize_format(".DOCX"), "docx")
        self.assertEqual(normalize_format("markdown"), "md")
        self.assertEqual(normalize_format("tif"), "tiff")

    def test_source_format(self):
        self.assertEqual(source_format(Path("report.CSV")), "csv")
        self.assertEqual(source_format(Path("photo.tif")), "tiff")

    def test_safe_relative_dir_rejects_escape(self):
        self.assertEqual(safe_relative_dir("nested/deeper"), "nested/deeper")
        self.assertEqual(safe_relative_dir("."), "")
        self.assertEqual(safe_relative_dir("../escape"), "")
        self.assertEqual(safe_relative_dir("/absolute/path"), "")
        self.assertEqual(safe_relative_dir(r"C:\\temp\\file"), "")
        self.assertEqual(safe_relative_dir(r"\\\\server\\share"), "")
        self.assertEqual(safe_relative_dir(r"nested\\deeper"), "nested/deeper")

    def test_auto_profiles(self):
        self.assertEqual(choose_auto_target(Path("notes.md")), "docx")
        self.assertEqual(choose_auto_target(Path("data.csv")), "xlsx")
        self.assertEqual(choose_auto_target(Path("photo.jpg")), "png")
        self.assertEqual(choose_auto_target(Path("report.pdf")), "docx")

    def test_table_matrix_is_constrained(self):
        targets = compatible_targets("csv")
        self.assertIn("ods", targets)
        self.assertIn("xlsx", targets)
        self.assertIn("json", targets)
        self.assertIn("tsv", targets)
        self.assertIn("pdf", targets)
        self.assertNotIn("pptx", targets)
        self.assertNotIn("pdf", compatible_targets("json"))

    def test_document_matrix_does_not_offer_spreadsheet_or_presentation_outputs(self):
        targets = compatible_targets("docx")
        self.assertIn("pdf", targets)
        self.assertIn("md", targets)
        self.assertNotIn("xlsx", targets)
        self.assertNotIn("pptx", targets)
        self.assertNotIn("md", compatible_targets("doc"))
        self.assertNotIn("pdf", compatible_targets("md"))

    def test_presentation_matrix_is_constrained(self):
        self.assertEqual(
            compatible_targets("pptx"),
            ["auto", "pdf", "pptx", "odp"],
        )

    def test_image_matrix(self):
        targets = compatible_targets("png")
        self.assertIn("webp", targets)
        self.assertIn("jpg", targets)
        self.assertIn("pdf", targets)

    def test_pdf_matrix(self):
        self.assertEqual(compatible_targets("pdf"), ["auto", "docx", "txt", "html", "png", "jpg", "tiff"])

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

    def test_recursive_intake_skips_hidden_and_internal_directories(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "keep").mkdir()
            (root / "keep" / "a.txt").write_text("a")
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("x")
            (root / ".venv").mkdir()
            (root / ".venv" / "package.py").write_text("x")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "bundle.js").write_text("x")
            files = discover_folder_files(root, recursive=True)
            self.assertEqual([p.relative_to(root).as_posix() for p in files], ["keep/a.txt"])

    def test_recursive_intake_skips_output_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = root / "converted"
            out.mkdir()
            (root / "source.txt").write_text("source")
            (out / "old.txt").write_text("old")
            files = discover_folder_files(root, recursive=True, output_dir=out)
            self.assertEqual([p.name for p in files], ["source.txt"])

    def test_hidden_file_is_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            hidden = root / ".secret.txt"
            hidden.write_text("x")
            self.assertTrue(should_skip_intake_path(hidden, root))

    def test_atomic_copy_replaces_destination_without_temp_leftovers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.txt"
            output = root / "output.txt"
            source.write_text("new")
            output.write_text("old")
            engine = Engine()
            used = engine.convert(source, output)
            self.assertEqual(used, "copy")
            self.assertEqual(output.read_text(), "new")
            self.assertFalse(any(".fluxfile-" in p.name for p in root.iterdir()))

    def test_failed_atomic_conversion_preserves_existing_destination(self):
        class BrokenEngine(Engine):
            def engine_for(self, source_fmt, target_fmt):
                return "copy"

            def _convert_direct(self, engine, source, output):
                output.write_text("partial")
                raise RuntimeError("simulated failure")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.txt"
            output = root / "output.txt"
            source.write_text("new")
            output.write_text("old")
            with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                BrokenEngine().convert(source, output)
            self.assertEqual(output.read_text(), "old")
            self.assertFalse(any(".fluxfile-" in p.name for p in root.iterdir()))


if __name__ == "__main__":
    unittest.main()
