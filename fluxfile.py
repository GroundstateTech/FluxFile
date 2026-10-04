#!/usr/bin/env python3
from __future__ import annotations

import queue
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from fluxfile_core import (
    ALL_TARGETS,
    APP_NAME,
    MIN_PYTHON,
    SOURCE_FORMATS,
    VERSION,
    Engine,
    Job,
    choose_auto_target,
    compatible_targets,
    create_job,
    discover_folder_files,
    format_matches,
    normalize_format,
    resolve_output,
    safe_relative_dir,
    should_skip_intake_path,
    source_format,
    which_any,
)
from fluxfile_batch import BatchEvent, BatchRunner, BatchSummary, recommended_workers
from fluxfile_session import load_session, relink_job, relink_missing_jobs, save_session


class FluxFileApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {VERSION}")
        self.geometry("1220x790")
        self.minsize(980, 650)

        self.engine = Engine()
        self.jobs: list[Job] = []
        self.output_dir = tk.StringVar(value=str(Path.cwd() / "converted"))
        self.source_choice = tk.StringVar(value="any")
        self.target_choice = tk.StringVar(value="auto")
        self.conflict = tk.StringVar(value="suffix")
        self.recursive = tk.BooleanVar(value=False)
        self.layout = tk.StringVar(value="flat")
        self.plan_text = tk.StringVar(value="Choose a source and target format.")
        self.status_text = tk.StringVar(value="Ready")
        self.progress_text = tk.StringVar(value="0 / 0")
        self.details_text = tk.StringVar(value="Select a queue item to see its full path and result.")
        self.worker_text = tk.StringVar(value=f"Parallel workers: {recommended_workers()}")

        self._running = False
        self._runner: BatchRunner | None = None
        self._ui_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._batch_thread: threading.Thread | None = None

        self._configure_style()
        self._build()
        self._bind_shortcuts()
        self._refresh_engines()
        self._update_target_choices()
        self.after(75, self._drain_ui_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_style(self):
        style = ttk.Style(self)
        style.configure("Flux.Title.TLabel", font=("TkDefaultFont", 17, "bold"))
        style.configure("Flux.Subtitle.TLabel", font=("TkDefaultFont", 10))
        style.configure("Flux.Primary.TButton", padding=(16, 8))
        style.configure("Flux.Action.TButton", padding=(10, 6))
        style.configure("Treeview", rowheight=26)
        style.configure("Treeview.Heading", font=("TkDefaultFont", 9, "bold"))

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        hero = ttk.Frame(self, padding=(14, 12, 14, 6))
        hero.grid(row=0, column=0, sticky="ew")
        hero.columnconfigure(1, weight=1)
        ttk.Label(hero, text="FluxFile", style="Flux.Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(hero, text=f"  {VERSION}  ·  local conversion workstation", style="Flux.Subtitle.TLabel").grid(row=0, column=1, sticky="w")
        self.rescan_btn = ttk.Button(hero, text="Rescan engines", command=self._refresh_engines, style="Flux.Action.TButton")
        self.rescan_btn.grid(row=0, column=2, padx=(8, 0))
        self.guide_btn = ttk.Button(hero, text="Format guide", command=self.show_format_guide, style="Flux.Action.TButton")
        self.guide_btn.grid(row=0, column=3, padx=(8, 0))

        plan = ttk.LabelFrame(self, text="Conversion plan", padding=(12, 8))
        plan.grid(row=1, column=0, padx=14, pady=(4, 7), sticky="ew")
        plan.columnconfigure(7, weight=1)
        ttk.Label(plan, text="From").grid(row=0, column=0, padx=(0, 5))
        self.source_box = ttk.Combobox(plan, textvariable=self.source_choice, values=SOURCE_FORMATS, state="readonly", width=12)
        self.source_box.grid(row=0, column=1, padx=(0, 14))
        self.source_box.bind("<<ComboboxSelected>>", lambda _e: self._update_target_choices())
        ttk.Label(plan, text="To").grid(row=0, column=2, padx=(0, 5))
        self.target_box = ttk.Combobox(plan, textvariable=self.target_choice, values=ALL_TARGETS, state="readonly", width=12)
        self.target_box.grid(row=0, column=3, padx=(0, 14))
        self.target_box.bind("<<ComboboxSelected>>", lambda _e: self._update_plan_status())
        self.apply_btn = ttk.Button(plan, text="Apply to queue", command=self.apply_plan_to_queue, style="Flux.Action.TButton")
        self.apply_btn.grid(row=0, column=4, padx=(0, 12))
        ttk.Separator(plan, orient="vertical").grid(row=0, column=5, sticky="ns", padx=6)
        ttk.Label(plan, textvariable=self.plan_text).grid(row=0, column=7, sticky="e")

        intake = ttk.Frame(self, padding=(14, 2, 14, 7))
        intake.grid(row=2, column=0, sticky="ew")
        intake.columnconfigure(9, weight=1)
        self.add_files_btn = ttk.Button(intake, text="Add files", command=self.add_files, style="Flux.Action.TButton")
        self.add_files_btn.grid(row=0, column=0, padx=(0, 7))
        self.add_folder_btn = ttk.Button(intake, text="Add folder", command=self.add_folder, style="Flux.Action.TButton")
        self.add_folder_btn.grid(row=0, column=1, padx=(0, 10))
        self.recursive_btn = ttk.Checkbutton(intake, text="Include subfolders", variable=self.recursive)
        self.recursive_btn.grid(row=0, column=2, padx=(0, 18))
        ttk.Label(intake, text="Existing output").grid(row=0, column=3, padx=(0, 5))
        self.conflict_box = ttk.Combobox(intake, textvariable=self.conflict, values=["suffix", "skip", "overwrite"], state="readonly", width=10)
        self.conflict_box.grid(row=0, column=4, padx=(0, 14))
        self.remove_btn = ttk.Button(intake, text="Remove", command=self.remove_selected, style="Flux.Action.TButton")
        self.remove_btn.grid(row=0, column=5, padx=(0, 7))
        self.retry_btn = ttk.Button(intake, text="Retry", command=self.retry_selected, style="Flux.Action.TButton")
        self.retry_btn.grid(row=0, column=6, padx=(0, 7))
        self.relink_btn = ttk.Button(intake, text="Relink missing", command=self.relink_missing_folder, style="Flux.Action.TButton")
        self.relink_btn.grid(row=0, column=7, padx=(0, 7))
        self.clear_btn = ttk.Button(intake, text="Clear", command=self.clear, style="Flux.Action.TButton")
        self.clear_btn.grid(row=0, column=8)
        ttk.Label(intake, textvariable=self.worker_text).grid(row=0, column=9, sticky="e")

        output = ttk.Frame(self, padding=(14, 0, 14, 8))
        output.grid(row=3, column=0, sticky="ew")
        output.columnconfigure(1, weight=1)
        ttk.Label(output, text="Output").grid(row=0, column=0, padx=(0, 8))
        self.output_entry = ttk.Entry(output, textvariable=self.output_dir)
        self.output_entry.grid(row=0, column=1, sticky="ew")
        self.output_browse_btn = ttk.Button(output, text="Browse", command=self.pick_output, style="Flux.Action.TButton")
        self.output_browse_btn.grid(row=0, column=2, padx=(8, 12))
        ttk.Label(output, text="Folder layout").grid(row=0, column=3, padx=(0, 5))
        self.layout_box = ttk.Combobox(output, textvariable=self.layout, values=["flat", "preserve"], state="readonly", width=10)
        self.layout_box.grid(row=0, column=4, padx=(0, 12))
        self.save_session_btn = ttk.Button(output, text="Save queue", command=self.save_queue_session, style="Flux.Action.TButton")
        self.save_session_btn.grid(row=0, column=5, padx=(0, 7))
        self.load_session_btn = ttk.Button(output, text="Load queue", command=self.load_queue_session, style="Flux.Action.TButton")
        self.load_session_btn.grid(row=0, column=6)

        queue_box = ttk.LabelFrame(self, text="Queue", padding=(8, 8))
        queue_box.grid(row=4, column=0, padx=14, pady=(0, 7), sticky="nsew")
        queue_box.rowconfigure(0, weight=1)
        queue_box.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            queue_box,
            columns=("source", "route", "engine", "status", "result"),
            show="headings",
            selectmode="extended",
        )
        columns = [
            ("source", "Source", 280),
            ("route", "Route", 125),
            ("engine", "Engine", 110),
            ("status", "Status", 110),
            ("result", "Output / Error", 430),
        ]
        for key, label, width in columns:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=70, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._selection_changed)
        self.tree.bind("<Double-1>", lambda _e: self.open_selected_output())
        self.tree.bind("<Button-3>", self._show_context_menu)

        yscroll = ttk.Scrollbar(queue_box, command=self.tree.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll = ttk.Scrollbar(queue_box, orient="horizontal", command=self.tree.xview)
        xscroll.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        detail = ttk.Label(self, textvariable=self.details_text, anchor="w")
        detail.grid(row=5, column=0, padx=16, pady=(0, 6), sticky="ew")

        progress = ttk.Frame(self, padding=(14, 3, 14, 3))
        progress.grid(row=6, column=0, sticky="ew")
        progress.columnconfigure(1, weight=1)
        ttk.Label(progress, textvariable=self.status_text).grid(row=0, column=0, padx=(0, 10), sticky="w")
        self.progressbar = ttk.Progressbar(progress, mode="determinate", maximum=100, value=0)
        self.progressbar.grid(row=0, column=1, sticky="ew")
        ttk.Label(progress, textvariable=self.progress_text, width=12, anchor="e").grid(row=0, column=2, padx=(10, 0))

        actions = ttk.Frame(self, padding=(14, 5, 14, 12))
        actions.grid(row=7, column=0, sticky="ew")
        actions.columnconfigure(1, weight=1)
        self.engine_label = ttk.Label(actions, text="")
        self.engine_label.grid(row=0, column=0, sticky="w")
        self.open_btn = ttk.Button(actions, text="Open output folder", command=self.open_output_folder, style="Flux.Action.TButton")
        self.open_btn.grid(row=0, column=2, padx=(8, 0))
        self.cancel_btn = ttk.Button(actions, text="Cancel", command=self.cancel_queue, state="disabled", style="Flux.Action.TButton")
        self.cancel_btn.grid(row=0, column=3, padx=(8, 0))
        self.run_btn = ttk.Button(actions, text="Convert queue", command=self.run_queue, style="Flux.Primary.TButton")
        self.run_btn.grid(row=0, column=4, padx=(8, 0))

        self.context_menu = tk.Menu(self, tearoff=False)
        self.context_menu.add_command(label="Retry selected", command=self.retry_selected)
        self.context_menu.add_command(label="Relink selected source…", command=self.relink_selected_source)
        self.context_menu.add_command(label="Remove selected", command=self.remove_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Open selected output", command=self.open_selected_output)

        self._mutable_widgets = [
            self.source_box, self.target_box, self.apply_btn, self.add_files_btn, self.add_folder_btn,
            self.recursive_btn, self.conflict_box, self.remove_btn, self.retry_btn, self.relink_btn, self.clear_btn,
            self.output_entry, self.output_browse_btn, self.layout_box, self.save_session_btn,
            self.load_session_btn, self.rescan_btn,
        ]

    def _bind_shortcuts(self):
        self.bind("<Control-o>", lambda _e: self.add_files())
        self.bind("<Control-O>", lambda _e: self.add_files())
        self.bind("<Control-Shift-O>", lambda _e: self.add_folder())
        self.bind("<Control-Return>", lambda _e: self.run_queue())
        self.bind("<Delete>", lambda _e: self.remove_selected())
        self.bind("<F5>", lambda _e: self._refresh_engines())
        self.bind("<Escape>", lambda _e: self.cancel_queue())
        self.bind("<Control-a>", self._select_all)
        self.bind("<Control-Shift-S>", lambda _e: self.save_queue_session())
        self.bind("<Control-Shift-L>", lambda _e: self.load_queue_session())
        self.bind("<Control-Shift-R>", lambda _e: self.relink_missing_folder())

    def _select_all(self, _event=None):
        self.tree.selection_set(self.tree.get_children())
        return "break"

    def _show_context_menu(self, event):
        if self._running:
            return
        row = self.tree.identify_row(event.y)
        if row and row not in self.tree.selection():
            self.tree.selection_set(row)
        if row:
            self.context_menu.tk_popup(event.x_root, event.y_root)

    def _set_running(self, running: bool):
        self._running = running
        for widget in self._mutable_widgets:
            if isinstance(widget, ttk.Combobox):
                widget.configure(state="disabled" if running else "readonly")
            else:
                widget.configure(state="disabled" if running else "normal")
        self.run_btn.configure(state="disabled" if running else "normal")
        self.cancel_btn.configure(state="normal" if running else "disabled")
        if not running:
            self.status_text.set(self._queue_summary())

    def _queue_summary(self) -> str:
        if not self.jobs:
            return "Ready"
        counts: dict[str, int] = {}
        for job in self.jobs:
            counts[job.status] = counts.get(job.status, 0) + 1
        done = counts.get("Done", 0)
        failed = counts.get("Failed", 0) + counts.get("Unsupported", 0)
        missing = counts.get("Missing", 0)
        extra = f" · {missing} missing" if missing else ""
        return f"{len(self.jobs)} items · {done} done · {failed} failed/unsupported{extra}"

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
            self.plan_text.set("Mixed input · per-file target" if target == "auto" else f"Mixed input → .{target}")
            return
        if target == "auto":
            self.plan_text.set(f".{src} → recommended output")
            return
        engine = self.engine.engine_for(src, target)
        self.plan_text.set(f".{src} → .{target} · {engine or 'engine unavailable'}")

    def add_files(self):
        if self._running:
            return
        fmt = normalize_format(self.source_choice.get())
        variants = {
            "jpg": "*.jpg *.jpeg", "jpeg": "*.jpg *.jpeg", "tiff": "*.tif *.tiff",
            "html": "*.html *.htm", "md": "*.md *.markdown", "tgz": "*.tgz *.tar.gz",
            "tbz2": "*.tbz2 *.tar.bz2", "txz": "*.txz *.tar.xz",
        }
        filetypes = [("Supported / all files", "*.*")] if fmt == "any" else [
            (f"{fmt.upper()} files", variants.get(fmt, f"*.{fmt}")), ("All files", "*.*")
        ]
        paths = filedialog.askopenfilenames(title="Choose files to convert", filetypes=filetypes)
        self._add_paths([Path(p) for p in paths])

    def add_folder(self):
        if self._running:
            return
        folder = filedialog.askdirectory(title="Choose a folder")
        if not folder:
            return
        root = Path(folder)
        output_dir = Path(self.output_dir.get()).expanduser()
        try:
            paths = discover_folder_files(root, self.recursive.get(), output_dir)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not scan folder:\n{exc}")
            return
        self._add_paths(paths, root)

    def _add_paths(self, paths: list[Path], root: Path | None = None):
        existing = {job.source for job in self.jobs}
        selected_source = normalize_format(self.source_choice.get())
        selected_target = normalize_format(self.target_choice.get())
        added = 0
        skipped = 0
        for path in paths:
            fmt = source_format(path)
            if not format_matches(selected_source, fmt):
                skipped += 1
                continue
            resolved = str(path.expanduser().resolve())
            if resolved in existing:
                continue
            relative_dir = ""
            if root is not None:
                try:
                    relative_dir = path.absolute().parent.relative_to(root.expanduser().absolute()).as_posix()
                    if relative_dir == ".":
                        relative_dir = ""
                except (ValueError, OSError):
                    relative_dir = ""
            try:
                job = create_job(path, selected_target, self.engine, relative_dir=relative_dir)
            except OSError:
                continue
            self.jobs.append(job)
            existing.add(resolved)
            self._insert_job_row(job)
            added += 1
        self._refresh_progress()
        self.status_text.set(f"Added {added} item(s)" + (f" · skipped {skipped} wrong format" if skipped else ""))

    def apply_plan_to_queue(self):
        if self._running:
            return
        selected_source = normalize_format(self.source_choice.get())
        selected_target = normalize_format(self.target_choice.get())
        changed = 0
        unsupported = 0
        for job in self.jobs:
            if not format_matches(selected_source, job.source_format):
                continue
            source = Path(job.source)
            if not source.is_file():
                job.status = "Missing"
                job.engine = "unavailable"
                job.output = ""
                job.error = "Source file is missing"
                self._update_job_row(job)
                continue
            job.source_format = source_format(source)
            target = choose_auto_target(source) if selected_target == "auto" else selected_target
            job.target_format = target
            job.engine = self.engine.engine_for(job.source_format, target) or "unavailable"
            job.status = "Queued" if job.engine != "unavailable" else "Unsupported"
            job.output = ""
            job.error = "" if job.status == "Queued" else f"No installed engine supports .{job.source_format} → .{target}"
            job.duration_seconds = 0.0
            job.output_bytes = 0
            self._update_job_row(job)
            changed += 1
            unsupported += int(job.engine == "unavailable")
        self.plan_text.set(f"Applied to {changed} item(s) · {unsupported} unavailable")
        self._refresh_progress()

    def _session_settings(self) -> dict[str, object]:
        return {
            "output_dir": self.output_dir.get(),
            "source_choice": self.source_choice.get(),
            "target_choice": self.target_choice.get(),
            "conflict": self.conflict.get(),
            "recursive": self.recursive.get(),
            "layout": self.layout.get(),
        }

    def save_queue_session(self):
        if self._running:
            return
        path = filedialog.asksaveasfilename(
            title="Save FluxFile queue",
            defaultextension=".fluxqueue.json",
            filetypes=[("FluxFile queue", "*.fluxqueue.json"), ("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            save_session(Path(path), self.jobs, self._session_settings())
            self.status_text.set(f"Queue saved · {Path(path).name}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not save queue session:\n{exc}")

    def load_queue_session(self):
        if self._running:
            return
        path = filedialog.askopenfilename(
            title="Load FluxFile queue",
            filetypes=[("FluxFile queue", "*.fluxqueue.json"), ("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            jobs, settings = load_session(Path(path))
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not load queue session:\n{exc}")
            return

        self.jobs = jobs
        self.tree.delete(*self.tree.get_children())
        self.output_dir.set(settings.get("output_dir") or str(Path.cwd() / "converted"))
        self.source_choice.set(settings.get("source_choice") if settings.get("source_choice") in SOURCE_FORMATS else "any")
        self.target_choice.set(settings.get("target_choice") if settings.get("target_choice") in ALL_TARGETS else "auto")
        self.conflict.set(settings.get("conflict") if settings.get("conflict") in {"suffix", "skip", "overwrite"} else "suffix")
        self.recursive.set(bool(settings.get("recursive", False)))
        self.layout.set(settings.get("layout") if settings.get("layout") in {"flat", "preserve"} else "flat")

        missing = 0
        for job in self.jobs:
            source = Path(job.source)
            if not source.is_file():
                job.status = "Missing"
                job.engine = "unavailable"
                job.error = "Source file is missing"
                missing += 1
            else:
                job.source_format = source_format(source)
                job.engine = self.engine.engine_for(job.source_format, job.target_format) or "unavailable"
                if job.status == "Queued" and job.engine == "unavailable":
                    job.status = "Unsupported"
                    job.error = f"No installed engine supports .{job.source_format} → .{job.target_format}"
            self._insert_job_row(job)
        self._update_target_choices()
        self._refresh_progress()
        version = settings.get("session_version", 1)
        self.status_text.set(
            f"Loaded queue v{version} · {len(self.jobs)} item(s)"
            + (f" · {missing} missing — use Relink missing" if missing else "")
        )

    def pick_output(self):
        if self._running:
            return
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self.output_dir.set(folder)

    def clear(self):
        if self._running:
            return
        self.jobs.clear()
        self.tree.delete(*self.tree.get_children())
        self._refresh_progress()
        self.details_text.set("Select a queue item to see its full path and result.")

    def remove_selected(self):
        if self._running:
            return
        selected = set(self.tree.selection())
        if not selected:
            return
        self.jobs = [job for job in self.jobs if job.id not in selected]
        for item in selected:
            if self.tree.exists(item):
                self.tree.delete(item)
        self._refresh_progress()

    def retry_selected(self):
        if self._running:
            return
        selected = set(self.tree.selection())
        for job in self.jobs:
            if job.id not in selected:
                continue
            source = Path(job.source)
            if not source.is_file():
                job.status = "Missing"
                job.output = ""
                job.error = "Source file is missing"
                job.engine = "unavailable"
                self._update_job_row(job)
                continue
            job.source_format = source_format(source)
            job.status = "Queued"
            job.output = ""
            job.error = ""
            job.duration_seconds = 0.0
            job.output_bytes = 0
            job.engine = self.engine.engine_for(job.source_format, job.target_format) or "unavailable"
            if job.engine == "unavailable":
                job.status = "Unsupported"
                job.error = f"No installed engine supports .{job.source_format} → .{job.target_format}"
            self._update_job_row(job)
        self._refresh_progress()

    def relink_selected_source(self):
        if self._running:
            return
        selected = self.tree.selection()
        if len(selected) != 1:
            messagebox.showinfo(APP_NAME, "Select exactly one queue item to relink.")
            return
        by_id = {job.id: job for job in self.jobs}
        job = by_id.get(selected[0])
        if not job:
            return
        path = filedialog.askopenfilename(title="Choose replacement source file")
        if not path:
            return
        try:
            relink_job(job, Path(path), self.engine)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not relink source:\n{exc}")
            return
        self._update_job_row(job)
        self._refresh_progress()
        self.status_text.set(f"Relinked {Path(job.source).name}")

    def relink_missing_folder(self):
        if self._running:
            return
        missing = [job for job in self.jobs if job.status == "Missing" or not Path(job.source).is_file()]
        if not missing:
            messagebox.showinfo(APP_NAME, "There are no missing source files to relink.")
            return
        folder = filedialog.askdirectory(
            title="Choose the new source root",
            mustexist=True,
        )
        if not folder:
            return
        try:
            relinked, unresolved = relink_missing_jobs(self.jobs, Path(folder), self.engine)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not relink missing sources:\n{exc}")
            return
        for job in self.jobs:
            self._update_job_row(job)
        self._refresh_progress()
        self.status_text.set(f"Relinked {relinked} source(s) · {unresolved} still missing")

    def _insert_job_row(self, job: Job):
        if self.tree.exists(job.id):
            self._update_job_row(job)
            return
        self.tree.insert("", "end", iid=job.id, values=self._row_values(job))

    def _update_job_row(self, job: Job):
        if self.tree.exists(job.id):
            self.tree.item(job.id, values=self._row_values(job))
        else:
            self._insert_job_row(job)
        if job.id in self.tree.selection():
            self._selection_changed()

    def _row_values(self, job: Job):
        source = Path(job.source).name
        if job.relative_dir:
            source = f"{job.relative_dir}/{source}"
        route = f"{job.source_format} → {job.target_format}"
        result = job.output or job.error
        return source, route, job.engine, job.status, result

    def _selection_changed(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            self.details_text.set("Select a queue item to see its full path and result.")
            return
        by_id = {job.id: job for job in self.jobs}
        job = by_id.get(selected[0])
        if not job:
            return
        details = job.source
        if job.output:
            details += f"  →  {job.output}"
        elif job.error:
            details += f"  ·  {job.error}"
        if job.duration_seconds:
            details += f"  ·  {job.duration_seconds:.2f}s"
        self.details_text.set(details)

    def _refresh_engines(self):
        if self._running:
            return
        self.engine = Engine()
        caps = self.engine.capabilities()
        active = [name for name, ok in caps.items() if ok]
        self.engine_label.configure(text=f"Engines: {', '.join(active) if active else 'built-in only'}")
        for job in self.jobs:
            job.engine = self.engine.engine_for(job.source_format, job.target_format) or "unavailable"
            self._update_job_row(job)
        self._update_plan_status()

    def _refresh_progress(self, completed: int | None = None, total: int | None = None):
        total = len(self.jobs) if total is None else total
        terminal = {"Done", "Failed", "Unsupported", "Skipped", "Cancelled", "Missing"}
        completed = sum(job.status in terminal for job in self.jobs) if completed is None else completed
        percent = (completed / total * 100) if total else 0
        self.progressbar.configure(value=percent)
        self.progress_text.set(f"{completed} / {total}")
        if not self._running:
            self.status_text.set(self._queue_summary())

    def open_output_folder(self):
        folder = Path(self.output_dir.get()).expanduser()
        try:
            folder.mkdir(parents=True, exist_ok=True)
            self._open_path(folder)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not open output folder:\n{exc}")

    def open_selected_output(self):
        selected = self.tree.selection()
        if not selected:
            return
        by_id = {job.id: job for job in self.jobs}
        job = by_id.get(selected[0])
        if not job or not job.output:
            return
        path = Path(job.output)
        try:
            self._open_path(path.parent if path.exists() else Path(self.output_dir.get()).expanduser())
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not open result folder:\n{exc}")

    def _open_path(self, path: Path):
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            opener = which_any("xdg-open", "gio")
            if not opener:
                raise RuntimeError("No desktop folder opener found (xdg-open/gio).")
            subprocess.Popen([opener, "open", str(path)] if Path(opener).name == "gio" else [opener, str(path)])

    def run_queue(self):
        if self._running:
            return
        if not self.jobs:
            messagebox.showinfo(APP_NAME, "Add files to the queue first.")
            return
        out_dir = Path(self.output_dir.get()).expanduser()
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not create output folder:\n{exc}")
            return

        batch_jobs = [job for job in self.jobs if job.status == "Queued"]
        if not batch_jobs:
            messagebox.showinfo(APP_NAME, "No queued items. Use Retry on finished/failed items to run them again.")
            return

        self._runner = BatchRunner(self.engine)
        self.worker_text.set(f"Parallel workers: {self._runner.workers}")
        self._set_running(True)
        self.status_text.set("Starting conversion pass…")
        self._refresh_progress()
        conflict = self.conflict.get()
        layout = self.layout.get()
        self._batch_thread = threading.Thread(
            target=self._run_batch_thread,
            args=(batch_jobs, out_dir, conflict, layout),
            daemon=True,
            name="fluxfile-batch",
        )
        self._batch_thread.start()

    def _run_batch_thread(self, jobs: list[Job], out_dir: Path, conflict: str, layout: str):
        assert self._runner is not None
        try:
            summary = self._runner.run(
                jobs, out_dir, conflict,
                callback=lambda event: self._ui_queue.put(("batch", event)),
                layout=layout,
            )
            self._ui_queue.put(("summary", summary))
        except Exception as exc:
            self._ui_queue.put(("fatal", str(exc)))
        finally:
            self._ui_queue.put(("running", False))

    def cancel_queue(self):
        if not self._running or not self._runner:
            return
        self.status_text.set("Cancelling… running external conversions are being stopped.")
        self.cancel_btn.configure(state="disabled")
        self._runner.cancel()

    def _handle_batch_event(self, event: BatchEvent):
        if event.job is not None:
            self._update_job_row(event.job)
        if event.kind == "start":
            self.status_text.set(event.message or "Converting…")
        elif event.kind == "job" and event.job is not None and event.job.status == "Converting":
            self.status_text.set(f"Converting {Path(event.job.source).name}")
        elif event.kind == "progress":
            self._refresh_progress(event.completed, event.total)
        elif event.kind == "complete":
            self._refresh_progress(event.completed, event.total)

    def _show_summary(self, summary: BatchSummary):
        counts = summary.counts
        lines = [
            "Conversion pass finished.",
            "",
            f"Done: {counts.get('Done', 0)}",
            f"Failed: {counts.get('Failed', 0)}",
            f"Unsupported: {counts.get('Unsupported', 0)}",
            f"Skipped: {counts.get('Skipped', 0)}",
            f"Cancelled: {counts.get('Cancelled', 0)}",
            f"Time: {summary.duration_seconds:.2f}s with {summary.workers} worker(s)",
            "",
            f"JSON report: {Path(summary.json_report).name}",
            f"CSV report: {Path(summary.csv_report).name}",
        ]
        messagebox.showinfo(APP_NAME, "\n".join(lines))

    def _drain_ui_queue(self):
        try:
            while True:
                action, payload = self._ui_queue.get_nowait()
                if action == "batch":
                    self._handle_batch_event(payload)
                elif action == "summary":
                    self._show_summary(payload)
                elif action == "fatal":
                    messagebox.showerror(APP_NAME, f"Conversion pass stopped unexpectedly:\n{payload}")
                elif action == "running":
                    self._set_running(bool(payload))
                    self._refresh_progress()
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(75, self._drain_ui_queue)

    def show_format_guide(self):
        guide = tk.Toplevel(self)
        guide.title("FluxFile format guide")
        guide.geometry("720x560")
        guide.minsize(560, 420)
        guide.columnconfigure(0, weight=1)
        guide.rowconfigure(1, weight=1)
        ttk.Label(guide, text="Local conversion engines", style="Flux.Title.TLabel", padding=(14, 12, 14, 6)).grid(row=0, column=0, sticky="w")
        text = tk.Text(guide, wrap="word", padx=14, pady=12)
        text.grid(row=1, column=0, sticky="nsew")
        body = (
            "Documents / ebooks\n  Pandoc or LibreOffice\n\n"
            "Tables / JSONL\n  pandas + spreadsheet readers/writers\n\n"
            "Images / icons\n  Pillow; codec support depends on the installed Pillow build\n\n"
            "PDF text, HTML and page images\n  PyMuPDF\n\n"
            "Audio / video / audio extraction\n  FFmpeg\n\n"
            "SVG → PNG / PDF\n  CairoSVG + Cairo\n\n"
            "SRT / VTT and ZIP / TAR / TGZ / TBZ2 / TXZ\n  Built in\n\n"
            "Integrity rules\n"
            "• Multi-page PDFs require TIFF to preserve every page when rendering images.\n"
            "• Animated images require a multi-frame output target.\n"
            "• Multi-sheet workbooks cannot be flattened to CSV/TSV/JSON without explicit data loss, so FluxFile refuses that route.\n"
            "• Media conversion uses the first video/audio stream.\n"
            "• Archive repacking rejects links, unsafe paths, duplicates, and oversized expanded content.\n"
            "• Existing output files are published atomically after a successful conversion.\n"
            "• Folder layout can stay flat or preserve recursive source subfolders.\n"
            "• Queue session v2 stores safe relative path references when files live beside/below the session file.\n"
            "• Older v1 queue sessions still load. Missing sources can be repaired with Relink missing or Relink selected source.\n"
            "• Session files store paths and queue metadata only; source file contents are never embedded.\n"
        )
        text.insert("1.0", body)
        text.configure(state="disabled")
        ttk.Button(guide, text="Close", command=guide.destroy, style="Flux.Action.TButton").grid(row=2, column=0, pady=10)

    def _on_close(self):
        if self._running:
            close = messagebox.askyesno(APP_NAME, "A conversion pass is running. Cancel it and close FluxFile?")
            if not close:
                return
            if self._runner:
                self._runner.cancel()
        self.destroy()


if __name__ == "__main__":
    if sys.version_info < MIN_PYTHON:
        raise SystemExit(
            f"FluxFile requires Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+; found {sys.version.split()[0]}"
        )
    FluxFileApp().mainloop()
