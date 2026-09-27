#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "FluxFile"
VERSION = "0.6.0"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
TABLE_EXTS = {".csv", ".tsv", ".json", ".xlsx", ".ods"}
PANDOC_EXTS = {".md", ".markdown", ".html", ".htm", ".docx", ".odt", ".rtf", ".epub", ".txt"}
OFFICE_EXTS = {".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp"}

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
PANDOC_TARGETS = ["docx", "odt", "rtf", "html", "md", "txt", "epub"]
OFFICE_TARGETS = ["pdf", "docx", "odt", "xlsx", "ods", "pptx", "odp", "html", "txt"]


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
    if ext in TABLE_EXTS or fmt == "xls":
        return ["auto", *TABLE_TARGETS, "pdf"]
    if ext in IMAGE_EXTS:
        return ["auto", *IMAGE_TARGETS]
    if fmt == "pdf":
        return ["auto", "docx", "txt"]
    if ext in PANDOC_EXTS:
        values = ["auto", *PANDOC_TARGETS]
        if ext in OFFICE_EXTS:
            values.extend(x for x in OFFICE_TARGETS if x not in values)
        return values
    if ext in OFFICE_EXTS:
        return ["auto", *OFFICE_TARGETS]
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


class Engine:
    def __init__(self):
        self.pandoc = which_any("pandoc")
        self.libreoffice = which_any("libreoffice", "soffice")

    def capabilities(self) -> dict[str, bool]:
        # Do not import optional libraries just to detect them. Some dependencies
        # emit warnings at import time; find_spec keeps startup/doctor output clean.
        return {
            "pandoc": bool(self.pandoc),
            "libreoffice": bool(self.libreoffice),
            "pillow": importlib.util.find_spec("PIL") is not None,
            "pandas": importlib.util.find_spec("pandas") is not None,
            "pdf2docx": importlib.util.find_spec("pdf2docx") is not None,
            "pymupdf": importlib.util.find_spec("pymupdf") is not None,
        }

    def engine_for(self, source_fmt: str, target_fmt: str) -> str | None:
        src = f".{normalize_format(source_fmt)}"
        dst = f".{normalize_format(target_fmt)}"
        caps = self.capabilities()

        if src == dst:
            return "copy"
        if src in IMAGE_EXTS and (dst in IMAGE_EXTS or dst == ".pdf"):
            return "pillow" if caps["pillow"] else None
        if (src in TABLE_EXTS or src == ".xls") and dst in TABLE_EXTS:
            return "pandas" if caps["pandas"] else None
        if src == ".pdf" and dst == ".docx":
            return "pdf2docx" if caps["pdf2docx"] else None
        if src == ".pdf" and dst == ".txt":
            return "pymupdf" if caps["pymupdf"] else None
        if self.pandoc and src in PANDOC_EXTS and dst in {f".{x}" for x in PANDOC_TARGETS}:
            return "pandoc"
        if self.libreoffice and (src in OFFICE_EXTS or src in TABLE_EXTS) and dst in {f".{x}" for x in OFFICE_TARGETS}:
            return "libreoffice"
        return None

    def convert(self, source: Path, output: Path) -> str:
        src_fmt = source_format(source)
        dst_fmt = normalize_format(output.suffix)
        engine = self.engine_for(src_fmt, dst_fmt)
        if not engine:
            raise RuntimeError(f"No installed engine supports .{src_fmt} → .{dst_fmt}")

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
        return engine

    def _run(self, cmd: list[str]) -> None:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "conversion failed").strip())

    def _image(self, source: Path, output: Path) -> None:
        from PIL import Image

        with Image.open(source) as im:
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
        if src == ".csv":
            df = pd.read_csv(source)
        elif src == ".tsv":
            df = pd.read_csv(source, sep="\t")
        elif src == ".json":
            data = json.loads(source.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data = data.get("rows", [data])
            df = pd.DataFrame(data)
        elif src in {".xlsx", ".xls"}:
            df = pd.read_excel(source)
        elif src == ".ods":
            df = pd.read_excel(source, engine="odf")
        else:
            raise RuntimeError(f"Unsupported table source: {src}")

        if dst == ".csv":
            df.to_csv(output, index=False)
        elif dst == ".tsv":
            df.to_csv(output, sep="\t", index=False)
        elif dst == ".json":
            output.write_text(df.to_json(orient="records", indent=2), encoding="utf-8")
        elif dst == ".xlsx":
            df.to_excel(output, index=False)
        elif dst == ".ods":
            df.to_excel(output, index=False, engine="odf")
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
        output.parent.mkdir(parents=True, exist_ok=True)
        target = output.suffix.lower().lstrip(".")
        temp_dir = output.parent / f".fluxfile-lo-{uuid.uuid4().hex[:8]}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._run([self.libreoffice, "--headless", "--convert-to", target, "--outdir", str(temp_dir), str(source)])
            produced = temp_dir / f"{source.stem}.{target}"
            if not produced.exists():
                matches = list(temp_dir.glob(f"{source.stem}.*"))
                if not matches:
                    raise RuntimeError("LibreOffice did not produce an output file")
                produced = matches[0]
            shutil.move(str(produced), str(output))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


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

        self._build()
        self._refresh_engines()
        self._update_target_choices()

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

        ttk.Button(header, text="Apply plan to queue", command=self.apply_plan_to_queue).grid(row=0, column=5)
        ttk.Label(header, textvariable=self.plan_text).grid(row=0, column=6, sticky="e", padx=(12, 0))

        top = ttk.Frame(self, padding=(12, 6, 12, 6))
        top.grid(row=1, column=0, sticky="ew")
        top.columnconfigure(6, weight=1)

        ttk.Button(top, text="Add files", command=self.add_files).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(top, text="Add folder", command=self.add_folder).grid(row=0, column=1, padx=(0, 12))
        ttk.Checkbutton(top, text="Include subfolders", variable=self.recursive).grid(row=0, column=2, padx=(0, 18))
        ttk.Label(top, text="If output exists").grid(row=0, column=3, padx=(0, 6))
        ttk.Combobox(
            top, textvariable=self.conflict, values=["suffix", "skip", "overwrite"], state="readonly", width=12
        ).grid(row=0, column=4)
        ttk.Button(top, text="Remove selected", command=self.remove_selected).grid(row=0, column=5, padx=(12, 8))
        ttk.Button(top, text="Clear queue", command=self.clear).grid(row=0, column=6, sticky="e")

        out = ttk.Frame(self, padding=(12, 6, 12, 8))
        out.grid(row=2, column=0, sticky="ew")
        out.columnconfigure(1, weight=1)
        ttk.Label(out, text="Output folder").grid(row=0, column=0, padx=(0, 8))
        ttk.Entry(out, textvariable=self.output_dir).grid(row=0, column=1, sticky="ew")
        ttk.Button(out, text="Browse", command=self.pick_output).grid(row=0, column=2, padx=(8, 0))

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
        ttk.Button(bottom, text="Rescan engines", command=self._refresh_engines).grid(row=0, column=2, padx=8)
        ttk.Button(bottom, text="Open output folder", command=self.open_output_folder).grid(row=0, column=3, padx=8)
        self.run_btn = ttk.Button(bottom, text="Convert queue", command=self.run_queue)
        self.run_btn.grid(row=0, column=4)

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
        paths = root.rglob("*") if self.recursive.get() else root.iterdir()
        self._add_paths([p for p in paths if p.is_file() and not p.name.startswith(".")])

    def _add_paths(self, paths: list[Path]):
        existing = {j.source for j in self.jobs}
        selected_source = normalize_format(self.source_choice.get())
        selected_target = normalize_format(self.target_choice.get())

        skipped_wrong_type = 0
        for p in paths:
            fmt = source_format(p)
            if selected_source != "any" and fmt != selected_source:
                # jpg/jpeg and tif/tiff are treated as equivalent selection families.
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

        unavailable = [j for j in self.jobs if self.engine.engine_for(j.source_format, j.target_format) is None]
        if unavailable:
            preview = "\n".join(
                f"{Path(j.source).name}: .{j.source_format} → .{j.target_format}"
                for j in unavailable[:8]
            )
            more = f"\n…and {len(unavailable)-8} more" if len(unavailable) > 8 else ""
            messagebox.showerror(
                APP_NAME,
                "Some queued conversions are unsupported with the installed engines:\n\n"
                + preview + more
                + "\n\nChange the From/To plan, install Pandoc/LibreOffice, or rescan engines."
            )
            return

        out_dir = Path(self.output_dir.get()).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        conflict = self.conflict.get()
        jobs_snapshot = list(self.jobs)
        self.run_btn.configure(state="disabled")
        threading.Thread(
            target=self._worker,
            args=(out_dir, conflict, jobs_snapshot),
            daemon=True,
        ).start()

    def _worker(self, out_dir: Path, conflict: str, jobs: list[Job]):
        started = time.time()
        report = []

        for job in jobs:
            source = Path(job.source)
            target = normalize_format(job.target_format)
            output = resolve_output(source, out_dir, target, conflict)
            if output is None:
                job.status = "Skipped"
                job.error = "Output exists"
                report.append(asdict(job))
                self.after(0, self.render)
                continue

            try:
                job.status = "Converting"
                job.error = ""
                self.after(0, self.render)
                engine = self.engine.convert(source, output)
                job.status = "Done"
                job.engine = engine
                job.output = str(output)
                item = asdict(job)
                report.append(item)
            except Exception as exc:
                job.status = "Failed"
                job.error = str(exc)
                report.append(asdict(job))
            self.after(0, self.render)

        stamp = time.strftime("%Y%m%d-%H%M%S")
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

        import csv
        with csv_report.open("w", newline="", encoding="utf-8") as fh:
            fields = ["source", "source_format", "target_format", "engine", "status", "output", "error"]
            writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(report)

        self.after(0, lambda: self.run_btn.configure(state="normal"))
        self.after(
            0,
            lambda: messagebox.showinfo(
                APP_NAME,
                f"Conversion pass finished.\n\nJSON report: {json_report.name}\nCSV report: {csv_report.name}"
            ),
        )


if __name__ == "__main__":
    FluxFileApp().mainloop()
