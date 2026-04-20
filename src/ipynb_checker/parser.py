import json
import re

from pathlib import Path

from .models import ParsedTask

START_RE = re.compile(r"<!--\s*TASK:([A-Za-z0-9_-]+)\s+START\s*-->", re.IGNORECASE)
END_RE = re.compile(r"<!--\s*TASK:([A-Za-z0-9_-]+)\s+END\s*-->", re.IGNORECASE)


class NotebookParseError(ValueError):
    pass


def _extract_cell_source(cell: dict) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(source)
    return str(source)


def parse_notebook_tasks(path: Path) -> dict[str, ParsedTask]:
    """Парсит задания, размеченные markdown-маркерами.

    Допустимые маркеры:
    ```
        <!-- TASK:01 START -->
        <!-- TASK:01 END -->
    ```

    Ячейки с кодом между START и END собираются как решение соответствующей задачи.
    Markdown-ячейки внутри задания тоже сохраняются, но на данный момент не используются.
    """

    with path.open("r", encoding="utf-8") as file:
        notebook = json.load(file)

    tasks: dict[str, ParsedTask] = {}
    current: ParsedTask | None = None

    for index, cell in enumerate(notebook.get("cells", [])):
        cell_type = cell.get("cell_type")
        source = _extract_cell_source(cell)

        if cell_type == "markdown":
            start_match = START_RE.search(source)
            end_match = END_RE.search(source)

            if end_match:
                task_id = end_match.group(1)
                if current is None or task_id != current.task_id:
                    raise NotebookParseError(
                        f"Найден END для задачи {task_id} в ячейке {index}, "
                        f"но для нее не было маркера START."
                    )

                current.end_cell_index = index
                tasks[current.task_id] = current
                current = None

            if start_match:
                if current is not None:
                    raise NotebookParseError(
                        f"Найден START для задачи {start_match.group(1)} в ячейке {index}, "
                        f"но для задачи {current.task_id} не было маркера END."
                    )
                task_id = start_match.group(1)
                if task_id in tasks:
                    raise NotebookParseError(f"Дублирующаяся задача {task_id} в ячейке {index}.")
                current = ParsedTask(
                    task_id=task_id,
                    code_cells=[],
                    markdown_cells=[],
                    start_cell_index=index,
                )

        if current is not None:
            if cell_type == "code":
                current.code_cells.append(source)
            elif cell_type == "markdown":
                current.markdown_cells.append(source)

    if current is not None:
        raise NotebookParseError(f"Задача {current.task_id} не закрыта маркером END.")

    return tasks
