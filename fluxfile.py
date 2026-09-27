#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "FluxFile"
VERSION = "0.5.0"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
TABLE_EXTS = {".csv", ".tsv", ".json", ".xlsx", ".ods"}
PANDOC_EXTS = {".md", ".markdown", ".html", ".htm", ".docx", ".odt", ".rtf", ".epub", ".txt"}
OFFICE_EXTS = {".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp"}
TARGETS = ["auto", "pdf", "docx", "odt", "html", "md", "txt", "xlsx", "csv", "json", "png", "jpg", "webp"]

@dataclass
class Job:
    id: str
    source: str
    target_format: str
    status: str = "Queued"
    output: str = ""
    error: str = ""

def which_any(*names: str) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None

def normalize_target(target: str) -> str:
    return target.strip().lower().lstrip(".")

def choose_auto_target(source: Path) -> str:
    ext = source.suffix.lower()
    if ext in {".md", ".markdown", ".txt", ".rtf", ".odt", ".html", ".htm"}:
        return "docx"
    if ext in {".csv", ".tsv", ".json", ".ods"}:
        return "xlsx"
    if ext in IMAGE_EXTS and ext != ".png":
        return "png"
    if ext == ".png":
        return "jpg"
    if ext in {".doc", ".docx", ".ppt", ".pptx", ".odp"}:
        return "pdf"
    if ext == ".pdf":
        return "docx"
    return "pdf"

def resolve_output(source: Path, out_dir: Path, target: str, conflict: str) -> Path | None:
    target = normalize_target(target)
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

    def capabilities(self) -> dict:
        caps = {
            "pandoc": bool(self.pandoc),
            "libreoffice": bool(self.libreoffice),
            "pillow": False,
            "pandas": False,
            "pdf2docx": False,
        }
        try:
            import PIL  # noqa
            caps["pillow"] = True
        except Exception:
            pass
        try:
            import pandas  # noqa
            caps["pandas"] = True
        except Exception:
            pass
        try:
            import pdf2docx  # noqa
            caps["pdf2docx"] = True
        except Exception:
            pass
        return caps

    def convert(self, source: Path, output: Path) -> str:
        src = source.suffix.lower()
        dst = output.suffix.lower()

        if src == dst:
            shutil.copy2(source, output)
            return "copy"

        if src in IMAGE_EXTS and dst in IMAGE_EXTS:
            return self._image(source, output)

        if src in TABLE_EXTS and dst in TABLE_EXTS:
            return self._table(source, output)

        if src == ".pdf" and dst == ".docx":
            return self._pdf_docx(source, output)

        if self.pandoc and src in PANDOC_EXTS and dst in {".md", ".html", ".docx", ".odt", ".rtf", ".epub", ".txt"}:
            self._run([self.pandoc, str(source), "-o", str(output)])
            return "pandoc"

        if self.libreoffice and src in OFFICE_EXTS and dst in {".pdf", ".docx", ".odt", ".xlsx", ".ods", ".pptx", ".odp", ".html", ".txt"}:
            return self._libreoffice(source, output)

        raise RuntimeError(f"No installed engine supports {src or '(no extension)'} → {dst}")

    def _run(self, cmd: list[str]) -> None:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "conversion failed").strip())

    def _image(self, source: Path, output: Path) -> str:
        from PIL import Image
        with Image.open(source) as im:
            if output.suffix.lower() in {".jpg", ".jpeg"} and im.mode not in {"RGB", "L"}:
                background = Image.new("RGB", im.size, "white")
                alpha = im.getchannel("A") if "A" in im.getbands() else None
                background.paste(im.convert("RGB"), mask=alpha)
                im = background
            im.save(output)
        return "pillow"

    def _table(self, source: Path, output: Path) -> str:
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
        elif src == ".xlsx":
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
        return "pandas"

    def _pdf_docx(self, source: Path, output: Path) -> str:
        try:
            from pdf2docx import Converter
        except Exception as exc:
            raise RuntimeError("PDF → DOCX requires the optional pdf2docx package") from exc
        cv = Converter(str(source))
        try:
            cv.convert(str(output))
        finally:
            cv.close()
        return "pdf2docx"

    def _libreoffice(self, source: Path, output: Path) -> str:
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
        return "libreoffice"

class FluxFileApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {VERSION}")
        self.geometry("1100x720")
        self.minsize(900, 620)
        self.engine = Engine()
        self.jobs: list[Job] = []
        self.output_dir = tk.StringVar(value=str(Path.cwd() / "converted"))
        self.target = tk.StringVar(value="auto")
        self.conflict = tk.StringVar(value="suffix")
        self._build()
        self._refresh_engines()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        top = ttk.Frame(self, padding=12)
        top.grid(row=0, column=0, sticky="ew")
        for col in range(8):
            top.columnconfigure(col, weight=1 if col in {1, 3} else 0)

        ttk.Button(top, text="Add files", command=self.add_files).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(top, text="Add folder", command=self.add_folder).grid(row=0, column=1, sticky="w")
        ttk.Label(top, text="Target").grid(row=0, column=2, padx=(18, 6))
        ttk.Combobox(top, textvariable=self.target, values=TARGETS, state="readonly", width=12).grid(row=0, column=3, sticky="w")
        ttk.Label(top, text="Conflict").grid(row=0, column=4, padx=(18, 6))
        ttk.Combobox(top, textvariable=self.conflict, values=["suffix", "skip", "overwrite"], state="readonly", width=12).grid(row=0, column=5, sticky="w")
        ttk.Button(top, text="Clear queue", command=self.clear).grid(row=0, column=7, sticky="e")

        out = ttk.Frame(self, padding=(12, 0, 12, 8))
        out.grid(row=1, column=0, sticky="ew")
        out.columnconfigure(1, weight=1)
        ttk.Label(out, text="Output folder").grid(row=0, column=0, padx=(0, 8))
        ttk.Entry(out, textvariable=self.output_dir).grid(row=0, column=1, sticky="ew")
        ttk.Button(out, text="Browse", command=self.pick_output).grid(row=0, column=2, padx=(8, 0))

        frame = ttk.Frame(self, padding=(12, 0, 12, 8))
        frame.grid(row=2, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(frame, columns=("source", "target", "status", "output"), show="headings")
        for key, label, width in [
            ("source", "Source", 420), ("target", "Target", 90), ("status", "Status", 120), ("output", "Output / Error", 360)
        ]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)

        bottom = ttk.Frame(self, padding=12)
        bottom.grid(row=3, column=0, sticky="ew")
        bottom.columnconfigure(1, weight=1)
        self.engine_label = ttk.Label(bottom, text="")
        self.engine_label.grid(row=0, column=0, sticky="w")
        ttk.Button(bottom, text="Rescan engines", command=self._refresh_engines).grid(row=0, column=2, padx=8)
        self.run_btn = ttk.Button(bottom, text="Convert queue", command=self.run_queue)
        self.run_btn.grid(row=0, column=3)

    def add_files(self):
        paths = filedialog.askopenfilenames(title="Choose files to convert")
        self._add_paths([Path(p) for p in paths])

    def add_folder(self):
        folder = filedialog.askdirectory(title="Choose a folder")
        if not folder:
            return
        paths = [p for p in Path(folder).iterdir() if p.is_file() and not p.name.startswith(".")]
        self._add_paths(paths)

    def _add_paths(self, paths):
        existing = {j.source for j in self.jobs}
        for p in paths:
            sp = str(p.resolve())
            if sp in existing:
                continue
            target = choose_auto_target(p) if self.target.get() == "auto" else self.target.get()
            self.jobs.append(Job(uuid.uuid4().hex, sp, target))
        self.render()

    def pick_output(self):
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self.output_dir.set(folder)

    def clear(self):
        self.jobs.clear()
        self.render()

    def render(self):
        self.tree.delete(*self.tree.get_children())
        for job in self.jobs:
            tail = job.output or job.error
            self.tree.insert("", "end", iid=job.id, values=(job.source, job.target_format, job.status, tail))

    def _refresh_engines(self):
        self.engine = Engine()
        caps = self.engine.capabilities()
        active = ", ".join(name for name, ok in caps.items() if ok) or "standard library only"
        self.engine_label.configure(text=f"Engines: {active}")

    def run_queue(self):
        if not self.jobs:
            messagebox.showinfo(APP_NAME, "Add files to the queue first.")
            return
        out_dir = Path(self.output_dir.get()).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        self.run_btn.configure(state="disabled")
        threading.Thread(target=self._worker, args=(out_dir,), daemon=True).start()

    def _worker(self, out_dir: Path):
        started = time.time()
        report = []
        for job in self.jobs:
            source = Path(job.source)
            target = normalize_target(job.target_format)
            if self.target.get() != "auto":
                target = normalize_target(self.target.get())
                job.target_format = target
            output = resolve_output(source, out_dir, target, self.conflict.get())
            if output is None:
                job.status = "Skipped"
                job.error = "Output exists"
                report.append(asdict(job))
                self.after(0, self.render)
                continue
            try:
                job.status = "Converting"
                self.after(0, self.render)
                engine = self.engine.convert(source, output)
                job.status = "Done"
                job.output = str(output)
                job.error = ""
                item = asdict(job)
                item["engine"] = engine
                report.append(item)
            except Exception as exc:
                job.status = "Failed"
                job.error = str(exc)
                report.append(asdict(job))
            self.after(0, self.render)

        stamp = time.strftime("%Y%m%d-%H%M%S")
        report_path = out_dir / f"fluxfile-report-{stamp}.json"
        payload = {
            "fluxfile_version": VERSION,
            "started_unix": started,
            "finished_unix": time.time(),
            "platform": sys.platform,
            "engines": self.engine.capabilities(),
            "jobs": report,
        }
        report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.after(0, lambda: self.run_btn.configure(state="normal"))
        self.after(0, lambda: messagebox.showinfo(APP_NAME, f"Conversion pass finished.\nReport: {report_path}"))

if __name__ == "__main__":
    FluxFileApp().mainloop()
