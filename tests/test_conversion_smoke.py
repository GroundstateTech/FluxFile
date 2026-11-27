import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

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

    def test_whole_workbook_exports_one_csv_per_sheet(self):
        import pandas as pd

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "book.xlsx"
            output = root / "book.csv.zip"
            with pd.ExcelWriter(source, engine="openpyxl") as writer:
                pd.DataFrame({"value": [1]}).to_excel(writer, index=False, sheet_name="Alpha")
                pd.DataFrame({"value": [2]}).to_excel(writer, index=False, sheet_name="Beta")
            self.assertEqual(self.engine.convert(source, output), "pandas")
            with ZipFile(output) as archive:
                self.assertEqual(archive.namelist(), ["001-Alpha.csv", "002-Beta.csv"])
                self.assertEqual(archive.read("001-Alpha.csv").splitlines(), [b"value", b"1"])
                self.assertEqual(archive.read("002-Beta.csv").splitlines(), [b"value", b"2"])

    def test_whole_pdf_exports_one_image_per_page(self):
        import pymupdf

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "sample.pdf"
            with pymupdf.open() as doc:
                doc.new_page(width=100, height=100)
                doc.new_page(width=200, height=100)
                doc.save(source)
            for extension in ("png", "jpg"):
                with self.subTest(extension=extension):
                    output = root / f"sample.{extension}.zip"
                    self.assertEqual(self.engine.convert(source, output), "pdf-export")
                    with ZipFile(output) as archive:
                        names = [f"page-0001.{extension}", f"page-0002.{extension}"]
                        self.assertEqual(archive.namelist(), names)
                        one, two = (pymupdf.Pixmap(archive.read(name)) for name in names)
                        self.assertEqual((one.width, two.width), (200, 400))

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

    def test_pipe_separated_to_ndjson_and_back(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "parts.psv"
            interim = root / "parts.ndjson"
            output = root / "roundtrip.psv"
            source.write_text('name|count\n"plug|socket"|2\n', encoding="utf-8")
            self.assertEqual(self.engine.convert(source, interim), "pandas")
            self.assertEqual(json.loads(interim.read_text()), {"name": "plug|socket", "count": 2})
            self.assertEqual(self.engine.convert(interim, output), "pandas")
            self.assertEqual(output.read_text(), source.read_text())

    def test_xlsm_to_xlsx_preserves_sheet_data(self):
        import pandas as pd

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "sample.xlsm"
            output = root / "sample.xlsx"
            with pd.ExcelWriter(source, engine="openpyxl") as writer:
                pd.DataFrame({"value": [1]}).to_excel(writer, index=False, sheet_name="Inputs")
                pd.DataFrame({"value": [2]}).to_excel(writer, index=False, sheet_name="Results")
            self.assertEqual(self.engine.convert(source, output), "pandas")
            sheets = pd.read_excel(output, sheet_name=None)
            self.assertEqual({name: frame["value"].tolist() for name, frame in sheets.items()},
                             {"Inputs": [1], "Results": [2]})

    def test_qoi_and_jpeg2000_preserve_pixels(self):
        from PIL import Image, features

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "sample.png"
            Image.new("LA", (8, 8), (77, 150)).save(source)
            qoi = root / "sample.qoi"
            out = root / "from-qoi.png"
            self.assertEqual(self.engine.convert(source, qoi), "pillow")
            self.assertEqual(self.engine.convert(qoi, out), "pillow")
            with Image.open(out) as image:
                self.assertEqual(image.getpixel((0, 0)), (77, 77, 77, 150))

            if features.check_codec("jpg_2000"):
                jp2 = root / "sample.jp2"
                self.assertEqual(self.engine.convert(out, jp2), "pillow")
                self.assertEqual(self.engine.convert(jp2, out), "pillow")
                with Image.open(out) as image:
                    self.assertEqual(image.getpixel((0, 0)), (77, 77, 77, 150))
            else:
                self.assertIsNone(self.engine.engine_for("png", "jp2"))
                self.assertIsNone(self.engine.engine_for("jp2", "png"))

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
