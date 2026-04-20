import json
import requests

from typing import Any

from .prompt import SYSTEM_PROMPT


class OllamaError(RuntimeError):
    pass


GRADE_FORMAT: dict[str, Any] = {
    "type": "object",
    "properties": {
        "score_multiplier": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "requires_manual_check": {
            "type": "boolean",
        },
        "comment": {
            "type": "string",
        },
        "detected_issues": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "score_multiplier",
        "requires_manual_check",
        "comment",
        "detected_issues",
    ],
    "additionalProperties": False,
}


class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "deepseek-coder:6.7b",
        timeout_seconds: int = 180,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def grade_solution(self, prompt: str) -> dict[str, Any]:
        url = f"{self.base_url}/api/generate"

        payload = {
            "model": self.model,
            "system": SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": False,
            # Формат ответа
            "format": GRADE_FORMAT,
            "options": {
                # "Разброс" модели
                "temperature": 0.0,
                # Кол-во одновременно видимых токенов
                "num_ctx": 8192,
            },
        }

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OllamaError(f"Ollama request failed: {exc}") from exc

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise OllamaError("Ollama returned a non-JSON HTTP response") from exc

        raw_text = data.get("response", "")

        try:
            result = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise OllamaError(f"Ollama returned invalid grading JSON: {raw_text}") from exc

        return self._validate_result(result)

    @staticmethod
    def _validate_result(result: Any) -> dict[str, Any]:
        """Валидирует возвращаемый моделью JSON.

        Валидация необходима, поскольку даже переданный GRADE_FORMAT
        не на 100% гарантирует его соблюдение.
        """

        if not isinstance(result, dict):
            raise OllamaError("Grading result must be a JSON object")

        required_fields = {
            "score_multiplier",
            "requires_manual_check",
            "comment",
            "detected_issues",
        }

        missing_fields = required_fields - result.keys()
        if missing_fields:
            raise OllamaError(f"Grading result is missing required fields: {missing_fields}")

        score_multiplier = result["score_multiplier"]
        if not isinstance(score_multiplier, int | float):
            raise OllamaError("score_multiplier must be a number")
        if not 0.0 <= float(score_multiplier) <= 1.0:
            raise OllamaError("score_multiplier must be between 0 and 1")
        result["score_multiplier"] = float(score_multiplier)

        if not isinstance(result["requires_manual_check"], bool):
            raise OllamaError("requires_manual_check must be a boolean")

        if not isinstance(result["comment"], str):
            raise OllamaError("comment must be a string")

        if not isinstance(result["detected_issues"], list):
            raise OllamaError("detected_issues must be a list")
        if not all(isinstance(issue, str) for issue in result["detected_issues"]):
            raise OllamaError("detected_issues must contain only strings")

        return result
