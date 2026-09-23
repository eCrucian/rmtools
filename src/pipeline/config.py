"""Leitura de config/*.yaml. Tenta PyYAML; se ausente, cai num parser mínimo
próprio (mesmo padrão try/except do resto do projeto, CLAUDE.md §2.2) que cobre
só o subconjunto de YAML usado pelos arquivos deste repositório: mapeamentos
aninhados, listas de escalares e listas de mapeamentos simples — sem âncoras,
multi-linha, ou outras features avançadas do YAML.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml

    _HAS_YAML = True
except ImportError:  # pragma: no cover - exercitado quando pyyaml não está instalado
    _HAS_YAML = False


def load_yaml(path: str | Path) -> Any:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if _HAS_YAML:
        return yaml.safe_load(text)
    return _minimal_yaml_load(text)


def _scalar(token: str) -> Any:
    token = token.strip()
    if token in ("", "null", "~"):
        return None
    if token == "true":
        return True
    if token == "false":
        return False
    if token.startswith('"') and token.endswith('"'):
        return token[1:-1]
    if token.startswith("'") and token.endswith("'"):
        return token[1:-1]
    if token.startswith("[") and token.endswith("]"):
        inner = token[1:-1].strip()
        if not inner:
            return []
        return [_scalar(part) for part in inner.split(",")]
    if token.startswith("{") and token.endswith("}"):
        inner = token[1:-1].strip()
        result: dict[str, Any] = {}
        if inner:
            for part in inner.split(","):
                k, _, v = part.partition(":")
                result[k.strip().strip("\"'")] = _scalar(v)
        return result
    try:
        if any(c in token for c in (".", "e", "E")) and token.lstrip("+-").replace(".", "", 1).isdigit():
            return float(token)
        return int(token)
    except ValueError:
        return token


def _strip_inline_comment(line: str) -> str:
    """Remove um comentário `# ...` à direita, respeitando aspas simples/duplas
    (suficiente para os arquivos deste repositório — não lida com '#' escapado)."""
    in_single = in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i]
    return line


def _minimal_yaml_load(text: str) -> dict:
    raw_lines = (_strip_inline_comment(line).rstrip() for line in text.split("\n"))
    lines = [line for line in raw_lines if line.strip() and not line.strip().startswith("#")]

    def indent(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    def parse_block(lines: list[str], start: int, base_indent: int) -> tuple[Any, int]:
        i = start
        if i < len(lines) and lines[i].lstrip().startswith("- "):
            items: list[Any] = []
            while i < len(lines) and indent(lines[i]) == base_indent and lines[i].lstrip().startswith("- "):
                rest = lines[i].lstrip()[2:]
                if ":" in rest and not rest.strip().startswith(("[", "{", '"', "'")):
                    key, _, value = rest.partition(":")
                    item: dict[str, Any] = {}
                    value = value.strip()
                    if value:
                        item[key.strip()] = _scalar(value)
                    else:
                        sub, i = parse_block(lines, i + 1, base_indent + 2)
                        item[key.strip()] = sub
                        items.append(item)
                        continue
                    i += 1
                    while (
                        i < len(lines)
                        and indent(lines[i]) > base_indent
                        and not lines[i].lstrip().startswith("- ")
                    ):
                        k2, _, v2 = lines[i].strip().partition(":")
                        item[k2.strip()] = _scalar(v2)
                        i += 1
                    items.append(item)
                else:
                    items.append(_scalar(rest))
                    i += 1
            return items, i

        result: dict[str, Any] = {}
        while i < len(lines) and indent(lines[i]) == base_indent:
            key, _, value = lines[i].strip().partition(":")
            value = value.strip()
            if value:
                result[key.strip()] = _scalar(value)
                i += 1
            else:
                if i + 1 < len(lines) and indent(lines[i + 1]) > base_indent:
                    sub, i = parse_block(lines, i + 1, indent(lines[i + 1]))
                    result[key.strip()] = sub
                else:
                    result[key.strip()] = None
                    i += 1
        return result, i

    parsed, _ = parse_block(lines, 0, 0)
    return parsed
