import os
import re
import shutil
from pathlib import Path
from collections import defaultdict

# 1. Входные пути
INPUT_MARKDOWN_DIR = Path("./markdown_docs").resolve()
INPUT_API_SMART = Path("./tflex_docs_api_smart.md").resolve()

# 2. Выходные пути
PROJECT_EXPORT_DIR = Path("./export_for_project").resolve()
GITHUB_DOCS_DIR = PROJECT_EXPORT_DIR / ".github" / "docs"
EXAMPLES_DIR = GITHUB_DOCS_DIR / "examples"
GEMINI_DIR = PROJECT_EXPORT_DIR / "for_gemini_notebook"

EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
GEMINI_DIR.mkdir(parents=True, exist_ok=True)

# Стоп-лист общих классов и служебных слов C#
BLACK_LIST_METHODS = {
    "MacroContext", "MacroProvider", "ReferenceObject", "MacrosMacroContext",
    "MacrosMacroProvider", "UIMacroContext", "Base", "Object", "String", "Guid",
    "System", "Exception", "Type", "List", "Dictionary", "IEnumerable", "Action",
    "AddYears", "Math", "Pow", "Contains", "Trim", "IsNullOrEmpty", "Format",
    "ToString", "TFlex", "Model", "Macros", "Macro", "Environment", "Parse",
    "Select", "Where", "ToList", "ToArray", "FirstOrDefault", "First", "Add",
    "Program", "Console", "Task", "Void", "Boolean", "Int32", "Double",
    "ClassName", "Designer", "Value", "Item"
}

MANUAL_DESCRIPTIONS = {
    "1 - Введение": "Архитектура T-FLEX DOCs Open API, терминология, принципы автоматизации",
    "2.1.1 - Общие сведения": "Назначение макросов, отличия от внешних приложений, жизненный цикл",
    "2.1.2 - Создание и редактирование": "Создание макросов в GUI, редактор кода, сборка библиотек DLL",
    "2.1.3 - Использование": "Точки входа Run(), назначение макросов на события и команды",
    "2.2.1 - Общие сведения": "Архитектура внешних подключаемых модулей (плагинов/приложений)",
    "2.2.2 - Генерация API справочников": "Генерация строго типизированных классов для справочников",
    "2.2.3 - Создание и использование приложений": "Сборка независимых EXE/DLL утилит с подключением к серверу",
    "2.3.1 - Общие сведения": "Инструмент ImportReference для пакетного импорта и выгрузки",
    "3.1.5 - Экземпляры": "Концепция экземпляров объектов (ReferenceObjectInstance) в иерархиях",
    "3.18 - Таблица локализации элементов макроязыка": "Таблица соответствия русских и английских имен API"
}

# Подсистемы, которые являются чисто внутренними низкоуровневыми DTO
EXCLUDED_INFRA_PREFIXES = (
    "TFlex.DOCs.Common",
    "TFlex.DOCs.Data",
    "TFlex.DOCs.References",
    "TFlex.DOCs.Projects.Objects.Mail.Data",
    "TFlex.DOCs.Model.Configuration.ControlSettings",
    "TFlex.DOCs.Model.Configuration.Compatibility",
    "TFlex.DOCs.Model.Configuration.Configurations",
    "TFlex.DOCs.Model.Configuration.Dialogs.Layout",
    "TFlex.DOCs.Model.Macros.Flowchart",
    "TFlex.DOCs.Model.Macros.MathExtensions",
    "TFlex.DOCs.Model.Macros.Path",
    "TFlex.DOCs.Model.Macros.Tools",
    "TFlex.DOCs.Model.Macros.Analyzers",
    "TFlex.DOCs.Model.Search.Path",
    "TFlex.DOCs.Model.Search.Rules",
    "TFlex.DOCs.Model.DataExchange",
    "TFlex.DOCs.Model.FilePreview.CADExchange",
    "TFlex.DOCs.Model.FilePreview.CADInteraction",
    "TFlex.DOCs.Model.FilePreview.Contract",
    "TFlex.DOCs.Model.FilePreview.Service",
    "TFlex.DOCs.Model.FilePreview.Settings",
    "TFlex.DOCs.Model.Scheduler",
    "TFlex.DOCs.Model.ScheduleChart",
    "TFlex.DOCs.Model.Diagnostics",
    "TFlex.DOCs.Model.Exceptions",
    "TFlex.DOCs.Model.Logging",
    "TFlex.DOCs.Model.Internal",
    "TFlex.DOCs.Model.Connection",
    "TFlex.DOCs.Model.Undo",
    "TFlex.DOCs.Model.Utils",
    "TFlex.DOCs.Model.WorkingFolder",
    "TFlex.DOCs.Model.ObjectsComparison",
    "TFlex.DOCs.Model.ReferenceRestrictiveLists",
    "TFlex.DOCs.Model.References.Assignments.Converters",
    "TFlex.DOCs.Model.References.Characteristics.Extensions",
    "TFlex.DOCs.Model.References.Codifier.CounterLogic",
    "TFlex.DOCs.Model.References.Codifier.Macros",
    "TFlex.DOCs.Model.References.Codifier.NumberElements",
    "TFlex.DOCs.Model.References.Configurators.Criterias",
    "TFlex.DOCs.Model.References.ConversionTaskQueue.ConversionFormat",
    "TFlex.DOCs.Model.References.ConversionTaskQueue.FileConversionModule",
    "TFlex.DOCs.Model.References.Extensions",
    "TFlex.DOCs.Model.References.Files.FileHistory",
    "TFlex.DOCs.Model.References.Files.Representation",
    "TFlex.DOCs.Model.References.Links.Extensions",
    "TFlex.DOCs.Model.References.Macros.MacroFlowchart",
    "TFlex.DOCs.Model.References.Nomenclature.ConfigurationsManager",
    "TFlex.DOCs.Model.References.Nomenclature.DesignContexts",
    "TFlex.DOCs.Model.References.Nomenclature.ProductsApplicability.Creators",
    "TFlex.DOCs.Model.References.Nomenclature.ProductsClassifier.Helpers",
    "TFlex.DOCs.Model.References.Nomenclature.StructureVariants",
    "TFlex.DOCs.Model.References.Nomenclature.StructuresMapping",
    "TFlex.DOCs.Model.References.RecordControlCards.Mail",
    "TFlex.DOCs.Model.References.RelationTables.Macros",
    "TFlex.DOCs.Model.References.Remarks.DependeciesOfRemarks",
    "TFlex.DOCs.Model.References.Reporting.ReportMacro.Flowchart",
    "TFlex.DOCs.Model.References.Reporting.ReportMacro.ObjectModel",
    "TFlex.DOCs.Model.References.Reporting.ReportsKit",
    "TFlex.DOCs.Model.References.Tasks.Parameters",
    "TFlex.DOCs.Model.References.WorkTime",
)


def clean_markdown_for_llm(text: str) -> str:
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[(?:Иллюстрация|Схема|Рисунок).*?\]", "", text)
    text = re.sub(r"^>\s*$\n?", "", text, flags=re.MULTILINE)

    lines = [line.rstrip() for line in text.splitlines()]
    clean_text = "\n".join(lines)
    while "\n\n\n" in clean_text:
        clean_text = clean_text.replace("\n\n\n", "\n\n")
    return clean_text.strip()


def extract_technical_tags(text: str, filename_stem: str):
    clean_title = re.sub(r"^[\d\.]+\s*-\s*", "", filename_stem).strip()

    for key, desc in MANUAL_DESCRIPTIONS.items():
        if filename_stem.startswith(key):
            return clean_title, [desc]

    tags = []

    # Методы
    method_candidates = re.findall(r"\b([A-ZА-Я][a-zA-Zа-яА-Я0-9_]+)\s*\(", text)
    for m in method_candidates:
        if m not in BLACK_LIST_METHODS and len(m) > 3:
            formatted_m = f"`{m}()`"
            if formatted_m not in tags:
                tags.append(formatted_m)

    # Индексаторы
    indexer_candidates = re.findall(r"\b([A-ZА-Я][a-zA-Zа-яА-Я0-9_]+)\s*\[", text)
    for idx in indexer_candidates:
        if idx in ["Параметр", "ГлобальныйПараметр", "ДиалогВвода"]:
            formatted_idx = f"`{idx}[]`"
            if formatted_idx not in tags:
                tags.append(formatted_idx)

    # Свойства
    prop_candidates = re.findall(r"\b([A-ZА-Я][a-zA-Zа-яА-Я0-9_]+)\.([A-ZА-Я][a-zA-Zа-яА-Я0-9_]+)\b", text)
    for obj, prop in prop_candidates:
        if obj not in BLACK_LIST_METHODS and prop not in BLACK_LIST_METHODS:
            if obj not in ["DateTime", "Math", "String", "Path", "File", "Convert"] and prop not in ["Изменить", "Сохранить", "Удалить"]:
                formatted_prop = f"`{obj}.{prop}`"
                if formatted_prop not in tags:
                    tags.append(formatted_prop)

    # Маркеры
    global_props = ["ИзмененныйПараметр", "ТекущийОбъект", "ТекущийПользователь", "ВыбранныеОбъекты"]
    for gp in global_props:
        if gp in text and f"`{gp}`" not in tags:
            tags.append(f"`{gp}`")

    # Специфичные классы
    code_blocks = re.findall(r"```csharp(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    combined_code = "\n".join(code_blocks)
    if combined_code:
        class_candidates = re.findall(r"\b([A-Z][a-zA-Z0-9_]+)\b", combined_code)
        for c in class_candidates:
            if c not in BLACK_LIST_METHODS and len(c) > 5:
                formatted_c = f"`{c}`"
                if formatted_c not in tags and not any(t.startswith(f"`{c}") for t in tags):
                    tags.append(formatted_c)

    def sort_weight(tag):
        if "[]" in tag: return 0
        if "()" in tag and re.search(r"[А-Я]", tag): return 1
        if "." in tag: return 2
        return 3

    tags.sort(key=sort_weight)

    if not tags:
        tags.append("Спецификация и концепция раздела")

    return clean_title, tags[:7]


def parse_smart_api_reference(api_path: Path):
    if not api_path.exists():
        return {}

    namespace_map = defaultdict(list)
    class_header_regex = re.compile(
        r"^###\s+`?([A-Za-z0-9_`]+)`?\s+\(Namespace:\s+`?([A-Za-z0-9_\.]+)`?\)"
    )

    with api_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            match = class_header_regex.match(line.strip())
            if match:
                class_name = match.group(1).replace("`", "")
                namespace = match.group(2).replace("`", "")
                namespace_map[namespace].append(class_name)

    return namespace_map


def filter_redundant_reference_types(classes: list) -> list:
    """
    Убирает шаблонный шум автогенерации (когда на один справочник есть
    XReference, XReferenceObject, XType, XTypes). Оставляет ключевые типы.
    """
    cleaned = []
    for c in classes:
        # Если есть парные вспомогательные типы, убираем избыточные суффиксы
        if c.endswith("ReferenceObject") and c.replace("ReferenceObject", "Reference") in classes:
            continue
        if c.endswith("Types") and c[:-1] in classes:
            continue
        cleaned.append(c)
    return cleaned


def generate_smart_api_rows(namespace_map):
    index_api_rows = []

    # 1. Прикладные пространства
    for ns in sorted(namespace_map.keys()):
        if any(ns.startswith(p) for p in EXCLUDED_INFRA_PREFIXES):
            continue

        raw_classes = sorted(namespace_map[ns])
        classes = filter_redundant_reference_types(raw_classes)

        classes_display = ", ".join(f"`{c}`" for c in classes)
        index_api_rows.append(f"| `{ns}` | {classes_display} |")

    # 2. Сводка технических подсистем (ровно 5 емких строк)
    index_api_rows.extend([
        "| `TFlex.DOCs.References.*` | *Типизированные оболочки справочников (26 модулей: контакты, координаты, фильтры и др.)* |",
        "| `TFlex.DOCs.Model.FilePreview.*` | *Низкоуровневые DTO и IPC-контракты CAD-просмотрщика (120 классов)* |",
        "| `TFlex.DOCs.Model.DataExchange.*` | *Пакетная сериализация XML/JSON данных сервера (89 классов)* |",
        "| `TFlex.DOCs.Model.Macros.Flowchart.*` | *Элементы и менеджеры визуального дизайнера блок-схем (70 классов)* |",
        "| `TFlex.DOCs.Common.*` / `TFlex.DOCs.Data.*` | *Системные утилиты ядра, криптография, потоки, слой БД (634 класса)* |"
    ])

    return index_api_rows


def build_copilot_instructions_file():
    instructions_path = PROJECT_EXPORT_DIR / ".github" / "copilot-instructions.md"
    content = """# Инструкция для GitHub Copilot: T-FLEX DOCs Open API (C#)

Ты — главный инженер по автоматизации и разработке макросов для системы T-FLEX DOCs на языке C#.

## Структура базы знаний (`.github/docs/`):
- `.github/docs/INDEX.md` — общая карта сценариев и пространств имен API.
- `.github/docs/examples/` — готовые сценарии задач (объекты, файлы, доступы, бизнес-процессы, отчеты).
- `.github/docs/tflex_docs_api_smart.md` — справочник классов, типов, свойств и перегрузок методов.

## Регламент разработки:
1. **Стилистика кода:**
   - Высокоуровневые макросы наследуются от `MacroProvider` (методы `ТекущийОбъект`, `СоздатьОбъект()`, `Параметр[...]`).
   - Низкоуровневые процедуры/плагины используют объекты `ServerConnection`, `Desktop`, `ReferenceCatalog`.
2. **Алгоритм поиска:**
   - Для поиска решений задач делай `@workspace` поиск по `.github/docs/examples/`.
   - Для сверки точных сигнатур обращайся к `.github/docs/tflex_docs_api_smart.md`.
3. **Безопасность данных:**
   - Изменение объекта всегда оборачивается в `BeginChanges()` -> `EndChanges()`.
   - В версионных справочниках обязательно вызывается `CheckOut()` перед правкой и `CheckIn()` после сохранения.
"""
    instructions_path.write_text(content, encoding="utf-8")


def main():
    if not INPUT_MARKDOWN_DIR.exists():
        print(f"❌ Папка '{INPUT_MARKDOWN_DIR}' не найдена!")
        return

    md_files = sorted(
        [f for f in INPUT_MARKDOWN_DIR.glob("**/*.md") if f.name.lower() != "index.md"],
        key=lambda x: x.name.lower()
    )

    print(f"🔍 Генерация индекса для {len(md_files)} файлов примеров...")

    index_example_rows = []
    gemini_examples_content = [
        "# T-FLEX DOCs Open API — Примеры написания макросов и сценариев\n",
        "Практические рецепты решения задач автоматизации в T-FLEX DOCs на C#.\n"
    ]

    for file_path in md_files:
        raw_text = file_path.read_text(encoding="utf-8", errors="ignore")
        cleaned_text = clean_markdown_for_llm(raw_text)

        title, tags = extract_technical_tags(cleaned_text, file_path.stem)
        tags_str = ", ".join(tags)

        llm_file_content = f"""# {title}

> **Ключевые сущности:** {tags_str}
> **Контекст:** T-FLEX DOCs Open API (C# Macro)

{cleaned_text}
"""
        out_example_path = EXAMPLES_DIR / file_path.name
        out_example_path.write_text(llm_file_content, encoding="utf-8")

        index_example_rows.append(f"| `examples/{file_path.name}` | **{title}** | {tags_str} |")
        gemini_examples_content.append(f"\n\n---\n\n## {title}\n\n{cleaned_text}")

    namespace_map = parse_smart_api_reference(INPUT_API_SMART)
    if namespace_map:
        index_api_rows = generate_smart_api_rows(namespace_map)
    else:
        index_api_rows = ["| `TFlex.DOCs.Model` | Поиск классов в `tflex_docs_api_smart.md` |"]

    index_content = f"""# T-FLEX DOCs API — Полная карта базы знаний

> **Поиск информации:**
> 1. **Нужен готовый рецепт решения задачи** -> найдите тему в **Разделе 1 (Примеры сценариев)** и откройте соответствующий файл из папки `examples/`.
> 2. **Нужно узнать методы, свойства или типы параметров конкретного класса** -> найдите его `Namespace` в **Разделе 2 (Карта пространств имён)** и выполните поиск по названию класса в файле `tflex_docs_api_smart.md`.

---

## 1. Сценарии и рецепты кода (How-To Guides)

| Файл с примером | Раздел / Задача | Ключевые методы API, свойства и темы |
| :--- | :--- | :--- |
""" + "\n".join(index_example_rows) + f"""

---

## 2. Карта пространств имён и классов API (`tflex_docs_api_smart.md`)

| Пространство имён (`using ...;`) | Доступные классы и интерфейсы |
| :--- | :--- |
""" + "\n".join(index_api_rows)

    out_index = GITHUB_DOCS_DIR / "INDEX.md"
    out_index.write_text(index_content, encoding="utf-8")
    file_size_kb = len(index_content.encode('utf-8')) / 1024
    print(f"📑 Создан индекс: {out_index} (размер: {file_size_kb:.1f} КБ)")

    if INPUT_API_SMART.exists():
        shutil.copy2(INPUT_API_SMART, GITHUB_DOCS_DIR / "tflex_docs_api_smart.md")
        gemini_api_path = GEMINI_DIR / "T-FLEX DOCs API Reference.md"
        shutil.copy2(INPUT_API_SMART, gemini_api_path)
    else:
        print(f"⚠️ Файл '{INPUT_API_SMART.name}' не найден!")

    gemini_examples_path = GEMINI_DIR / "T-FLEX DOCs Examples.md"
    gemini_examples_path.write_text("\n".join(gemini_examples_content), encoding="utf-8")
    print(f"📦 Сформированы источники Gemini: {GEMINI_DIR.resolve()}")

    build_copilot_instructions_file()
    print("\n🎉 Готово к работе!")


if __name__ == "__main__":
    main()