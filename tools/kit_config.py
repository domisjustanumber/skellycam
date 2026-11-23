"""Read the values of this repository for a check tool from ``kit.toml`` (decision 0001).

``kit.toml`` is in the repository root. Each check tool reads its own table, for example
``[check_decision_log]``. With no ``kit.toml``, a tool uses its defaults. When ``kit.toml`` is
there, the tool fails closed: the table must be there (it can be empty), each key must be a key of
the tool, and each value must have the type of that key. A misspelt table or key, or a value of the
wrong type, then stops the tool. It does not fall back to a default. Standard library only.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

KINDS = {
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "str": lambda v: isinstance(v, str),
    "list[str]": lambda v: isinstance(v, list) and all(isinstance(i, str) for i in v),
    "list[table]": lambda v: isinstance(v, list) and all(isinstance(i, dict) for i in v),
}


def kit_values(root: Path, section: str, keys: dict[str, str]) -> dict:
    """The table ``[section]`` of ``root/kit.toml``, or {} when there is no ``kit.toml``.

    ``keys`` maps each key of the tool to its kind: a key of ``KINDS``.
    """
    path = root / "kit.toml"
    if not path.is_file():
        return {}
    with path.open("rb") as file:
        data = tomllib.load(file)
    if not isinstance(data.get(section), dict):
        raise SystemExit(f"kit.toml: no table [{section}]; add it, also when it is empty")
    table = data[section]
    unknown = sorted(set(table) - set(keys))
    if unknown:
        raise SystemExit(f"kit.toml [{section}]: unknown keys: {', '.join(unknown)}")
    for key, value in table.items():
        if not KINDS[keys[key]](value):
            raise SystemExit(f"kit.toml [{section}] {key}: the value must be {keys[key]}")
    return table
