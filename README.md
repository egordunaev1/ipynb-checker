# IPYNB Checker

Проект для проверки студенческих `.ipynb` ноутбуков по эталону.
GUI: `tkinter`. Проверка корректности: `Ollama` + `deepseek-coder:6.7b`.

## 1. Разметка notebook

В эталоне и студенческих работах задания размечаются отдельными markdown-ячейками:

```markdown
<!-- TASK:01 START -->
```

Затем идут одна или несколько ячеек с решением.

```markdown
<!-- TASK:01 END -->
```

Пример:

```markdown
# Задание 1

Необходимо привести "Hello" к нижнему регистру.

<!-- TASK:01 START -->
```

```python
def task01(text):
    return text.lower()

task01("Hello")
```

```markdown
*Конец решения*
<!-- TASK:01 END -->
```

Эти маркеры являются markdown-комментариями и не отображаются при рендеринге. В той же ячейке может быть и другой текст. Нет необходимости создавать отдельные ячейки под разметку.

## 2. Установка и запуск: macOS / Linux

```bash
git clone https://github.com/egordunaev1/ipynb-checker
cd ipynb-checker

python3 -m venv .venv
source .venv/bin/activate

pip install -e .
```

Запуск Ollama:

```bash
ollama pull deepseek-coder:6.7b
ollama serve
```

Запуск GUI:

```bash
ipynb-checker-gui
```

CLI-запуск:

```bash
ipynb-checker \
  --reference reference.ipynb \
  --students student_01.ipynb student_02.ipynb \
  --config grading.yaml \
  --output grades.xlsx
```

## 3. Установка и запуск: Windows

```powershell
git clone https://github.com/egordunaev1/ipynb-checker
cd ipynb-checker

py -m venv .venv
.venv\Scripts\activate

pip install -e .
```

Запуск Ollama:

```powershell
ollama pull deepseek-coder:6.7b
ollama serve
```

Запуск GUI:

```powershell
ipynb-checker-gui
```

CLI-запуск:

```powershell
ipynb-checker
  --reference reference.ipynb
  --students student_01.ipynb student_02.ipynb
  --config config/grading.yaml
  --output grades.xlsx
```

## 4. Ollama

По умолчанию проект ожидает локально установленную Ollama:

```text
http://localhost:11434/api/generate
```

Можно изменить через аргумент при CLI-запуске или через текстовое поле в GUI.

### Установка Ollama

Скачать Ollama можно с [официального сайта](https://ollama.com).

После установки скачайте модель:

```bash
ollama pull deepseek-coder:6.7b
```

Запустите Ollama server:

```bash
ollama serve
```

Проверьте, что Ollama работает:

```bash
ollama list
```

В списке должна появиться модель:

```text
deepseek-coder:6.7b
```

## 5. Конфиг баллов

`config/grading.yaml`:

```yaml
default_points: 1.0

tasks:
  "01":
    title: "Задание 1"
    points: 1.0
  "02":
    title: "Задание 2"
    points: 2.0
```

Логика начисления баллов:

- `correct` — `points * 1.0`
- `incorrect` — `points * 0`

Если конфиг не задан, имена заданий берутся из markdown-меток, а макс. балл за каждое задание равен `1.0`.
