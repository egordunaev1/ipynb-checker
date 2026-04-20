import yaml

from pathlib import Path

from .models import GradingConfig


def load_grading_config(path: Path | None) -> GradingConfig:
    if path is None:
        return GradingConfig()
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return GradingConfig.model_validate(data)
