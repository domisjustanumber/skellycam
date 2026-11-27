"""No file in `tools/` imports a package of the product.

The doc checks in CI install only the dev group, so the product is not importable there. A script or a
test that imports the product is in the product package, with its tests.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def product_packages() -> set[str]:
    """The packages of the repository: each folder with an `__init__.py` in the root or in `src/`."""
    found = (*ROOT.glob("*/__init__.py"), *ROOT.glob("src/*/__init__.py"))
    return {path.parent.name for path in found} - {"tools"}


def imported(tree: ast.AST) -> set[str]:
    """The first name of each absolute import, also of an import in a function."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_no_file_in_tools_imports_the_product() -> None:
    packages = product_packages()
    found = [
        f"{path.relative_to(ROOT).as_posix()}: imports {', '.join(sorted(hits))}"
        for path in sorted((ROOT / "tools").rglob("*.py"))
        if (hits := imported(ast.parse(path.read_bytes(), str(path))) & packages)
    ]
    assert not found, "Move each file into the product package, with its test:\n" + "\n".join(found)


def test_the_check_finds_each_form_of_import() -> None:
    tree = ast.parse("import pkg1\nimport pkg2.sub as two\ndef f():\n    from pkg3.sub import x\nfrom . import pkg4\n")
    assert imported(tree) == {"pkg1", "pkg2", "pkg3"}
