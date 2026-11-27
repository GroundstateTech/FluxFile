import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.make_msix import copy_runtime


class MsixStagingTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.build = root / "build"
        self.stage = root / "stage"
        self.stage.mkdir()
        self.templates = self.build / "_internal" / "docx" / "templates"
        self.templates.mkdir(parents=True)
        (self.build / "FluxFile.exe").write_bytes(b"desktop executable")

    def test_stage_preserves_runtime_template_and_omits_expanded_sources(self):
        expanded = self.templates / "default-docx-template"
        expanded.mkdir()
        (expanded / "[Content_Types].xml").write_text("<Types/>", encoding="utf-8")
        (self.templates / "default.docx").write_bytes(b"runtime template")

        copy_runtime(self.build, self.stage)

        staged_templates = self.stage / "_internal" / "docx" / "templates"
        self.assertEqual((self.stage / "FluxFile.exe").read_bytes(), b"desktop executable")
        self.assertEqual((staged_templates / "default.docx").read_bytes(), b"runtime template")
        self.assertFalse((staged_templates / expanded.name).exists())
        self.assertTrue(expanded.is_dir())

    def test_stage_rejects_expanded_sources_without_runtime_template(self):
        (self.templates / "default-docx-template").mkdir()

        with self.assertRaisesRegex(ValueError, r"missing its default\.docx template"):
            copy_runtime(self.build, self.stage)

    def test_stage_accepts_runtime_with_no_expanded_sources(self):
        (self.templates / "default.docx").write_bytes(b"runtime template")

        copy_runtime(self.build, self.stage)

        staged_templates = self.stage / "_internal" / "docx" / "templates"
        self.assertEqual((staged_templates / "default.docx").read_bytes(), b"runtime template")
