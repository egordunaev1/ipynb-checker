import pandas as pd

from typing import cast
from pathlib import Path
from xlsxwriter.workbook import Workbook
from xlsxwriter.worksheet import Worksheet

from .models import GradingConfig, StudentGrade, TaskGrade
from .ollama_client import OllamaClient
from .parser import parse_notebook_tasks
from .prompt import build_grading_prompt


class NotebookGrader:
    def __init__(self, config: GradingConfig, client: OllamaClient) -> None:
        self.config = config
        self.client = client

    def grade_student(
        self,
        reference_notebook: Path,
        student_notebook: Path,
        student_name: str | None = None,
    ) -> StudentGrade:
        reference_tasks = parse_notebook_tasks(reference_notebook)
        student_tasks = parse_notebook_tasks(student_notebook)

        task_grades: list[TaskGrade] = []

        for task_id, reference_task in reference_tasks.items():
            max_score = self.config.get_points_for(task_id)

            student_task = student_tasks.get(task_id)

            # Если маркеры отсутствуют, предполагаем, что они были случайно или специально удалены.
            # В этом случае требуется провести ручную проверку.
            if student_task is None:
                task_grades.append(
                    TaskGrade(
                        task_id=task_id,
                        max_score=max_score,
                        score_multiplier=0.0,
                        requires_manual_check=True,
                        comment="Задание не размечено.",
                        detected_issues=["В студенческой работе не найдено маркеров задания."],
                    )
                )
                continue

            student_code = student_task.joined_code

            # Если решение пустое, можно сразу выдать вердикт без обращения к модели.
            if not student_code:
                task_grades.append(
                    TaskGrade(
                        task_id=task_id,
                        max_score=max_score,
                        score_multiplier=0.0,
                        requires_manual_check=False,
                        comment="Решение отсутствует.",
                        detected_issues=["Нет кода между маркерами задания."],
                    )
                )
                continue

            prompt = build_grading_prompt(
                task_id=task_id,
                reference_code=reference_task.joined_code,
                student_code=student_code,
                max_points=max_score,
            )

            result = self.client.grade_solution(prompt)

            task_grades.append(
                TaskGrade(
                    task_id=task_id,
                    max_score=max_score,
                    score_multiplier=result["score_multiplier"],
                    requires_manual_check=result["requires_manual_check"],
                    comment=result["comment"],
                    detected_issues=result["detected_issues"],
                )
            )

        return StudentGrade(
            name=student_name or student_notebook.stem,
            tasks=task_grades,
        )


def grades_to_summary_dataframe(
    grades: list[StudentGrade],
    config: GradingConfig,
) -> pd.DataFrame:
    """
    Summary:
    Одна строка — одна работа.
    """

    task_ids = sorted({task.task_id for grade in grades for task in grade.tasks})

    rows = []

    for grade in grades:
        by_task = {task.task_id: task for task in grade.tasks}

        row = {
            "Работа": grade.name,
            "Балл": grade.total_score,
            "Макс. балл": grade.max_score,
            "Итог": grade.final_grade,
            "Нужна ручная проверка": "Да" if grade.requires_manual_check else "Нет",
        }

        for task_id in task_ids:
            title = config.get_title_for(task_id)
            task = by_task.get(task_id)

            row[title] = task.score if task else 0

        rows.append(row)

    return pd.DataFrame(rows)


def grade_to_details_dataframe(
    grade: StudentGrade,
    config: GradingConfig,
) -> pd.DataFrame:
    """
    Детальный разбор по одной работе:
    Одна строка — одно задание.
    """

    rows = []

    for task in grade.tasks:
        rows.append(
            {
                "Задание": config.get_title_for(task.task_id),
                "Балл": task.score,
                "Макс. балл": task.max_score,
                "Нужна ручная проверка": "Да" if grade.requires_manual_check else "Нет",
                "Комментарий": task.comment,
                "Проблемы": "\n".join(task.detected_issues),
            }
        )

    return pd.DataFrame(rows)


def export_results(
    grades: list[StudentGrade],
    config: GradingConfig,
    path: Path,
) -> Path:
    """
    Экспортирует результаты проверки в XLSX.

    Структура:
    - Summary: общая таблица по всем работам
    - Лист с подробной информацией по каждой работе
    """

    if path.suffix != ".xlsx":
        path = path.with_suffix(".xlsx")

    summary_df = grades_to_summary_dataframe(grades, config)

    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        _write_sheet(
            writer=writer,
            sheet_name="Summary",
            dataframe=summary_df,
        )

        used_sheet_names = {"Summary"}

        for grade in grades:
            sheet_name = _make_valid_sheet_name(
                raw_name=grade.name,
                used_names=used_sheet_names,
            )
            used_sheet_names.add(sheet_name)

            details_df = grade_to_details_dataframe(
                grade=grade,
                config=config,
            )

            _write_sheet(
                writer=writer,
                sheet_name=sheet_name,
                dataframe=details_df,
            )

    return path


def _write_sheet(
    writer: pd.ExcelWriter,
    sheet_name: str,
    dataframe: pd.DataFrame,
) -> None:
    """
    Пишет DataFrame на лист и добавляет базовое форматирование.
    """

    dataframe.to_excel(
        excel_writer=writer,
        index=False,
        sheet_name=sheet_name,
    )

    # xlsxwriter плохо типизирован, делаем явные касты
    workbook = cast(Workbook, writer.book)
    worksheet = cast(Worksheet, writer.sheets[sheet_name])

    # TODO: можно продумать более интересное оформление
    header_format = workbook.add_format(
        {
            "bold": True,
            "bg_color": "#EAEAEA",
            "border": 1,
        }
    )
    cell_format = workbook.add_format(
        {
            "text_wrap": True,  # Для длинных текстовых ячеек (комментарий и проблемы)
            "valign": "top",  # Аналогично
            "border": 1,
        }
    )

    for col_num, column_name in enumerate(dataframe.columns):
        # Применяем формат заголовка
        worksheet.write(0, col_num, column_name, header_format)

        values = dataframe[column_name].tolist()

        # Вычисляем нужную ширину колонки (min=12, max=60)
        max_value_length = max(
            [
                _max_line_length(column_name),
                *(_max_line_length(value) for value in values),
            ],
            default=12,
        )
        width = min(max(max_value_length + 2, 12), 60)

        # Применяем формат ячеек + ширину
        worksheet.set_column(col_num, col_num, width, cell_format)

    # Фиксируем при скролле первый столбец и первую строку
    worksheet.freeze_panes(1, 1)

    if not dataframe.empty:
        # Применяем к таблице возможность фильтровать/сортировать колонки
        worksheet.autofilter(0, 0, len(dataframe), max(len(dataframe.columns) - 1, 0))


def _max_line_length(value: object) -> int:
    """
    Получает длину самой длинной строки в строковом представлении значения.
    """

    lines = str(value).splitlines()
    if not lines:
        return 0
    return max(len(line) for line in lines)


def _make_valid_sheet_name(
    raw_name: str,
    used_names: set[str],
) -> str:
    """
    Делает валидное имя Excel-листа.
    https://stackoverflow.com/questions/451452/valid-characters-for-excel-sheet-names
    """

    invalid_chars = "[]:*?/\\"

    name = "".join("_" if char in invalid_chars else char for char in raw_name).strip()

    if not name:
        name = "Work"

    name = name[:31]

    if name not in used_names:
        return name

    index = 1

    while True:
        suffix = f"_{index}"
        base = name[: 31 - len(suffix)]
        next_try = f"{base}{suffix}"

        if next_try not in used_names:
            return next_try

        index += 1
