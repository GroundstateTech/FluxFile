#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from extended_formats import (
    ARCHIVES,
    AUDIO,
    AUDIO_TARGETS,
    EXTRA_IMAGES,
    IMAGE_OUTPUTS,
    MEDIA_TARGETS,
    VIDEO,
    convert_subtitles,
    media_command,
    render_svg,
    repack_archive,
)

APP_NAME = "FluxFile"
VERSION = "0.9.0"
MIN_PYTHON = (3, 10)
SUBPROCESS_TIMEOUT_SECONDS = 300

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
TABLE_EXTS = {".csv", ".tsv", ".json", ".xls", ".xlsx", ".ods"}
DOCUMENT_EXTS = {".doc", ".docx", ".odt", ".rtf", ".md", ".markdown", ".html", ".htm", ".txt", ".epub"}
PRESENTATION_EXTS = {".ppt", ".pptx", ".odp"}

PANDOC_INPUT_EXTS = {".md", ".markdown", ".html", ".htm", ".docx", ".odt", ".epub", ".txt"}
PANDOC_OUTPUT_EXTS = {".docx", ".odt", ".rtf", ".html", ".md", ".txt", ".epub"}

LIBREOFFICE_DOCUMENT_INPUTS = {".doc", ".docx", ".odt", ".rtf"}
LIBREOFFICE_DOCUMENT_TARGETS = {".pdf", ".docx", ".odt", ".rtf", ".html", ".txt"}
LIBREOFFICE_SHEET_INPUTS = {".xls", ".xlsx", ".ods", ".csv", ".tsv"}
LIBREOFFICE_SHEET_TARGETS = {".pdf", ".xlsx", ".ods", ".csv"}
LIBREOFFICE_PRESENTATION_INPUTS = {".ppt", ".pptx", ".odp"}
LIBREOFFICE_PRESENTATION_TARGETS = {".pdf", ".pptx", ".odp"}

SOURCE_FORMATS = [
    "any", "pdf", "doc", "docx", "odt", "rtf", "html", "md", "txt", "epub",
    "csv", "tsv", "json", "xls", "xlsx", "ods",
    "png", "jpg", "jpeg", "bmp", "gif", "tif", "tiff", "webp",
    "ppt", "pptx", "odp",
]
ALL_TARGETS = [
    "auto", "pdf", "docx", "odt", "rtf", "html", "md", "txt", "epub",
    "xlsx", "ods", "csv", "tsv", "json",
    "png", "jpg", "jpeg", "bmp", "gif", "tiff", "webp",
    "pptx", "odp",
]

TABLE_TARGETS = ["xlsx", "ods", "csv", "tsv", "json"]
IMAGE_TARGETS = ["png", "jpg", "jpeg", "bmp", "gif", "tiff", "webp", "pdf"]
DOCUMENT_TARGETS = ["pdf", "docx", "odt", "rtf", "html", "md", "txt", "epub"]
PRESENTATION_TARGETS = ["pdf", "pptx", "odp"]

IMAGE_EXTS |= {"." + fmt for fmt in EXTRA_IMAGES}
IMAGE_TARGETS += IMAGE_OUTPUTS
TABLE_EXTS.add(".jsonl")
TABLE_TARGETS.append("jsonl")
SOURCE_FORMATS += sorted(AUDIO | VIDEO | EXTRA_IMAGES | {"svg", "srt", "vtt", "jsonl"} | ARCHIVES)
ALL_TARGETS += list(dict.fromkeys(AUDIO_TARGETS + MEDIA_TARGETS + IMAGE_OUTPUTS + ["srt", "vtt", "jsonl"] + sorted(ARCHIVES)))
SOURCE_FORMATS = list(dict.fromkeys(SOURCE_FORMATS))
ALL_TARGETS = list(dict.fromkeys(ALL_TARGETS))

INTERNAL_DIR_NAMES = {
    ".git", ".hg", ".svn", ".venv", "venv", "__pycache__", "node_modules",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
}

COMPOUND_ARCHIVE_SUFFIXES = {
    ".tar.gz": "tgz",
    ".tar.bz2": "tbz2",
    ".tar.xz": "txz",
}


class ConversionCancelled(RuntimeError):
    """Raised when a running external conversion is cancelled."""


@dataclass
class Job:
    id: str
    source: str
    source_format: str
    target_format: str
    status: str = "Queued"
    engine: str = ""
    output: str = ""
    error: str = ""
    duration_seconds: float = 0.0
    input_bytes: int = 0
    output_bytes: int = 0


def which_any(*names: str) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def normalize_format(value: str) -> str:
    value = value.strip().lower().lstrip(".")
    aliases = {
        "markdown": "md",
        "htm": "html",
        "tif": "tiff",
        "tar.gz": "tgz",
        "tar.bz2": "tbz2",
        "tar.xz": "txz",
    }
    return aliases.get(value, value)


def source_format(path: Path) -> str:
    lower = path.name.lower()
    for suffix, fmt in COMPOUND_ARCHIVE_SUFFIXES.items():
        if lower.endswith(suffix):
            return fmt
    return normalize_format(path.suffix)


def source_stem(path: Path) -> str:
    lower = path.name.lower()
    for suffix in COMPOUND_ARCHIVE_SUFFIXES:
        if lower.endswith(suffix):
            return path.name[:-len(suffix)]
    return path.stem


def format_matches(selected: str, detected: str) -> bool:
    selected = normalize_format(selected)
    detected = normalize_format(detected)
    if selected in {"any", ""} or selected == detected:
        return True
    return (
        {selected, detected} <= {"jpg", "jpeg"}
        or {selected, detected} <= {"tif", "tiff"}
    )


def choose_auto_target(source: Path) -> str:
    fmt = source_format(source)
    ext = source.suffix.lower()
    if fmt in AUDIO:
        return "wav" if fmt != "wav" else "flac"
    if fmt in VIDEO:
        return "mp4" if fmt != "mp4" else "mkv"
    if fmt in {"svg", "ico", "icns"}:
        return "png"
    if fmt in {"srt", "vtt"}:
        return "vtt" if fmt == "srt" else "srt"
    if fmt == "jsonl":
        return "xlsx"
    if fmt in ARCHIVES:
        return "tgz" if fmt == "zip" else "zip"
    if ext in {".md", ".markdown", ".txt", ".rtf", ".odt", ".html", ".htm", ".epub"}:
        return "docx"
    if ext in {".csv", ".tsv", ".json", ".ods"}:
        return "xlsx"
    if ext in {".xls", ".xlsx"}:
        return "csv"
    if ext in IMAGE_EXTS and ext != ".png":
        return "png"
    if ext == ".png":
        return "jpg"
    if ext in {".doc", ".docx", ".ppt", ".pptx", ".odp"}:
        return "pdf"
    if ext == ".pdf":
        return "docx"
    return "pdf"


def compatible_targets(fmt: str) -> list[str]:
    fmt = normalize_format(fmt)
    if fmt in {"any", ""}:
        return ALL_TARGETS[:]
    if fmt in ARCHIVES:
        return ["auto", *sorted(ARCHIVES)]
    if fmt == "jsonl":
        return ["auto", *TABLE_TARGETS]
    if fmt in AUDIO:
        return ["auto", *AUDIO_TARGETS]
    if fmt in VIDEO:
        return ["auto", *MEDIA_TARGETS, *AUDIO_TARGETS]
    if fmt == "svg":
        return ["auto", "png", "pdf"]
    if fmt in {"srt", "vtt"}:
        return ["auto", "srt", "vtt"]
    ext = f".{fmt}"
    if ext == ".json":
        return ["auto", *TABLE_TARGETS]
    if ext in TABLE_EXTS:
        return ["auto", *TABLE_TARGETS, "pdf"]
    if ext in IMAGE_EXTS:
        return ["auto", *IMAGE_TARGETS]
    if fmt == "pdf":
        return ["auto", "docx", "txt", "html", "png", "jpg", "tiff"]
    if ext in PRESENTATION_EXTS:
        return ["auto", *PRESENTATION_TARGETS]
    if ext in {".doc", ".rtf"}:
        return ["auto", "pdf", "docx", "odt", "rtf", "html", "txt"]
    if ext in {".docx", ".odt"}:
        return ["auto", *DOCUMENT_TARGETS]
    if ext in {".md", ".markdown", ".html", ".htm", ".txt", ".epub"}:
        return ["auto", "docx", "odt", "rtf", "html", "md", "txt", "epub"]
    return ALL_TARGETS[:]


def resolve_output(
    source: Path,
    out_dir: Path,
    target: str,
    conflict: str,
    reserved: set[Path] | None = None,
) -> Path | None:
    """Resolve and optionally reserve an output path.

    A reservation set prevents parallel jobs with equal basenames from selecting
    the same destination before either file exists.
    """
    target = normalize_format(target)
    reserved = reserved if reserved is not None else set()
    base = out_dir / f"{source_stem(source)}.{target}"

    if base not in reserved and (not base.exists() or conflict == "overwrite"):
        reserved.add(base)
        return base
    if conflict == "skip":
        return None

    n = 2
    while True:
        candidate = out_dir / f"{source_stem(source)}_{n}.{target}"
        if candidate not in reserved and not candidate.exists():
            reserved.add(candidate)
            return candidate
        n += 1


def should_skip_intake_path(path: Path, root: Path, output_dir: Path | None = None) -> bool:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    for part in rel.parts[:-1]:
        if part.startswith(".") or part in INTERNAL_DIR_NAMES:
            return True
    if path.name.startswith("."):
        return True
    if output_dir is not None:
        try:
            path.resolve().relative_to(output_dir.resolve())
            return True
        except (ValueError, OSError):
            pass
    return False


def discover_folder_files(root: Path, recursive: bool, output_dir: Path | None = None) -> list[Path]:
    """Discover files while pruning hidden/internal trees before traversal.

    Returned paths retain the caller's lexical root. This matters on Windows,
    where resolving an 8.3 temporary-directory alias can produce a different
    long path string even though both names refer to the same directory.
    """
    root_input = root.expanduser().absolute()
    root_resolved = root_input.resolve()
    output_resolved = output_dir.expanduser().resolve() if output_dir else None
    if not recursive:
        return sorted(
            [
                p for p in root_input.iterdir()
                if p.is_file() and not should_skip_intake_path(p, root_resolved, output_resolved)
            ],
            key=lambda p: p.name.lower(),
        )

    found: list[Path] = []
    for current, dirs, files in os.walk(root_resolved, topdown=True):
        current_path = Path(current)
        kept_dirs: list[str] = []
        for name in dirs:
            candidate = current_path / name
            if name.startswith(".") or name in INTERNAL_DIR_NAMES:
                continue
            if output_resolved is not None:
                try:
                    candidate.resolve().relative_to(output_resolved)
                    continue
                except (ValueError, OSError):
                    pass
            kept_dirs.append(name)
        dirs[:] = kept_dirs
        for name in files:
            path = current_path / name
            if should_skip_intake_path(path, root_resolved, output_resolved):
                continue
            try:
                relative = path.resolve().relative_to(root_resolved)
            except (ValueError, OSError):
                continue
            found.append(root_input / relative)
    return sorted(found, key=lambda p: str(p).lower())


def create_job(path: Path, target: str, engine: "Engine") -> Job:
    path = path.expanduser().resolve()
    fmt = source_format(path)
    resolved_target = choose_auto_target(path) if normalize_format(target) == "auto" else normalize_format(target)
    selected_engine = engine.engine_for(fmt, resolved_target) or "unavailable"
    size = path.stat().st_size if path.exists() else 0
    return Job(uuid.uuid4().hex, str(path), fmt, resolved_target, engine=selected_engine, input_bytes=size)


class Engine:
    """Route conversions to local engines and atomically publish completed output."""

    def __init__(self):
        self.ffmpeg = which_any("ffmpeg")
        self.pandoc = which_any("pandoc")
        self.libreoffice = which_any("libreoffice", "soffice")
        try:
            import cairosvg  # noqa: F401
            svg_available = True
        except (ImportError, OSError):
            svg_available = False
        self._capabilities = {
            "ffmpeg": bool(self.ffmpeg),
            "cairosvg": svg_available,
            "pandoc": bool(self.pandoc),
            "libreoffice": bool(self.libreoffice),
            "pillow": importlib.util.find_spec("PIL") is not None,
            "pandas": importlib.util.find_spec("pandas") is not None,
            "pdf2docx": importlib.util.find_spec("pdf2docx") is not None,
            "pymupdf": importlib.util.find_spec("pymupdf") is not None,
        }
        self._route_cache: dict[tuple[str, str], str | None] = {}
        self._cancel_state = threading.local()
        self._image_save_exts: set[str] = set()
        if self._capabilities["pillow"]:
            from PIL import Image
            Image.init()
            registered = Image.registered_extensions()
            self._image_save_exts = {ext for ext, fmt in registered.items() if fmt in Image.SAVE}

    def capabilities(self) -> dict[str, bool]:
        return dict(self._capabilities)

    def engine_for(self, source_fmt: str, target_fmt: str) -> str | None:
        source_fmt = normalize_format(source_fmt)
        target_fmt = normalize_format(target_fmt)
        key = (source_fmt, target_fmt)
        if key in self._route_cache:
            return self._route_cache[key]
        src = f".{source_fmt}"
        dst = f".{target_fmt}"
        engine: str | None = None

        if src == dst:
            engine = "copy"
        elif source_fmt in ARCHIVES and target_fmt in ARCHIVES:
            engine = "archive"
        elif source_fmt in AUDIO | VIDEO:
            if target_fmt in AUDIO_TARGETS or (source_fmt in VIDEO and target_fmt in MEDIA_TARGETS):
                engine = "ffmpeg" if self.ffmpeg else None
        elif src == ".svg" and dst in {".png", ".pdf"}:
            engine = "cairosvg" if self._capabilities["cairosvg"] else None
        elif {src, dst} == {".srt", ".vtt"}:
            engine = "subtitles"
        elif src == ".pdf" and dst in {".html", ".png", ".jpg", ".tiff"}:
            engine = "pdf-export" if self._capabilities["pymupdf"] else None
        elif src in IMAGE_EXTS and dst in self._image_save_exts:
            engine = "pillow" if self._capabilities["pillow"] else None
        elif src in TABLE_EXTS and target_fmt in TABLE_TARGETS:
            engine = "pandas" if self._capabilities["pandas"] else None
        elif src == ".pdf" and dst == ".docx":
            engine = "pdf2docx" if self._capabilities["pdf2docx"] else None
        elif src == ".pdf" and dst == ".txt":
            engine = "pymupdf" if self._capabilities["pymupdf"] else None
        elif self.pandoc and src in PANDOC_INPUT_EXTS and dst in PANDOC_OUTPUT_EXTS:
            engine = "pandoc"
        elif self.libreoffice:
            if src in LIBREOFFICE_DOCUMENT_INPUTS and dst in LIBREOFFICE_DOCUMENT_TARGETS:
                engine = "libreoffice"
            elif src in LIBREOFFICE_SHEET_INPUTS and dst in LIBREOFFICE_SHEET_TARGETS:
                engine = "libreoffice"
            elif src in LIBREOFFICE_PRESENTATION_INPUTS and dst in LIBREOFFICE_PRESENTATION_TARGETS:
                engine = "libreoffice"

        self._route_cache[key] = engine
        return engine

    def convert(self, source: Path, output: Path, cancel_event: threading.Event | None = None) -> str:
        source = source.expanduser().resolve()
        output = output.expanduser()
        if cancel_event and cancel_event.is_set():
            raise ConversionCancelled("Conversion cancelled")
        if not source.is_file():
            raise FileNotFoundError(f"Source file not found: {source}")
        output.parent.mkdir(parents=True, exist_ok=True)

        src_fmt = source_format(source)
        dst_fmt = normalize_format(output.suffix)
        engine = self.engine_for(src_fmt, dst_fmt)
        if not engine:
            raise RuntimeError(f"No installed engine supports .{src_fmt} → .{dst_fmt}")

        temp = output.parent / f".{output.stem}.fluxfile-{uuid.uuid4().hex[:10]}{output.suffix.lower()}"
        previous_cancel_event = getattr(self._cancel_state, "event", None)
        self._cancel_state.event = cancel_event
        try:
            # Keep the historical three-argument hook so subclasses/tests that
            # override _convert_direct remain compatible with the scheduler refactor.
            self._convert_direct(engine, source, temp)
            if cancel_event and cancel_event.is_set():
                raise ConversionCancelled("Conversion cancelled")
            if not temp.exists():
                raise RuntimeError(f"{engine} completed without producing an output file")
            os.replace(temp, output)
        finally:
            if previous_cancel_event is None:
                try:
                    del self._cancel_state.event
                except AttributeError:
                    pass
            else:
                self._cancel_state.event = previous_cancel_event
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
        return engine

    def _convert_direct(self, engine: str, source: Path, output: Path) -> None:
        cancel_event = getattr(self._cancel_state, "event", None)
        if cancel_event and cancel_event.is_set():
            raise ConversionCancelled("Conversion cancelled")
        if engine == "copy":
            shutil.copy2(source, output)
        elif engine == "ffmpeg":
            self._run(media_command(self.ffmpeg, source, output), cancel_event)
        elif engine == "archive":
            repack_archive(source, output)
        elif engine == "subtitles":
            convert_subtitles(source, output)
        elif engine == "cairosvg":
            render_svg(source, output)
        elif engine == "pdf-export":
            self._pdf_export(source, output)
        elif engine == "pillow":
            self._image(source, output)
        elif engine == "pandas":
            self._table(source, output)
        elif engine == "pdf2docx":
            self._pdf_docx(source, output)
        elif engine == "pymupdf":
            self._pdf_text(source, output)
        elif engine == "pandoc":
            self._run([self.pandoc, str(source), "-o", str(output)], cancel_event)
        elif engine == "libreoffice":
            self._libreoffice(source, output, cancel_event)
        else:
            raise RuntimeError(f"Unknown conversion engine: {engine}")

    def _run(self, cmd: list[str], cancel_event: threading.Event | None = None) -> None:
        started = time.monotonic()
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        while True:
            try:
                stdout, stderr = proc.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if cancel_event and cancel_event.is_set():
                    proc.terminate()
                    try:
                        proc.communicate(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.communicate()
                    raise ConversionCancelled("Conversion cancelled")
                if time.monotonic() - started > SUBPROCESS_TIMEOUT_SECONDS:
                    proc.terminate()
                    try:
                        proc.communicate(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.communicate()
                    raise RuntimeError(f"Conversion timed out after {SUBPROCESS_TIMEOUT_SECONDS} seconds")
        if proc.returncode != 0:
            raise RuntimeError((stderr or stdout or "conversion failed").strip())

    def _image(self, source: Path, output: Path) -> None:
        from PIL import Image, ImageOps
        with Image.open(source) as opened:
            if getattr(opened, "n_frames", 1) > 1:
                if output.suffix.lower() not in {".gif", ".webp", ".png", ".tiff", ".tif", ".pdf"}:
                    raise RuntimeError("Multi-frame image: choose GIF, WebP, PNG, TIFF or PDF to preserve frames")
                from PIL import ImageSequence
                frames = [ImageOps.exif_transpose(frame.copy()) for frame in ImageSequence.Iterator(opened)]
                if output.suffix.lower() == ".pdf":
                    frames = [frame.convert("RGB") for frame in frames]
                options = {"save_all": True, "append_images": frames[1:]}
                if output.suffix.lower() in {".gif", ".webp", ".png"}:
                    options.update(duration=opened.info.get("duration", 100), loop=opened.info.get("loop", 0))
                frames[0].save(output, **options)
                return
            im = ImageOps.exif_transpose(opened)
            target = output.suffix.lower()
            if target in {".jpg", ".jpeg", ".pdf"} and im.mode not in {"RGB", "L"}:
                rgba = im.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                im = background
            im.save(output)

    def _table(self, source: Path, output: Path) -> None:
        import pandas as pd
        src, dst = source.suffix.lower(), output.suffix.lower()
        sheets: dict[str, object]
        if src == ".jsonl":
            sheets = {"Sheet1": pd.read_json(source, lines=True)}
        elif src == ".csv":
            sheets = {"Sheet1": pd.read_csv(source)}
        elif src == ".tsv":
            sheets = {"Sheet1": pd.read_csv(source, sep="\t")}
        elif src == ".json":
            data = json.loads(source.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict) and "rows" in data:
                data = data["rows"]
            elif isinstance(data, dict):
                data = [data]
            if not isinstance(data, (list, dict)):
                raise RuntimeError("JSON table source must contain an object, array, or {'rows': [...]} structure")
            sheets = {"Sheet1": pd.DataFrame(data)}
        elif src in {".xlsx", ".xls"}:
            sheets = pd.read_excel(source, sheet_name=None)
        elif src == ".ods":
            sheets = pd.read_excel(source, sheet_name=None, engine="odf")
        else:
            raise RuntimeError(f"Unsupported table source: {src}")
        if not sheets:
            raise RuntimeError("Spreadsheet source contains no readable sheets")
        if dst in {".xlsx", ".ods"}:
            writer_engine = "odf" if dst == ".ods" else "openpyxl"
            used_names: set[str] = set()
            def safe_sheet_name(raw_name: object) -> str:
                name = str(raw_name) or "Sheet"
                for ch in '[]:*?/\\':
                    name = name.replace(ch, "_")
                name = name[:31] or "Sheet"
                base = name
                suffix = 2
                while name in used_names:
                    marker = f"_{suffix}"
                    name = f"{base[:31-len(marker)]}{marker}"
                    suffix += 1
                used_names.add(name)
                return name
            with pd.ExcelWriter(output, engine=writer_engine) as writer:
                for name, df in sheets.items():
                    df.to_excel(writer, index=False, sheet_name=safe_sheet_name(name))
            return
        if len(sheets) > 1:
            raise RuntimeError(
                f"Workbook contains {len(sheets)} sheets; converting to {dst} would discard data. "
                "Choose .xlsx or .ods to preserve all sheets."
            )
        df = next(iter(sheets.values()))
        if dst == ".csv":
            df.to_csv(output, index=False)
        elif dst == ".tsv":
            df.to_csv(output, sep="\t", index=False)
        elif dst == ".jsonl":
            output.write_text(df.to_json(orient="records", lines=True), encoding="utf-8")
        elif dst == ".json":
            output.write_text(df.to_json(orient="records", indent=2), encoding="utf-8")
        else:
            raise RuntimeError(f"Unsupported table target: {dst}")

    def _pdf_export(self, source: Path, output: Path) -> None:
        import pymupdf
        with pymupdf.open(source) as doc:
            if output.suffix == ".html":
                output.write_text(
                    "<!doctype html><html><head><meta charset='utf-8'></head><body>"
                    + "\n".join(page.get_text("html") for page in doc)
                    + "</body></html>",
                    encoding="utf-8",
                )
                return
            if len(doc) != 1 and output.suffix != ".tiff":
                raise RuntimeError("Multi-page PDF: choose TIFF to preserve every page")
            from PIL import Image
            frames = []
            if sum(page.rect.width * page.rect.height * 12 for page in doc) > 512 * 1024 * 1024:
                raise RuntimeError("PDF render exceeds 512 MiB; split it into smaller documents")
            for page in doc:
                pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
                frames.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
            if not frames:
                raise RuntimeError("PDF has no pages")
            if output.suffix == ".tiff":
                frames[0].save(output, save_all=True, append_images=frames[1:])
            else:
                frames[0].save(output)

    def _pdf_docx(self, source: Path, output: Path) -> None:
        from pdf2docx import Converter
        cv = Converter(str(source))
        try:
            cv.convert(str(output))
        finally:
            cv.close()

    def _pdf_text(self, source: Path, output: Path) -> None:
        import pymupdf
        doc = pymupdf.open(source)
        try:
            output.write_text("\n\n".join(page.get_text() for page in doc), encoding="utf-8")
        finally:
            doc.close()

    def _libreoffice(self, source: Path, output: Path, cancel_event: threading.Event | None) -> None:
        work_dir = output.parent / f".fluxfile-lo-{uuid.uuid4().hex[:8]}"
        profile_dir = work_dir / "profile"
        converted_dir = work_dir / "converted"
        profile_dir.mkdir(parents=True, exist_ok=True)
        converted_dir.mkdir(parents=True, exist_ok=True)
        target = output.suffix.lower().lstrip(".")
        profile_uri = profile_dir.resolve().as_uri()
        try:
            self._run([
                self.libreoffice,
                f"-env:UserInstallation={profile_uri}",
                "--headless", "--nologo", "--nodefault", "--nofirststartwizard", "--norestore",
                "--convert-to", target, "--outdir", str(converted_dir), str(source),
            ], cancel_event)
            produced = converted_dir / f"{source.stem}.{target}"
            if not produced.exists():
                matches = [p for p in converted_dir.iterdir() if p.is_file() and p.stem == source.stem]
                if not matches:
                    raise RuntimeError("LibreOffice did not produce an output file")
                produced = matches[0]
            shutil.move(str(produced), str(output))
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
