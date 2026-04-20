import queue
import threading
import tkinter as tk

from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ipynb_checker.config import load_grading_config
from ipynb_checker.grader import NotebookGrader, export_results
from ipynb_checker.ollama_client import OllamaClient, OllamaError
from ipynb_checker.parser import NotebookParseError


DEFAULT_MODEL = "deepseek-coder:6.7b"
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_OUTPUT = "grades.xlsx"


class GraderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title("IPYNB Grader")
        self.geometry("800x500")

        self.reference_path: Path | None = None
        self.config_path: Path | None = None
        self.student_paths: list[Path] = []

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()

        self._build_ui()
        self._poll_events()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill=tk.BOTH, expand=True)

        ttk.Label(root, text="IPYNB Grader", font=("Arial", 18, "bold")).pack(anchor="w")
        ttk.Label(root, text="Проверка Jupyter Notebook через Ollama").pack(anchor="w")

        form = ttk.Frame(root)
        form.pack(fill=tk.X, pady=8)

        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.base_url_var = tk.StringVar(value=DEFAULT_BASE_URL)
        self.output_var = tk.StringVar(value=DEFAULT_OUTPUT)

        self._add_entry(form, "Ollama model", self.model_var, 0)
        self._add_entry(form, "Ollama base URL", self.base_url_var, 1)
        self._add_entry(form, "Output .xlsx", self.output_var, 2)

        buttons = ttk.Frame(root)
        buttons.pack(fill=tk.X, pady=8)

        ttk.Button(buttons, text="Выбрать эталон", command=self._select_reference).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(buttons, text="Выбрать работы", command=self._select_students).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(buttons, text="Выбрать config", command=self._select_config).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(buttons, text="Куда сохранить", command=self._select_output).pack(
            side=tk.LEFT, padx=4
        )
        self.start_button = ttk.Button(
            buttons, text="Запустить проверку", command=self._start_grading
        )
        self.start_button.pack(side=tk.LEFT, padx=4)

        self.info_var = tk.StringVar(value="Выберите эталон и студенческие работы.")
        ttk.Label(root, textvariable=self.info_var).pack(anchor="w", pady=8)

        self.progress = ttk.Progressbar(root, mode="determinate")
        self.progress.pack(fill=tk.X, pady=8)

        self.log = tk.Text(root, height=14, wrap="word", state="disabled")
        self.log.pack(fill=tk.BOTH, expand=True)

    def _add_entry(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        row: int,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row, column=1, sticky="ew", pady=4
        )
        parent.columnconfigure(1, weight=1)

    def _select_reference(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите эталонный notebook",
            filetypes=[("Jupyter Notebook", "*.ipynb")],
        )
        if path:
            self.reference_path = Path(path)
            self._refresh_info()

    def _select_students(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Выберите студенческие notebook-файлы",
            filetypes=[("Jupyter Notebook", "*.ipynb")],
        )
        if paths:
            self.student_paths = [Path(path) for path in paths]
            self._refresh_info()

    def _select_config(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите конфиг (опционально)",
            filetypes=[("YAML", "*.yaml *.yml")],
        )
        if path:
            self.config_path = Path(path)
            self._refresh_info()

    def _select_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Куда сохранить результат",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if path:
            self.output_var.set(str(Path(path)))

    def _refresh_info(self) -> None:
        reference = self.reference_path.name if self.reference_path else "не выбран"
        students = len(self.student_paths)
        config = self.config_path.name if self.config_path else "по умолчанию"

        self.info_var.set(f"Эталон: {reference} | Работ: {students} | Конфиг: {config}")

    def _start_grading(self) -> None:
        if self.reference_path is None:
            messagebox.showerror("Ошибка", "Выберите эталонный notebook.")
            return

        if not self.student_paths:
            messagebox.showerror("Ошибка", "Выберите хотя бы одну студенческую работу.")
            return

        self.start_button.config(state=tk.DISABLED)
        self.progress["value"] = 0
        self.log.delete("1.0", tk.END)

        thread = threading.Thread(target=self._grade_worker, daemon=True)
        thread.start()

    def _grade_worker(self) -> None:
        try:
            config = load_grading_config(self.config_path)

            client = OllamaClient(
                base_url=self.base_url_var.get().strip() or DEFAULT_BASE_URL,
                model=self.model_var.get().strip() or DEFAULT_MODEL,
            )

            grader = NotebookGrader(config=config, client=client)

            grades = []
            total = len(self.student_paths)

            for index, student_path in enumerate(self.student_paths, start=1):
                self.events.put(("log", f"Проверяю {student_path.name} ({index}/{total})"))

                assert self.reference_path is not None

                grades.append(
                    grader.grade_student(
                        reference_notebook=self.reference_path,
                        student_notebook=student_path,
                    )
                )

                self.events.put(("progress", index / total))

            output_path = Path(self.output_var.get().strip() or DEFAULT_OUTPUT)
            export_results(
                grades=grades,
                config=config,
                path=output_path,
            )

            self.events.put(("done", output_path))

        except (NotebookParseError, OllamaError, Exception) as exc:
            self.events.put(("error", exc))

    def _poll_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()

                if event == "log":
                    assert isinstance(payload, str)
                    self._write_log(payload)

                elif event == "progress":
                    assert isinstance(payload, float)
                    self.progress["value"] = payload * 100

                elif event == "done":
                    assert isinstance(payload, Path)
                    self.start_button.config(state=tk.NORMAL)
                    self._write_log(f"Готово: {payload}")
                    messagebox.showinfo("Готово", f"Результаты сохранены:\n{payload}")

                elif event == "error":
                    assert isinstance(payload, NotebookParseError | OllamaError | Exception)
                    self.start_button.config(state=tk.NORMAL)
                    self._write_log(f"Ошибка: {payload}")
                    messagebox.showerror("Ошибка", str(payload))

        except queue.Empty:
            pass

        self.after(100, self._poll_events)

    def _write_log(self, text: str) -> None:
        self.log.config(state="normal")
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.log.config(state="disabled")


def main() -> None:
    app = GraderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
