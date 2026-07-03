#!/usr/bin/env python3
"""Simple desktop UI for exporting SWORD chapters to CSV."""

from __future__ import annotations

import io
import sys
import threading
import tkinter as tk
from contextlib import redirect_stderr
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from sword_chapter_to_csv import (
    DEFAULT_TEXT,
    discover_text_sources,
    export_chapter,
    export_synoptic_chapter,
    load_bible,
    resolve_text_source,
)

APP_DIR = Path(__file__).resolve().parent


class ExportApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("SWORD Chapter to CSV")
        self.minsize(420, 340)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        self.sources = discover_text_sources()
        self.books: list[str] = []
        self._busy = False
        self.text_vars: dict[str, tk.BooleanVar] = {}

        self.book_var = tk.StringVar()
        self.chapter_var = tk.StringVar(value="1")
        self.output_var = tk.StringVar()
        self.status_var = tk.StringVar(
            value="Choose one or more texts, book, and chapter, then export."
        )

        self._build_form()
        self._load_books()

        for var in (self.book_var, self.chapter_var):
            var.trace_add("write", lambda *_: self._update_default_output())

    def _build_form(self) -> None:
        form = ttk.Frame(self, padding=12)
        form.grid(row=0, column=0, sticky="nsew")
        form.columnconfigure(1, weight=1)

        texts_frame = ttk.LabelFrame(form, text="Texts", padding=(8, 6))
        texts_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        texts_frame.columnconfigure(0, weight=1)

        if self.sources:
            names = sorted(self.sources)
            for index, name in enumerate(names):
                var = tk.BooleanVar(value=name == DEFAULT_TEXT)
                self.text_vars[name] = var
                ttk.Checkbutton(
                    texts_frame,
                    text=name,
                    variable=var,
                    command=self._on_text_selection_changed,
                ).grid(row=index // 4, column=index % 4, sticky="w", padx=(0, 16), pady=2)
        else:
            ttk.Label(texts_frame, text="No texts found under SWORD/").grid(
                row=0, column=0, sticky="w"
            )

        ttk.Label(form, text="Book").grid(row=1, column=0, sticky="w", pady=4)
        self.book_combo = ttk.Combobox(form, textvariable=self.book_var, width=12)
        self.book_combo.grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(form, text="Chapter").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(form, textvariable=self.chapter_var, width=8).grid(
            row=2, column=1, sticky="w", pady=4
        )

        ttk.Label(form, text="Output CSV").grid(row=3, column=0, sticky="w", pady=4)
        output_row = ttk.Frame(form)
        output_row.grid(row=3, column=1, sticky="ew", pady=4)
        output_row.columnconfigure(0, weight=1)
        ttk.Entry(output_row, textvariable=self.output_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(output_row, text="Browse…", command=self._browse_output).grid(
            row=0, column=1, padx=(8, 0)
        )

        actions = ttk.Frame(self, padding=(12, 0, 12, 8))
        actions.grid(row=1, column=0, sticky="ew")
        self.export_button = ttk.Button(actions, text="Export CSV", command=self._start_export)
        self.export_button.pack(side="left")

        ttk.Label(self, textvariable=self.status_var, padding=(12, 0)).grid(
            row=2, column=0, sticky="w"
        )

        log_frame = ttk.LabelFrame(self, text="Log", padding=(12, 8))
        log_frame.grid(row=4, column=0, sticky="nsew", padx=12, pady=(8, 12))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log = tk.Text(log_frame, height=8, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

        if not self.sources:
            self._append_log(f"No SWORD text sources found under {APP_DIR / 'SWORD'}")
            self.export_button.configure(state="disabled")

    def _selected_texts(self) -> list[str]:
        return sorted(name for name, var in self.text_vars.items() if var.get())

    def _on_text_selection_changed(self) -> None:
        selected = self._selected_texts()
        if selected:
            self._load_books_from_source(selected[0])
        self._update_default_output()

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _load_books(self) -> None:
        selected = self._selected_texts()
        if not selected:
            return
        self._load_books_from_source(selected[0])

    def _load_books_from_source(self, text_name: str) -> None:
        try:
            sword_dir, module_name = resolve_text_source(text_name, self.sources)
            bible = load_bible(sword_dir, module_name)
            structure = bible.get_structure()
            self.books = [
                book.osis_name
                for book in structure.get_books()["ot"] + structure.get_books()["nt"]
            ]
        except (FileNotFoundError, KeyError) as exc:
            self.books = []
            self._append_log(f"Error loading books: {exc}")

        self.book_combo.configure(values=self.books)
        if self.books:
            if self.book_var.get() not in self.books:
                self.book_var.set("Exod" if "Exod" in self.books else self.books[0])
        else:
            self.book_var.set("")

        self._update_default_output()

    def _default_output_name(self, book: str, chapter: str) -> str:
        selected = self._selected_texts()
        if len(selected) >= 2:
            if selected == ["LXX", "WLC"]:
                return f"Synoptic_{book}_{chapter}.csv"
            return f"{'_'.join(selected)}_{book}_{chapter}.csv"
        if len(selected) == 1:
            return f"{selected[0]}_{book}_{chapter}.csv"
        return f"{book}_{chapter}.csv"

    def _update_default_output(self) -> None:
        book = self.book_var.get().strip()
        chapter = self.chapter_var.get().strip()
        if not book or not chapter.isdigit():
            return
        self.output_var.set(self._default_output_name(book, chapter))

    def _browse_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save CSV as",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir=str(APP_DIR),
            initialfile=self.output_var.get() or "chapter.csv",
        )
        if path:
            self.output_var.set(path)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.export_button.configure(state="disabled" if busy else "normal")

    def _start_export(self) -> None:
        if self._busy:
            return

        selected_texts = self._selected_texts()
        book = self.book_var.get().strip()
        chapter_text = self.chapter_var.get().strip()
        output_text = self.output_var.get().strip()

        if not selected_texts:
            messagebox.showwarning("Missing input", "Choose at least one text.")
            return
        if not book:
            messagebox.showwarning("Missing input", "Choose a book.")
            return
        if not chapter_text.isdigit() or int(chapter_text) < 1:
            messagebox.showwarning("Missing input", "Enter a valid chapter number.")
            return

        chapter = int(chapter_text)
        output_path = Path(output_text) if output_text else None

        self._set_busy(True)
        self.status_var.set("Exporting…")
        if len(selected_texts) == 1:
            target = self._run_single_export
            args = (selected_texts[0], book, chapter, output_path)
        else:
            target = self._run_synoptic_export
            args = (selected_texts, book, chapter, output_path)
        threading.Thread(target=target, args=args, daemon=True).start()

    def _run_synoptic_export(
        self,
        text_names: list[str],
        book: str,
        chapter: int,
        output_path: Path | None,
    ) -> None:
        stderr_buffer = io.StringIO()
        try:
            with redirect_stderr(stderr_buffer):
                written_path, word_counts, osis_book = export_synoptic_chapter(
                    book,
                    chapter,
                    text_names,
                    output_path,
                )
        except (FileNotFoundError, KeyError, ValueError) as exc:
            self.after(0, lambda: self._export_failed(str(exc), stderr_buffer.getvalue()))
            return

        warnings = stderr_buffer.getvalue().strip()
        counts_msg = " + ".join(f"{count} {name}" for name, count in word_counts.items())
        message = f"Wrote {written_path.name} ({counts_msg} words, {osis_book} {chapter})"
        self.after(
            0,
            lambda: self._export_succeeded(message, warnings, written_path),
        )

    def _run_single_export(
        self,
        text_name: str,
        book: str,
        chapter: int,
        output_path: Path | None,
    ) -> None:
        stderr_buffer = io.StringIO()
        try:
            with redirect_stderr(stderr_buffer):
                written_path, word_count, osis_book = export_chapter(
                    text_name,
                    book,
                    chapter,
                    output_path,
                )
        except (FileNotFoundError, KeyError, ValueError) as exc:
            self.after(0, lambda: self._export_failed(str(exc), stderr_buffer.getvalue()))
            return

        warnings = stderr_buffer.getvalue().strip()
        message = (
            f"Wrote {written_path.name} ({word_count} words from "
            f"{text_name.upper()} {osis_book} {chapter})"
        )
        self.after(
            0,
            lambda: self._export_succeeded(message, warnings, written_path),
        )

    def _export_failed(self, error: str, warnings: str) -> None:
        self._set_busy(False)
        self.status_var.set("Export failed.")
        if warnings:
            self._append_log(warnings)
        self._append_log(f"Error: {error}")
        messagebox.showerror("Export failed", error)

    def _export_succeeded(
        self,
        message: str,
        warnings: str,
        written_path: Path,
    ) -> None:
        self._set_busy(False)
        self.status_var.set(message)
        if warnings:
            self._append_log(warnings)
        self._append_log(message)
        messagebox.showinfo("Export complete", f"{message}\n\nSaved to:\n{written_path}")


def main() -> int:
    if not discover_text_sources():
        print(
            f"Error: no text sources found under {APP_DIR / 'SWORD'}",
            file=sys.stderr,
        )
        return 1

    app = ExportApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
