import argparse

from pathlib import Path

from .config import load_grading_config
from .grader import NotebookGrader, export_results
from .ollama_client import OllamaClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Grade student ipynb files with Ollama model.")
    parser.add_argument("--reference", type=Path, required=True, help="Path to reference .ipynb")
    parser.add_argument(
        "--students", type=Path, required=True, nargs="+", help="Student .ipynb files"
    )
    parser.add_argument("--config", type=Path, default=None, help="Path to grading.yaml")
    parser.add_argument("--output", type=Path, default="grades.xlsx", help="Output .xlsx")
    parser.add_argument("--model", type=str, default="deepseek-coder:6.7b", help="Ollama model")
    parser.add_argument(
        "--base-url", type=str, default="http://localhost:11434", help="Ollama base URL"
    )
    args = parser.parse_args()

    config = load_grading_config(args.config and Path(args.config))
    client = OllamaClient(base_url=args.base_url, model=args.model)
    grader = NotebookGrader(config=config, client=client)

    grades = []
    for student_path in args.students:
        grades.append(
            grader.grade_student(
                reference_notebook=args.reference,
                student_notebook=student_path,
            )
        )

    path = export_results(grades=grades, config=config, path=args.output)
    print(f"Grading results saved as {path}")


if __name__ == "__main__":
    main()
