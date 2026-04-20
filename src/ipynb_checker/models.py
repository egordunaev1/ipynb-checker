from typing import Any
from pydantic import BaseModel, Field, field_validator


class TaskGrade(BaseModel):
    """
    Результат проверки одного задания.
    """

    task_id: str
    # Максимально возможный балл за задание.
    max_score: float = Field(gt=0)
    # Множитель оценки от 0 до 1, который вернула LLM.
    score_multiplier: float = Field(ge=0, le=1)
    # Нужно ли проверить задание вручную (модель не уверена в оценке).
    requires_manual_check: bool = False
    # Комментарий модели.
    comment: str
    # Список найденных проблем.
    detected_issues: list[str] = Field(default_factory=list)

    @field_validator("max_score", "score_multiplier")
    @classmethod
    def _pretty_float(cls, value: float) -> float:
        return round(float(value), 2)

    @property
    def score(self) -> float:
        return self._pretty_float(self.max_score * self.score_multiplier)


class StudentGrade(BaseModel):
    """
    Итог проверки одной студенческой работы.
    """

    # Имя работы (имя студента или файла)
    name: str
    # Результаты проверки заданий
    tasks: list[TaskGrade]

    @classmethod
    def _pretty_float(cls, value: float) -> float:
        return round(float(value), 2)

    @property
    def total_score(self) -> float:
        return self._pretty_float(sum(task.score for task in self.tasks))

    @property
    def max_score(self) -> float:
        return self._pretty_float(sum(task.max_score for task in self.tasks))

    @property
    def final_grade(self) -> float:
        return self._pretty_float(self.total_score / self.max_score)

    @property
    def requires_manual_check(self) -> bool:
        return any(task.requires_manual_check for task in self.tasks)


class ParsedTask(BaseModel):
    """
    Задание, извлечённое из ipynb.
    """

    task_id: str
    code_cells: list[str]
    markdown_cells: list[str] = Field(default_factory=list)
    start_cell_index: int
    end_cell_index: int | None = None

    @property
    def joined_code(self) -> str:
        return "\n\n# --- next cell ---\n\n".join(self.code_cells).strip()


class GradingConfig(BaseModel):
    """
    Конфигурация системы проверки.

    Определяет разбалловку и отображаемые имена заданий.
    Если не указано явно, используется значение по умолчанию:
    1 балл и название из markdown-маркера.
    """

    default_points: float = 1.0
    tasks: dict[str, dict[str, Any]] = Field(default_factory=dict)

    def get_points_for(self, task_id: str) -> float:
        task_config = self.tasks.get(str(task_id), {})
        return float(task_config.get("points", self.default_points))

    def get_title_for(self, task_id: str) -> str:
        task_config = self.tasks.get(str(task_id), {})
        return str(task_config.get("title", f"Задание {task_id}"))
