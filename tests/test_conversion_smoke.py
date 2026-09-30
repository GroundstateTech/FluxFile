import json
import tempfile
import unittest
from pathlib import Path

from fluxfile import Engine


class ConversionSmokeTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine()

    def test_csv_to_xlsx_and_back(self):
        if not self.engine.capabilities()["pandas"]:
            self.skipTest("pandas not installed")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "sample.csv"
            xlsx = root / "sample.xlsx"
            roundtrip = root / "roundtrip.csv"
            source.write_text("name,value\nalpha,1\nbeta,2\n", encoding="utf-8")
            self.assertEqual(self.engine.convert(source, xlsx), "pandas")
            self.assertTrue(xlsx.exists())
            self.assertEqual(self.engine.convert(xlsx, roundtrip), "pandas")
            text = roundtrip.read_text(encoding="utf-8")
            self.assertIn("alpha,1", text)
            self.assertIn("beta,2", text)

    def test_json_rows_to_csv(self):
        if not self.engine.capabilities()["pandas"]:
            self.skipTest("pandas not installed")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "sample.json"
            output = root / "sample.csv"
            source.write_text(json.dumps({"rows": [{"name": "alpha", "value": 1}]}), encoding="utf-8")
            self.assertEqual(self.engine.convert(source, output), "pandas")
            self.assertIn("alpha,1", output.read_text(encoding="utf-8"))

    def test_multisheet_xlsx_to_ods_preserves_all_sheets(self):
        if not self.engine.capabilities()["pandas"]:
            self.skipTest("pandas not installed")
        import pandas as pd

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "book.xlsx"
            output = root / "book.ods"

            with pd.ExcelWriter(source, engine="openpyxl") as writer:
                pd.DataFrame({"value": [1]}).to_excel(writer, index=False, sheet_name="Alpha")
                pd.DataFrame({"value": [2]}).to_excel(writer, index=False, sheet_name="Beta")

            self.assertEqual(self.engine.convert(source, output), "pandas")
            sheets = pd.read_excel(output, sheet_name=None, engine="odf")
            self.assertEqual(list(sheets), ["Alpha", "Beta"])
            self.assertEqual(int(sheets["Alpha"].iloc[0]["value"]), 1)
            self.assertEqual(int(sheets["Beta"].iloc[0]["value"]), 2)

    def test_multisheet_workbook_refuses_flat_output(self):
        if not self.engine.capabilities()["pandas"]:
            self.skipTest("pandas not installed")
        import pandas as pd

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "book.xlsx"
            output = root / "book.csv"

            with pd.ExcelWriter(source, engine="openpyxl") as writer:
                pd.DataFrame({"value": [1]}).to_excel(writer, index=False, sheet_name="Alpha")
                pd.DataFrame({"value": [2]}).to_excel(writer, index=False, sheet_name="Beta")

            with self.assertRaisesRegex(RuntimeError, "would discard data"):
                self.engine.convert(source, output)
            self.assertFalse(output.exists())

    def test_png_to_jpg(self):
        if not self.engine.capabilities()["pillow"]:
            self.skipTest("Pillow not installed")
        from PIL import Image

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "sample.png"
            output = root / "sample.jpg"
            Image.new("RGBA", (16, 16), (255, 0, 0, 128)).save(source)
            self.assertEqual(self.engine.convert(source, output), "pillow")
            with Image.open(output) as im:
                self.assertEqual(im.mode, "RGB")
                self.assertEqual(im.size, (16, 16))

    def test_pdf_to_text(self):
        if not self.engine.capabilities()["pymupdf"]:
            self.skipTest("PyMuPDF not installed")
        import pymupdf

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "sample.pdf"
            output = root / "sample.txt"
            doc = pymupdf.open()
            page = doc.new_page()
            page.insert_text((72, 72), "FluxFile smoke test")
            doc.save(source)
            doc.close()

            self.assertEqual(self.engine.convert(source, output), "pymupdf")
            self.assertIn("FluxFile smoke test", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
