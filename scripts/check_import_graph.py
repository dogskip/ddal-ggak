"""Find runtime modules without source references, including literal dynamic imports."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path


def unreferenced(repository: Path) -> tuple[int, list[str]]:
    source = repository / "src"
    modules = {
        ".".join(path.relative_to(source).with_suffix("").parts).removesuffix(".__init__"): path
        for path in (source / "ddk").rglob("*.py")
    }
    incoming: dict[str, set[str]] = {name: set() for name in modules}
    for name, path in modules.items():
        package = name if path.name == "__init__.py" else name.rpartition(".")[0]
        for node in ast.walk(ast.parse(path.read_text())):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                parts = package.split(".")
                prefix = ".".join(parts[: len(parts) - node.level + 1]) if node.level else ""
                target = ".".join(part for part in (prefix, node.module or "") if part)
                targets = [target, *[target + "." + alias.name for alias in node.names]]
            elif isinstance(node, ast.Call) and node.args:
                function = node.func
                if (isinstance(function, ast.Name) and function.id == "import_module") or (
                    isinstance(function, ast.Attribute) and function.attr == "import_module"
                ):
                    argument = node.args[0]
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                        targets = [argument.value]
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                targets = re.findall(r"(?:from|import)\s+(ddk\.[a-zA-Z0-9_.]+)", node.value)
            for target in targets:
                if target in incoming and target != name:
                    incoming[target].add(name)
    unused = sorted(
        name
        for name, path in modules.items()
        if not incoming[name] and path.name not in {"__init__.py", "__main__.py"}
    )
    return len(modules), unused


def main() -> int:
    count, unused = unreferenced(Path(__file__).resolve().parents[1])
    print(json.dumps({"modules": count, "unreferenced": unused}))
    return bool(unused)


if __name__ == "__main__":
    raise SystemExit(main())
