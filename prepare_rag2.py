# -*- coding: utf-8 -*-
"""
prepare_rag2.py — конвертер TFlex.DOCs.Model.xml -> Markdown для RAG (Gemini).

Вход : TFlex.DOCs.Model.xml (стандартный .NET XML-файл документации).
Выход: tflex_docs_api_rag2.md — компактный MD, сгруппированный по пространствам
       имён и типам, с однострочными записями членов, удобными для поиска.

Принципы компактности:
  * один заголовок на тип, члены — списком, без повторов имени типа;
  * сигнатуры сокращены (System.Int32 -> int, TFlex.DOCs.Model.X.Y -> X.Y);
  * пустые summary и служебные члены (get_/set_, op_*) опускаются;
  * inline-теги (<see>, <paramref>, <c>) сворачиваются в читаемый текст.

Запуск:  python prepare_rag2.py [вход.xml] [выход.md]
"""

import re
import sys
import xml.etree.ElementTree as ET
from collections import OrderedDict

DEFAULT_INPUT = "TFlex.DOCs.Model.xml"
DEFAULT_OUTPUT = "tflex_docs_api_rag2.md"

# ---------------------------------------------------------------------------
# Сокращения имён типов для компактности сигнатур
# ---------------------------------------------------------------------------

BCL_SHORT = {
    "System.String": "string", "System.Int32": "int", "System.Int64": "long",
    "System.Int16": "short", "System.Byte": "byte", "System.SByte": "sbyte",
    "System.Boolean": "bool", "System.Double": "double", "System.Single": "float",
    "System.Decimal": "decimal", "System.Object": "object", "System.Char": "char",
    "System.Void": "void", "System.UInt32": "uint", "System.UInt64": "ulong",
    "System.UInt16": "ushort", "System.Guid": "Guid", "System.DateTime": "DateTime",
    "System.TimeSpan": "TimeSpan", "System.Exception": "Exception",
    "System.Collections.Generic.List": "List",
    "System.Collections.Generic.Dictionary": "Dictionary",
    "System.Collections.Generic.IList": "IList",
    "System.Collections.Generic.IDictionary": "IDictionary",
    "System.Collections.Generic.IEnumerable": "IEnumerable",
    "System.Collections.Generic.ICollection": "ICollection",
    "System.Collections.Generic.IReadOnlyList": "IReadOnlyList",
    "System.Collections.Generic.IReadOnlyDictionary": "IReadOnlyDictionary",
    "System.Collections.Generic.KeyValuePair": "KeyValuePair",
    "System.Collections.ObjectModel.Collection": "Collection",
    "System.Collections.ObjectModel.ReadOnlyCollection": "ReadOnlyCollection",
    "System.Nullable": "Nullable",
}

# Члены, которые не несут смысловой нагрузки для RAG
SKIP_METHOD_NAMES = {"get_", "set_", "op_Equality", "op_Inequality", "op_LessThan",
                     "op_GreaterThan", "op_LessThanOrEqual", "op_GreaterThanOrEqual",
                     "op_Addition", "op_Subtraction", "op_Multiply", "op_Division",
                     "op_Implicit", "op_Explicit", "Finalize", "MemberwiseClone"}

# Пространства имён и префиксы, которые пропускаются при разборе
# (служебные, диагностические и внутренние типы, не используемые при
# разработке макросов — они создают шум для векторного поиска).
SKIP_NAMESPACES = {
    "TFlex.DOCs.Model.Logging",
    "TFlex.DOCs.Model.Internal",
    "TFlex.DOCs.RPC",
    "TFlex.DOCs.Model.WebConfiguration",
    "TFlex.DOCs.Model.CachingFileServer",
    "TFlex.DOCs.Model.FilePreview",
    "TFlex.DOCs.Model.Diagnostics",
    "TFlex.DOCs.Model.Configuration.Configurations.WebConfigurationStructure",
    "TFlex.DOCs.References.CachingFileServer",
}


def is_skipped_name(full_name):
    """Проверяет, относится ли тип или пространство имён к служебным пропускаемым.
    Совпадение как точное, так и для любых подпространств (префикс с точкой)."""
    if not full_name:
        return False
    norm = normalize_class_name(full_name)
    for skip in SKIP_NAMESPACES:
        if norm == skip or norm.startswith(skip + "."):
            return True
    return False

# Русскоязычные алиасы собираются автоматически из XML в build_auto_aliases().
# Статический словарь больше не используется — все соответствия извлекаются
# из входного файла TFlex.DOCs.Model.xml.

# ---------------------------------------------------------------------------
# Автосбор русскоязычных алиасов из XML и фильтрация кириллических имён
# ---------------------------------------------------------------------------

# Шаблон для обнаружения кириллических символов в строке
CYRILLIC_PATTERN = re.compile(r"[\u0400-\u04FF]")


def has_cyrillic(text):
    """Проверяет наличие кириллических символов в строке."""
    return bool(CYRILLIC_PATTERN.search(text)) if text else False


def normalize_class_name(name):
    """Убирает generic-суффиксы `1, `2 и заменяет + на . для вложенных типов."""
    if not name:
        return ""
    base = re.sub(r"`\d+", "", name)
    return base.replace("+", ".")


def normalize_summary(text):
    """Приводит текст summary к единому каноническому виду для сопоставления."""
    if not text:
        return ""
    # Очищаем от переносов строк, лишних пробелов и точек на конце
    s = re.sub(r"\s+", " ", text).strip().rstrip(".").lower()
    return s


def build_auto_aliases(xml_path):
    """
    Предварительный проход по XML для сбора связей латинских
    и кириллических имен членов API с привязкой к классу-владельцу.

    Связующий механизм — совпадение текста <summary> внутри одного класса:
    кириллический и латинский члены с одинаковым описанием и числом
    параметров считаются аналогами.

    Возвращает двухуровневый словарь:
        {norm_owner: {latin_member_name: ru_alias_name}}
    Все соответствия извлекаются строго из входного XML-файла.
    """
    # Нормализованный владелец -> список латинских членов
    latin_by_owner = {}  # norm_owner -> list({"name", "kind", "summary", "param_count"})
    # Нормализованный владелец -> список кириллических членов
    cyr_by_owner = {}    # norm_owner -> list(...)

    for event, el in ET.iterparse(xml_path, events=("end",)):
        if el.tag != "member":
            continue
        mid = el.get("name", "")
        if not mid or mid.startswith("T:"):
            el.clear()
            continue

        kind, head, params_str, ret_str = split_member_id(mid)
        if "." not in head:
            el.clear()
            continue

        owner, mname = head.rsplit(".", 1)
        norm_owner = normalize_class_name(owner)

        # Извлекаем текст summary для сопоставления
        summary_text = ""
        s_elem = el.find("summary")
        if s_elem is not None:
            summary_text = clean_text("".join(s_elem.itertext()))

        # Число параметров (для методов) — определяет сигнатуру
        param_count = len(params_str.split(",")) if params_str else 0

        if has_cyrillic(mname):
            # Кириллический член: сохраняем для последующего сопоставления
            cyr_by_owner.setdefault(norm_owner, []).append({
                "name": mname,
                "kind": kind,
                "summary": normalize_summary(summary_text),
                "param_count": param_count,
            })
        else:
            # Латинский член: сохраняем для сопоставления
            latin_by_owner.setdefault(norm_owner, []).append({
                "name": mname,
                "kind": kind,
                "summary": normalize_summary(summary_text),
                "param_count": param_count,
            })

        el.clear()

    # Сопоставление: для каждого владельца ищем пары латинский <-> кириллический
    # строго по совпадению kind, числа параметров и текста summary.
    # Также формируем множество связанных кириллических членов,
    # чтобы в parse_xml знать, какие из них уже представлены через [RU: ...].
    aliases = {}  # norm_owner -> dict(latin_name -> cyrillic_name)
    matched_cyrillic = set()  # set of (norm_owner, cyrillic_name) tuples

    for norm_owner, latin_list in latin_by_owner.items():
        cyr_list = cyr_by_owner.get(norm_owner, [])
        for latin_item in latin_list:
            for cyr_item in cyr_list:
                # Совпадение типа члена, числа параметров и непустого summary
                if (latin_item["kind"] == cyr_item["kind"]
                        and latin_item["param_count"] == cyr_item["param_count"]
                        and latin_item["summary"] == cyr_item["summary"]
                        and len(latin_item["summary"]) > 5):
                    aliases.setdefault(norm_owner, {})[latin_item["name"]] = cyr_item["name"]
                    matched_cyrillic.add((norm_owner, cyr_item["name"]))
                    break

    # Для базовых классов макромодели формируем общий макро-словарь,
    # чтобы методы макроконтекста всегда получали свой точный алиас
    macro_owners = [
        "TFlex.DOCs.Model.Macros.MacroProvider",
        "TFlex.DOCs.Model.Macros.RefObj",
        "TFlex.DOCs.Model.Macros.ObjectAccessor",
    ]
    macro_common = {}
    for owner in macro_owners:
        norm = normalize_class_name(owner)
        if norm in aliases:
            for latin_name, cyrillic_name in aliases[norm].items():
                macro_common[latin_name] = cyrillic_name
    if macro_common:
        aliases["__MACRO_COMMON__"] = macro_common

    return aliases, matched_cyrillic

# ---------------------------------------------------------------------------
# Нормализация member-ID
# ---------------------------------------------------------------------------

def split_member_id(mid):
    """'M:Ns.Type.Method`1(A~R)' -> (kind, full_name, params_str, ret_str)."""
    kind = mid[0]
    body = mid[2:]
    params_str = ret_str = None
    if "(" in body:
        head, params_str = body.split("(", 1)
        params_str = params_str.rstrip(")")
        if "~" in head:  # операторы преобразования: op_Implicit(A)~B
            head, ret_str = head.split("~", 1)
    else:
        head = body
        if "~" in head:
            head, ret_str = head.split("~", 1)
    return kind, head, params_str, ret_str


def render_type(tname):
    """Читаемое имя типа: backticks -> <T>, {..} -> <..>, BCL-сокращения."""

    # generic arity -> <T>, <T1, T2> ...; ``0/`0 — ссылка на generic-параметр
    def _arity(m):
        n = int(m.group(1))
        if n == 0:
            return "T"
        return "<" + ", ".join("T%d" % i if i else "T" for i in range(n)) + ">"

    tname = re.sub(r"`{1,2}(\d+)", _arity, tname)
    tname = tname.replace("{", "<").replace("}", ">")

    # сокращаем по сегментам: System.Int32 -> int, System.X.Y -> X.Y
    def _short_segment(seg):
        if seg in BCL_SHORT:
            return BCL_SHORT[seg]
        if seg.startswith("System.") and seg.count(".") >= 1:
            return seg.split(".", 1)[1]
        return seg

    out = []
    depth = 0
    cur = []
    for ch in tname:
        if ch == "<":
            out.append(_short_segment("".join(cur)) + "<")
            cur = []
            depth += 1
        elif ch == ">":
            out.append("".join(cur) + ">")
            cur = []
            depth -= 1
        elif ch == "," and depth > 0:
            out.append("".join(cur) + ", ")
            cur = []
        else:
            cur.append(ch)
    out.append(_short_segment("".join(cur)))
    return "".join(out)

def render_params(params_str):
    """'System.Guid,TFlex.DOCs.Model.X@' -> 'Guid guid, X x' — только типы."""
    if not params_str:
        return ""
    types = []
    depth = 0
    cur = []
    for ch in params_str:
        if ch == "<" or ch == "{":
            depth += 1
        elif ch == ">" or ch == "}":
            depth -= 1
        if ch == "," and depth == 0:
            types.append("".join(cur)); cur = []
        else:
            cur.append(ch)
    if cur:
        types.append("".join(cur))
    out = []
    for t in types:
        ref = t.endswith("@")
        ptr = t.endswith("*")
        t = t.rstrip("@*")
        rendered = render_type(t)
        if ref:
            rendered += " ref"
        if ptr:
            rendered += "*"
        out.append(rendered)
    return ", ".join(out)


def short_name(full_name):
    """'Ns.Type.Method' -> 'Type.Method' (тип + член, без длинного namespace)."""
    parts = full_name.rsplit(".", 2)
    if len(parts) >= 3:
        return parts[-2] + "." + parts[-1]
    return full_name

# ---------------------------------------------------------------------------
# Inline-теги документации
# ---------------------------------------------------------------------------

_CREF_RE = re.compile(r'<see(?:also)?\s+cref="([^"]+)"\s*/?>')
_PNAME_RE = re.compile(r'<paramref\s+name="([^"]+)"\s*/?>')
_C_RE = re.compile(r"<c>(.*?)</c>", re.S)
_PARA_RE = re.compile(r"</?para\s*/?>")
_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")


def _cref_text(m):
    kind, head, params, ret = split_member_id(m.group(1))
    if kind == "T":
        return render_type(head)
    return short_name(head)


def clean_text(text):
    """XML-текст -> компактный читаемый текст без тегов."""
    if not text:
        return ""
    text = _CREF_RE.sub(_cref_text, text)
    text = _PNAME_RE.sub(r"`\1`", text)
    text = _C_RE.sub(r"`\1`", text)
    text = _PARA_RE.sub(" ", text)
    text = _TAG_RE.sub("", text)          # неизвестные теги — вырезать
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    text = re.sub(r"\s+", " ", text).strip()
    return text

# ---------------------------------------------------------------------------
# Разбор XML
# ---------------------------------------------------------------------------

class TypeEntry:
    __slots__ = ("name", "ns", "kind", "summary", "members", "display")

    def __init__(self, name, ns, kind):
        self.name = name          # полное имя типа
        self.ns = ns
        self.kind = kind          # class/struct/enum/interface/delegate
        self.summary = ""
        self.display = name       # отображаемое имя (generic -> <T>)
        self.members = []         # (kind, name, summary, params, returns)


def guess_type_kind(name, summary):
    """Грубое определение вида типа (в XML-доках его нет)."""
    return "type"


def parse_xml(path, aliases_dict=None, matched_cyrillic=None):
    """Разбор XML-файла документации в OrderedDict типов.

    aliases_dict — предварительно собранный словарь алиасов
    {norm_owner: {latin_name: cyrillic_name}}, используется для
    определения, является ли кириллический член дублем латинского.
    matched_cyrillic — множество (norm_owner, cyrillic_name) для тех
    кириллических членов, которые уже связаны с латинскими через [RU: ...].
    """
    types = OrderedDict()          # full type name -> TypeEntry
    for event, el in ET.iterparse(path, events=("end",)):
        if el.tag != "member":
            continue
        mid = el.get("name", "")
        if not mid:
            el.clear()
            continue
        kind, head, params_str, ret_str = split_member_id(mid)

        # Пропускаем служебные пространства имён — они не используются при
        # разработке макросов и вызывают ложные срабатывания векторного поиска.
        # Проверяем полный head (включая имя члена), чтобы отсечь вложенные
        # подпространства типа TFlex.DOCs.Model.Logging.SomeHelper.
        if is_skipped_name(head):
            el.clear()
            continue

        if kind == "T":
            # Пропускаем кириллические типы — это служебные обёртки,
            # которые не используются при разработке макросов.
            # Также пропускаем типы из служебных пространств имён.
            if has_cyrillic(head) or is_skipped_name(head):
                el.clear()
                continue
            ns = head.rsplit(".", 1)[0] if "." in head else "(global)"
            disp = render_type(head)   # Type`1 -> Type<T>
            types[head] = TypeEntry(head, ns, guess_type_kind(head, ""))
            types[head].display = disp
            s = el.find("summary")
            if s is not None:
                types[head].summary = clean_text("".join(s.itertext()))
            el.clear()
            continue

        # член типа: имя вида Ns.Type.Member[.extra]
        owner = head.rsplit(".", 1)[0] if "." in head else head

        # Пропускаем членов из служебных пространств имён владельца
        if is_skipped_name(owner):
            el.clear()
            continue

        entry = types.get(owner)
        if entry is None:
            # член generic-типа: owner = Ns.Type`1 — пробуем без arity
            owner_base = re.sub(r"`\d+$", "", owner)
            entry = types.get(owner_base)
        if entry is None:
            # тип-владелец не задокументирован — создаём запись-заглушку,
            # чтобы члены не потерялись (важно для полноты RAG),
            # но пропускаем кириллические владельцы и служебные пространства имён
            if is_skipped_name(owner) or has_cyrillic(owner):
                el.clear()
                continue
            ns = owner.rsplit(".", 1)[0] if "." in owner else "(global)"
            entry = TypeEntry(owner, ns, guess_type_kind(owner, ""))
            types[owner] = entry

        mname = head.rsplit(".", 1)[1]

        # Принцип «Не удалять то, что не связано»:
        # Кириллический член отсекается только если он успешно
        # связался по summary с латинским методом (уже есть [RU: ...]).
        # Если латинской пары по summary не нашлось, но член принадлежит
        # пространствам макромодели (содержит "Macros" в owner) —
        # сохраняем его в Markdown как полноценный метод API.
        if has_cyrillic(mname):
            norm_owner = normalize_class_name(owner)
            # Если кириллический член успешно связался с латинским методом,
            # пропускаем его, чтобы не дублировать запись с [RU: ...].
            if matched_cyrillic and (norm_owner, mname) in matched_cyrillic:
                el.clear()
                continue
            # Если латинской пары по summary не нашлось и член НЕ
            # принадлежит пространствам макромодели — пропускаем.
            elif "Macros" not in norm_owner:
                el.clear()
                continue

        if kind == "M" and (mname in SKIP_METHOD_NAMES or mname in (".ctor", "#ctor")):
            el.clear()
            continue

        summary = ""
        params = OrderedDict()     # name -> text
        value = ""
        returns = ""
        for child in el:
            tag = child.tag
            if tag == "summary":
                summary = clean_text("".join(child.itertext()))
            elif tag == "param":
                params[child.get("name", "")] = clean_text("".join(child.itertext()))
            elif tag == "returns":
                returns = clean_text("".join(child.itertext()))
            elif tag == "value":
                value = clean_text("".join(child.itertext()))
            elif tag == "typeparam":
                params["<" + child.get("name", "") + ">"] = clean_text("".join(child.itertext()))
            elif tag == "remarks":
                r = clean_text("".join(child.itertext()))
                if r:
                    summary = (summary + " " + r).strip()
            elif tag == "example":
                e = clean_text("".join(child.itertext()))
                if e:
                    summary = (summary + " Пример: " + e).strip()
        el.clear()

        if kind == "M":
            mname_disp = re.sub(r"``\d+", "", mname)  # ``1 в имени метода не нужен
            # Приводим к привычному C# виду: ReturnType MethodName(params).
            # Если ret_str отсутствует (тип возврата не указан в XML),
            # проверяем тег <returns> на наличие короткого указания типа
            # (одно слово из букв/цифр или стандартный BCL/DOCs тип).
            # Если явного типа возврата нет — не подставляем фиктивный void,
            # оставляем чистую сигнатуру MethodName(params).
            if ret_str:
                ret_type_disp = render_type(ret_str)
                sig = "%s %s(%s)" % (ret_type_disp, mname_disp, render_params(params_str))
            elif returns and returns.strip():
                # Проверяем, выглядит ли returns как тип (одно слово без пробелов)
                r = returns.strip()
                if " " not in r and len(r) > 0:
                    ret_type_disp = render_type(r)
                    sig = "%s %s(%s)" % (ret_type_disp, mname_disp, render_params(params_str))
                else:
                    sig = "%s(%s)" % (mname_disp, render_params(params_str))
            else:
                sig = "%s(%s)" % (mname_disp, render_params(params_str))
            entry.members.append(("M", sig, summary, params, mname_disp))
        elif kind == "P":
            if params_str:
                # Индексатор: Item(System.String)
                sig = "%s[%s]" % (mname, render_params(params_str))
            elif ret_str:
                # Свойство с известным типом: PropertyType Name { get; set; }
                prop_type = render_type(ret_str)
                sig = "%s %s { get; set; }" % (prop_type, mname)
            else:
                # Тип неизвестен — оставляем чистое имя свойства
                sig = mname
            desc = value or summary
            entry.members.append(("P", sig, desc, params, mname))
        elif kind == "F":
            entry.members.append(("F", mname, summary, params, mname))
        elif kind == "E":
            entry.members.append(("E", mname, summary, params, mname))
    return types

# ---------------------------------------------------------------------------
# Генерация Markdown
# ---------------------------------------------------------------------------

KIND_LABEL = {"M": "Методы", "P": "Свойства", "F": "Поля", "E": "События"}


def member_line(kind, sig, summary, params, raw_name=None, owner_name=None, aliases_dict=None):
    """Одна строка на член: `- `sig` — summary (param: desc; ...)`."""
    parts = ["`" + sig + "`"]

    # Извлекаем чистое имя (без типа, параметров и модификаторов { get; set; })
    # Для методов: "void Name(params)" -> Name; для свойств: "Type Name { get; set; }" -> Name
    bare_name = raw_name if raw_name else sig
    if not raw_name:
        # убираем параметры (от первой скобки) и модификаторы { get; set; } / [indexer]
        cleaned = re.split(r"[\(\{\[]", sig)[0].strip()
        # последнее слово — имя (предыдущее может быть типом)
        tokens = cleaned.rsplit(None, 1)
        if tokens:
            bare_name = tokens[-1]

    # Контекстный поиск алиаса: нормализуем имя владельца
    # и ищем в конкретном классе, а также в общей группе макросов.
    ru_alias = None
    if aliases_dict and bare_name:
        norm_owner = normalize_class_name(owner_name) if owner_name else None
        if norm_owner:
            # 1. Поиск в конкретном классе
            class_map = aliases_dict.get(norm_owner)
            if class_map and bare_name in class_map:
                ru_alias = class_map[bare_name]
            # 2. Если не найден, проверяем базовый контекст макросов
            if ru_alias is None and "__MACRO_COMMON__" in aliases_dict:
                macro_map = aliases_dict["__MACRO_COMMON__"]
                if bare_name in macro_map and "Macros" in norm_owner:
                    ru_alias = macro_map[bare_name]

    if ru_alias:
        parts.append("[RU: %s]" % ru_alias)

    if summary:
        parts.append("— " + summary)
    if params:
        pd = "; ".join("%s: %s" % (k, v) for k, v in params.items() if v)
        if pd:
            parts.append("(" + pd + ")")
    line = " ".join(parts)
    return line


def emit_markdown(types, out_path, aliases_dict=None):
    # группировка по namespace
    by_ns = OrderedDict()
    for t in types.values():
        by_ns.setdefault(t.ns, []).append(t)

    lines = []
    total_members = 0
    lines.append("# T-FLEX DOCs Model API — справочник для RAG")
    lines.append("")
    lines.append("Источник: TFlex.DOCs.Model.xml. Формат: `##` — пространство имён, "
                 "`###` — тип, `-` — член. Ищите по имени типа или метода.")
    lines.append("")
    lines.append("## Содержание (пространства имён)")
    lines.append("")
    for ns, tl in by_ns.items():
        lines.append("- **%s** — %d типов" % (ns, len(tl)))
    lines.append("")

    for ns, tl in by_ns.items():
        lines.append("## %s" % ns)
        lines.append("")
        for t in tl:
            # Самодостаточный заголовок типа с полным путём —
            # при фрагментации сплиттерами заголовок не отрывается от контекста
            lines.append("### [Type] %s" % t.display)
            lines.append("- **Namespace:** `%s`" % t.ns)
            # Экранируем обратные кавычки в FullName для generic-типов
            # (например, `DomainObjectCollection`1` -> `DomainObjectCollection'1`)
            clean_fullname = t.name.replace("`", "'")
            lines.append("- **FullName:** `%s`" % clean_fullname)
            if t.summary:
                lines.append("- **Описание:** %s" % t.summary)
            # группировка членов по виду
            groups = OrderedDict()
            for m in t.members:
                groups.setdefault(m[0], []).append(m)
            for gk in ("M", "P", "F", "E"):
                ms = groups.get(gk)
                if not ms:
                    continue
                lines.append("")
                lines.append("**%s**" % KIND_LABEL[gk])
                lines.append("")
                for kind, sig, summary, params, raw_name in ms:
                    line_content = member_line(kind, sig, summary, params, raw_name, t.name, aliases_dict)
                    if line_content.strip():
                        lines.append("- " + line_content)
                        total_members += 1
            lines.append("")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return total_members

# ---------------------------------------------------------------------------

def main():
    inp = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INPUT
    outp = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUTPUT
    # Предварительный проход: собираем алиасы и множество связанных кириллических членов
    aliases, matched_cyrillic = build_auto_aliases(inp)
    # Второй проход: разбор XML с учётом алиасов и принципа
    # «Не удалять то, что не связано» — кириллические методы макроязыка,
    # не имеющие латинской пары по summary, сохраняются как полные API-члены
    types = parse_xml(inp, aliases, matched_cyrillic)
    n = emit_markdown(types, outp, aliases)
    print("Типов: %d, членов записано: %d" % (len(types), n))
    print("Выход: %s" % outp)


if __name__ == "__main__":
    main()
