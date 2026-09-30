#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "FluxFile"
VERSION = "0.7.0"
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

INTERNAL_DIR_NAMES = {
    ".git", ".hg", ".svn", ".venv", "venv", "__pycache__", "node_modules",
}


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
    }
    return aliases.get(value, value)


def source_format(path: Path) -> str:
    return normalize_format(path.suffix)


def choose_auto_target(source: Path) -> str:
    ext = source.suffix.lower()
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

    ext = f".{fmt}"
    if ext == ".json":
        return ["auto", *TABLE_TARGETS]
    if ext in TABLE_EXTS:
        return ["auto", *TABLE_TARGETS, "pdf"]
    if ext in IMAGE_EXTS:
        return ["auto", *IMAGE_TARGETS]
    if fmt == "pdf":
        return ["auto", "docx", "txt"]
    if ext in PRESENTATION_EXTS:
        return ["auto", *PRESENTATION_TARGETS]
    if ext in {".doc", ".rtf"}:
        return ["auto", "pdf", "docx", "odt", "rtf", "html", "txt"]
    if ext in {".docx", ".odt"}:
        return ["auto", *DOCUMENT_TARGETS]
    if ext in {".md", ".markdown", ".html", ".htm", ".txt", ".epub"}:
        return ["auto", "docx", "odt", "rtf", "html", "md", "txt", "epub"]
    return ALL_TARGETS[:]


def resolve_output(source: Path, out_dir: Path, target: str, conflict: str) -> Path | None:
    target = normalize_format(target)
    base = out_dir / f"{source.stem}.{target}"
    if not base.exists() or conflict == "overwrite":
        return base
    if conflict == "skip":
        return None
    n = 2
    while True:
        candidate = out_dir / f"{source.stem}_{n}.{target}"
        if not candidate.exists():
            return candidate
        n += 1


def should_skip_intake_path(path: Path, root: Path, output_dir: Path | None = None) -> bool:
    """Return True for hidden/internal paths and files inside the active output directory."""
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


def discover_folder_files(
    root: Path,
    recursive: bool,
    output_dir: Path | None = None,
) -> list[Path]:
    iterator = root.rglob("*") if recursive else root.iterdir()
    files: list[Path] = []
    for path in iterator:
        if not path.is_file():
            continue
        if should_skip_intake_path(path, root, output_dir):
            continue
        files.append(path)
    return files


class Engine:
    def __init__(self):
        self.pandoc = which_any("pandoc")
        self.libreoffice = which_any("libreoffice", "soffice")
        self._capabilities = {
            "pandoc": bool(self.pandoc),
            "libreoffice": bool(self.libreoffice),
            "pillow": importlib.util.find_spec("PIL") is not None,
            "pandas": importlib.util.find_spec("pandas") is not None,
            "pdf2docx": importlib.util.find_spec("pdf2docx") is not None,
            "pymupdf": importlib.util.find_spec("pymupdf") is not None,
        }

    def capabilities(self) -> dict[str, bool]:
        return dict(self._capabilities)

    def engine_for(self, source_fmt: str, target_fmt: str) -> str | None:
        src = f".{normalize_format(source_fmt)}"
        dst = f".{normalize_format(target_fmt)}"

        if src == dst:
            return "copy"

        if src in IMAGE_EXTS and (dst in IMAGE_EXTS or dst == ".pdf"):
            return "pillow" if self._capabilities["pillow"] else None

        if src in TABLE_EXTS and dst in TABLE_EXTS:
            return "pandas" if self._capabilities["pandas"] else None

        if src == ".pdf" and dst == ".docx":
            return "pdf2docx" if self._capabilities["pdf2docx"] else None

        if src == ".pdf" and dst == ".txt":
            return "pymupdf" if self._capabilities["pymupdf"] else None

        if (
            self.pandoc
            and src in PANDOC_INPUT_EXTS
            and dst in PANDOC_OUTPUT_EXTS
        ):
            return "pandoc"

        if self.libreoffice:
            if src in LIBREOFFICE_DOCUMENT_INPUTS and dst in LIBREOFFICE_DOCUMENT_TARGETS:
                return "libreoffice"
            if src in LIBREOFFICE_SHEET_INPUTS and dst in LIBREOFFICE_SHEET_TARGETS:
                return "libreoffice"
            if src in LIBREOFFICE_PRESENTATION_INPUTS and dst in LIBREOFFICE_PRESENTATION_TARGETS:
                return "libreoffice"

        return None

    def convert(self, source: Path, output: Path) -> str:
        source = source.expanduser().resolve()
        output = output.expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)

        src_fmt = source_format(source)
        dst_fmt = normalize_format(output.suffix)
        engine = self.engine_for(src_fmt, dst_fmt)
        if not engine:
            raise RuntimeError(f"No installed engine supports .{src_fmt} → .{dst_fmt}")

        temp = output.parent / (
            f".{output.stem}.fluxfile-{uuid.uuid4().hex[:10]}{output.suffix.lower()}"
        )
        try:
            self._convert_direct(engine, source, temp)
            if not temp.exists():
                raise RuntimeError(f"{engine} completed without producing an output file")
            os.replace(temp, output)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
        return engine

    def _convert_direct(self, engine: str, source: Path, output: Path) -> None:
        if engine == "copy":
            shutil.copy2(source, output)
        elif engine == "pillow":
            self._image(source, output)
        elif engine == "pandas":
            self._table(source, output)
        elif engine == "pdf2docx":
            self._pdf_docx(source, output)
        elif engine == "pymupdf":
            self._pdf_text(source, output)
        elif engine == "pandoc":
            self._run([self.pandoc, str(source), "-o", str(output)])
        elif engine == "libreoffice":
            self._libreoffice(source, output)
        else:
            raise RuntimeError(f"Unknown conversion engine: {engine}")

    def _run(self, cmd: list[str]) -> None:
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Conversion timed out after {SUBPROCESS_TIMEOUT_SECONDS} seconds"
            ) from exc
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "conversion failed").strip())

    def _image(self, source: Path, output: Path) -> None:
        from PIL import Image, ImageOps

        with Image.open(source) as opened:
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

        if src == ".csv":
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
        elif dst == ".json":
            output.write_text(df.to_json(orient="records", indent=2), encoding="utf-8")
        else:
            raise RuntimeError(f"Unsupported table target: {dst}")

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
            text = "\n\n".join(page.get_text() for page in doc)
            output.write_text(text, encoding="utf-8")
        finally:
            doc.close()

    def _libreoffice(self, source: Path, output: Path) -> None:
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
                "--headless",
                "--nologo",
                "--nodefault",
                "--nofirststartwizard",
                "--norestore",
                "--convert-to",
                target,
                "--outdir",
                str(converted_dir),
                str(source),
            ])
            produced = converted_dir / f"{source.stem}.{target}"
            if not produced.exists():
                matches = [
                    p for p in converted_dir.iterdir()
                    if p.is_file() and p.stem == source.stem
                ]
                if not matches:
                    raise RuntimeError("LibreOffice did not produce an output file")
                produced = matches[0]
            shutil.move(str(produced), str(output))
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)


class FluxFileApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {VERSION}")
        self.geometry("1180x760")
        self.minsize(960, 640)

        self.engine = Engine()
        self.jobs: list[Job] = []
        self.output_dir = tk.StringVar(value=str(Path.cwd() / "converted"))
        self.source_choice = tk.StringVar(value="any")
        self.target_choice = tk.StringVar(value="auto")
        self.conflict = tk.StringVar(value="suffix")
        self.recursive = tk.BooleanVar(value=False)
        self.plan_text = tk.StringVar(value="Choose a source and target format.")
        self.status_text = tk.StringVar(value="Ready")
        self._running = False
        self._ui_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        self._build()
        self._refresh_engines()
        self._update_target_choices()
        self.after(75, self._drain_ui_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        header = ttk.Frame(self, padding=(12, 12, 12, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(6, weight=1)

        ttk.Label(header, text="Conversion plan").grid(row=0, column=0, padx=(0, 8))
        ttk.Label(header, text="From").grid(row=0, column=1, padx=(0, 5))
        self.source_box = ttk.Combobox(
            header, textvariable=self.source_choice, values=SOURCE_FORMATS, state="readonly", width=11
        )
        self.source_box.grid(row=0, column=2, padx=(0, 12))
        self.source_box.bind("<<ComboboxSelected>>", lambda _e: self._update_target_choices())

        ttk.Label(header, text="To").grid(row=0, column=3, padx=(0, 5))
        self.target_box = ttk.Combobox(
            header, textvariable=self.target_choice, values=ALL_TARGETS, state="readonly", width=11
        )
        self.target_box.grid(row=0, column=4, padx=(0, 12))
        self.target_box.bind("<<ComboboxSelected>>", lambda _e: self._update_plan_status())

        self.apply_btn = ttk.Button(header, text="Apply plan to queue", command=self.apply_plan_to_queue)
        self.apply_btn.grid(row=0, column=5)
        ttk.Label(header, textvariable=self.plan_text).grid(row=0, column=6, sticky="e", padx=(12, 0))

        top = ttk.Frame(self, padding=(12, 6, 12, 6))
        top.grid(row=1, column=0, sticky="ew")
        top.columnconfigure(6, weight=1)

        self.add_files_btn = ttk.Button(top, text="Add files", command=self.add_files)
        self.add_files_btn.grid(row=0, column=0, padx=(0, 8))
        self.add_folder_btn = ttk.Button(top, text="Add folder", command=self.add_folder)
        self.add_folder_btn.grid(row=0, column=1, padx=(0, 12))
        self.recursive_btn = ttk.Checkbutton(top, text="Include subfolders", variable=self.recursive)
        self.recursive_btn.grid(row=0, column=2, padx=(0, 18))
        ttk.Label(top, text="If output exists").grid(row=0, column=3, padx=(0, 6))
        self.conflict_box = ttk.Combobox(
            top, textvariable=self.conflict, values=["suffix", "skip", "overwrite"], state="readonly", width=12
        )
        self.conflict_box.grid(row=0, column=4)
        self.remove_btn = ttk.Button(top, text="Remove selected", command=self.remove_selected)
        self.remove_btn.grid(row=0, column=5, padx=(12, 8))
        self.clear_btn = ttk.Button(top, text="Clear queue", command=self.clear)
        self.clear_btn.grid(row=0, column=6, sticky="e")

        out = ttk.Frame(self, padding=(12, 6, 12, 8))
        out.grid(row=2, column=0, sticky="ew")
        out.columnconfigure(1, weight=1)
        ttk.Label(out, text="Output folder").grid(row=0, column=0, padx=(0, 8))
        self.output_entry = ttk.Entry(out, textvariable=self.output_dir)
        self.output_entry.grid(row=0, column=1, sticky="ew")
        self.output_browse_btn = ttk.Button(out, text="Browse", command=self.pick_output)
        self.output_browse_btn.grid(row=0, column=2, padx=(8, 0))

        frame = ttk.Frame(self, padding=(12, 0, 12, 8))
        frame.grid(row=3, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            frame,
            columns=("source", "from", "to", "engine", "status", "output"),
            show="headings",
            selectmode="extended",
        )
        columns = [
            ("source", "Source file", 350),
            ("from", "From", 70),
            ("to", "To", 70),
            ("engine", "Engine", 95),
            ("status", "Status", 105),
            ("output", "Output / Error", 360),
        ]
        for key, label, width in columns:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")

        scroll_y = ttk.Scrollbar(frame, command=self.tree.yview)
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        scroll_x.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        bottom = ttk.Frame(self, padding=12)
        bottom.grid(row=4, column=0, sticky="ew")
        bottom.columnconfigure(1, weight=1)
        self.engine_label = ttk.Label(bottom, text="")
        self.engine_label.grid(row=0, column=0, sticky="w")
        ttk.Label(bottom, textvariable=self.status_text).grid(row=0, column=1, sticky="e", padx=12)
        self.rescan_btn = ttk.Button(bottom, text="Rescan engines", command=self._refresh_engines)
        self.rescan_btn.grid(row=0, column=2, padx=8)
        self.open_btn = ttk.Button(bottom, text="Open output folder", command=self.open_output_folder)
        self.open_btn.grid(row=0, column=3, padx=8)
        self.run_btn = ttk.Button(bottom, text="Convert queue", command=self.run_queue)
        self.run_btn.grid(row=0, column=4)

        self._mutable_widgets = [
            self.source_box, self.target_box, self.apply_btn,
            self.add_files_btn, self.add_folder_btn, self.recursive_btn,
            self.conflict_box, self.remove_btn, self.clear_btn,
            self.output_entry, self.output_browse_btn, self.rescan_btn,
        ]

    def _set_running(self, running: bool):
        self._running = running
        for widget in self._mutable_widgets:
            if isinstance(widget, ttk.Combobox):
                widget.configure(state="disabled" if running else "readonly")
            else:
                widget.configure(state="disabled" if running else "normal")
        self.run_btn.configure(state="disabled" if running else "normal")
        self.status_text.set("Converting…" if running else self._queue_summary())

    def _queue_summary(self) -> str:
        total = len(self.jobs)
        if not total:
            return "Ready"
        done = sum(j.status == "Done" for j in self.jobs)
        failed = sum(j.status in {"Failed", "Unsupported"} for j in self.jobs)
        return f"{total} queued · {done} done · {failed} failed/unsupported"

    def _update_target_choices(self):
        values = compatible_targets(self.source_choice.get())
        self.target_box.configure(values=values)
        if self.target_choice.get() not in values:
            self.target_choice.set("auto")
        self._update_plan_status()

    def _update_plan_status(self):
        src = normalize_format(self.source_choice.get())
        target = normalize_format(self.target_choice.get())
        if src == "any":
            self.plan_text.set("Mixed input mode · target chosen per file" if target == "auto" else f"Mixed input → .{target}")
            return
        if target == "auto":
            self.plan_text.set(f".{src} → automatic recommended output")
            return
        engine = self.engine.engine_for(src, target)
        if engine:
            self.plan_text.set(f".{src} → .{target} · {engine}")
        else:
            self.plan_text.set(f".{src} → .{target} · engine unavailable/unsupported")

    def add_files(self):
        fmt = normalize_format(self.source_choice.get())
        if fmt == "any":
            filetypes = [("Supported / all files", "*.*")]
        else:
            variants = {
                "jpg": "*.jpg *.jpeg",
                "jpeg": "*.jpg *.jpeg",
                "tiff": "*.tif *.tiff",
                "html": "*.html *.htm",
                "md": "*.md *.markdown",
            }
            filetypes = [(f"{fmt.upper()} files", variants.get(fmt, f"*.{fmt}")), ("All files", "*.*")]
        paths = filedialog.askopenfilenames(title="Choose files to convert", filetypes=filetypes)
        self._add_paths([Path(p) for p in paths])

    def add_folder(self):
        folder = filedialog.askdirectory(title="Choose a folder")
        if not folder:
            return
        root = Path(folder)
        output_dir = Path(self.output_dir.get()).expanduser()
        paths = discover_folder_files(root, self.recursive.get(), output_dir)
        self._add_paths(paths)

    def _add_paths(self, paths: list[Path]):
        existing = {j.source for j in self.jobs}
        selected_source = normalize_format(self.source_choice.get())
        selected_target = normalize_format(self.target_choice.get())

        skipped_wrong_type = 0
        for p in paths:
            fmt = source_format(p)
            if selected_source != "any" and fmt != selected_source:
                equivalent = (
                    {selected_source, fmt} <= {"jpg", "jpeg"}
                    or {selected_source, fmt} <= {"tif", "tiff"}
                )
                if not equivalent:
                    skipped_wrong_type += 1
                    continue

            sp = str(p.resolve())
            if sp in existing:
                continue

            target = choose_auto_target(p) if selected_target == "auto" else selected_target
            engine = self.engine.engine_for(fmt, target) or "unavailable"
            self.jobs.append(Job(uuid.uuid4().hex, sp, fmt, target, engine=engine))
            existing.add(sp)

        self.render()
        if skipped_wrong_type:
            messagebox.showinfo(APP_NAME, f"Skipped {skipped_wrong_type} file(s) that did not match the selected From format.")

    def apply_plan_to_queue(self):
        selected_source = normalize_format(self.source_choice.get())
        selected_target = normalize_format(self.target_choice.get())
        changed = 0
        unsupported = 0

        for job in self.jobs:
            if selected_source != "any" and job.source_format != selected_source:
                equivalent = (
                    {selected_source, job.source_format} <= {"jpg", "jpeg"}
                    or {selected_source, job.source_format} <= {"tif", "tiff"}
                )
                if not equivalent:
                    continue
            source = Path(job.source)
            target = choose_auto_target(source) if selected_target == "auto" else selected_target
            job.target_format = target
            job.engine = self.engine.engine_for(job.source_format, target) or "unavailable"
            job.status = "Queued"
            job.output = ""
            job.error = ""
            changed += 1
            if job.engine == "unavailable":
                unsupported += 1

        self.render()
        self.plan_text.set(f"Applied to {changed} queued file(s); {unsupported} need another engine/target.")

    def pick_output(self):
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self.output_dir.set(folder)

    def clear(self):
        self.jobs.clear()
        self.render()

    def remove_selected(self):
        selected = set(self.tree.selection())
        if not selected:
            return
        self.jobs = [j for j in self.jobs if j.id not in selected]
        self.render()

    def render(self):
        self.tree.delete(*self.tree.get_children())
        for job in self.jobs:
            tail = job.output or job.error
            self.tree.insert(
                "", "end", iid=job.id,
                values=(job.source, job.source_format, job.target_format, job.engine, job.status, tail),
            )
        if not self._running:
            self.status_text.set(self._queue_summary())

    def _refresh_engines(self):
        self.engine = Engine()
        caps = self.engine.capabilities()
        active = ", ".join(name for name, ok in caps.items() if ok) or "standard library only"
        self.engine_label.configure(text=f"Engines: {active}")
        for job in self.jobs:
            job.engine = self.engine.engine_for(job.source_format, job.target_format) or "unavailable"
        self.render()
        self._update_plan_status()

    def open_output_folder(self):
        folder = Path(self.output_dir.get()).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", str(folder)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                opener = which_any("xdg-open", "gio")
                if not opener:
                    raise RuntimeError("No desktop folder opener found (xdg-open/gio).")
                if Path(opener).name == "gio":
                    subprocess.Popen([opener, "open", str(folder)])
                else:
                    subprocess.Popen([opener, str(folder)])
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not open output folder:\n{exc}")

    def run_queue(self):
        if not self.jobs:
            messagebox.showinfo(APP_NAME, "Add files to the queue first.")
            return

        supported = []
        unsupported = []
        for job in self.jobs:
            engine = self.engine.engine_for(job.source_format, job.target_format)
            job.engine = engine or "unavailable"
            if engine:
                supported.append(job)
            else:
                unsupported.append(job)

        if not supported:
            preview = "\n".join(
                f"{Path(j.source).name}: .{j.source_format} → .{j.target_format}"
                for j in unsupported[:8]
            )
            messagebox.showerror(
                APP_NAME,
                "No queued conversion is currently supported by the installed engines.\n\n"
                + preview
                + "\n\nChange the plan, install Pandoc/LibreOffice, or rescan engines."
            )
            self.render()
            return

        if unsupported:
            for job in unsupported:
                job.status = "Unsupported"
                job.error = f"No installed engine supports .{job.source_format} → .{job.target_format}"
            messagebox.showinfo(
                APP_NAME,
                f"{len(unsupported)} unsupported job(s) will be recorded and skipped; "
                f"{len(supported)} supported job(s) will continue."
            )

        out_dir = Path(self.output_dir.get()).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        conflict = self.conflict.get()
        jobs_snapshot = list(self.jobs)
        self._set_running(True)
        threading.Thread(
            target=self._worker,
            args=(out_dir, conflict, jobs_snapshot),
            daemon=True,
        ).start()

    def _worker(self, out_dir: Path, conflict: str, jobs: list[Job]):
        started = time.time()
        report: list[dict] = []

        try:
            for job in jobs:
                if self.engine.engine_for(job.source_format, job.target_format) is None:
                    job.status = "Unsupported"
                    if not job.error:
                        job.error = f"No installed engine supports .{job.source_format} → .{job.target_format}"
                    report.append(asdict(job))
                    self._ui_queue.put(("render", None))
                    continue

                source = Path(job.source)
                target = normalize_format(job.target_format)
                output = resolve_output(source, out_dir, target, conflict)
                if output is None:
                    job.status = "Skipped"
                    job.error = "Output exists"
                    report.append(asdict(job))
                    self._ui_queue.put(("render", None))
                    continue

                try:
                    job.status = "Converting"
                    job.error = ""
                    self._ui_queue.put(("render", None))
                    engine = self.engine.convert(source, output)
                    job.status = "Done"
                    job.engine = engine
                    job.output = str(output)
                    report.append(asdict(job))
                except Exception as exc:
                    job.status = "Failed"
                    job.error = str(exc)
                    report.append(asdict(job))
                self._ui_queue.put(("render", None))

            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            json_report = out_dir / f"fluxfile-report-{stamp}.json"
            csv_report = out_dir / f"fluxfile-report-{stamp}.csv"

            payload = {
                "fluxfile_version": VERSION,
                "started_unix": started,
                "finished_unix": time.time(),
                "platform": sys.platform,
                "engines": self.engine.capabilities(),
                "jobs": report,
            }
            json_report.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            with csv_report.open("w", newline="", encoding="utf-8") as fh:
                fields = ["source", "source_format", "target_format", "engine", "status", "output", "error"]
                writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(report)

            summary = (
                f"Conversion pass finished.\n\n"
                f"Done: {sum(j['status'] == 'Done' for j in report)}\n"
                f"Failed: {sum(j['status'] == 'Failed' for j in report)}\n"
                f"Unsupported: {sum(j['status'] == 'Unsupported' for j in report)}\n"
                f"Skipped: {sum(j['status'] == 'Skipped' for j in report)}\n\n"
                f"JSON report: {json_report.name}\n"
                f"CSV report: {csv_report.name}"
            )
            self._ui_queue.put(("complete", summary))
        except Exception as exc:
            self._ui_queue.put(("worker_error", str(exc)))
        finally:
            self._ui_queue.put(("running", False))

    def _drain_ui_queue(self):
        try:
            while True:
                action, payload = self._ui_queue.get_nowait()
                if action == "render":
                    self.render()
                elif action == "running":
                    self._set_running(bool(payload))
                elif action == "complete":
                    self.render()
                    messagebox.showinfo(APP_NAME, str(payload))
                elif action == "worker_error":
                    self.render()
                    messagebox.showerror(APP_NAME, f"Conversion pass stopped unexpectedly:\n{payload}")
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(75, self._drain_ui_queue)

    def _on_close(self):
        if self._running:
            close = messagebox.askyesno(
                APP_NAME,
                "A conversion pass is still running. Closing FluxFile now will stop the background worker.\n\nClose anyway?"
            )
            if not close:
                return
        self.destroy()


if __name__ == "__main__":
    if sys.version_info < MIN_PYTHON:
        raise SystemExit(
            f"FluxFile requires Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+; "
            f"found {sys.version.split()[0]}"
        )
    FluxFileApp().mainloop()
