#!/usr/bin/env python3
"""Keep the kit text of this repository in step with the agents and ADR kit (decision 0001).

Usage::

    python tools/kit_sync.py check                 # offline: the kit text against kit.toml
    python tools/kit_sync.py pull [SHA]            # take the kit at SHA (default: HEAD of the kit)
    python tools/kit_sync.py pull --replace UNIT   # also write the kit text over a refused local text
    python tools/kit_sync.py propose [UNIT ...]    # write the local changes into the kit working tree
    python tools/kit_sync.py propose --new UNIT    # add a new unit to the kit
    python tools/kit_sync.py propose --fill NAME --literal NAME   # how to read a value in a changed line

The kit is the folder ``agents-and-adr-process/`` of the freemocap/project repository. Its file
``manifest.toml`` lists the kit text. Each item is a unit:

- A file unit (``[[file]]``) is a kit-owned file. Its ID is its path.
- A block unit (``[[block]]``) is the lines between the marker lines ``<!-- kit:<name> -->`` and
  ``<!-- /kit -->`` of a file, or ``# kit:<name>`` and ``# /kit`` in a YAML, TOML or ignore file.
  Its ID is ``<path>#<name>``. The marker lines stay in the file. Blocks do not nest.
- All other text is repo-owned. The tool does not change it.

The kit text of a unit is in ``bootstrap/<path>`` of the kit, or in the path that the item gives
with ``kit = "..."``. A placeholder in a unit is a name in upper case between two pairs of braces.
The table ``[values]`` of ``kit.toml`` gives the value of each name. A value is one line of text.

``kit.toml`` is in the repository root. The repository owns its tables: ``[sync]`` (``adopt``, the
unit IDs that the repository takes, default all; ``skip``, the unit IDs that it does not take;
``kit``, the path of the kit checkout), ``[values]``, and one table for each check tool. The table
``[kit]`` at its end is written by ``pull`` and ``propose``: ``commit``, the full SHA of the kit
commit taken; ``[kit.hashes]``, the SHA-256 of the filled text of each unit at that commit; and
``[kit.pending]``, the SHA-256 of each local change that ``propose`` wrote into the kit.

- ``check`` needs no kit checkout. It passes when there is no ``kit.toml`` ("not adopted"). It
  reports each unit whose text does not have its hash or its pending hash. With a kit checkout, the
  command also prints a note when the kit has a newer text of a unit. The note does not fail.
- ``pull`` reads the kit only with ``git show <SHA>:<path>``. It compares each unit three ways: the
  kit text at the commit in ``kit.toml``, the kit text at SHA, and the local text. It writes the kit
  text when the local text did not change. It keeps a local change when the kit did not change the
  unit. It refuses when both changed, or when a unit with no hash has a different local text. A copy
  of the kit file with its placeholders not filled in is not a change. A refusal prints the
  difference and writes nothing. ``--replace UNIT`` writes the kit text for that
  unit. Then the tool writes the commit and the hashes.
- ``propose`` writes each changed unit into the kit working tree, with the values changed back to
  their placeholders. It refuses when the kit HEAD changed the unit after the commit in
  ``kit.toml`` (run ``pull`` first). A value in a changed line becomes its placeholder only when the
  same line of the kit text has the placeholder at that position. In each other case it refuses,
  unless ``--fill NAME`` (a placeholder) or ``--literal NAME`` (text) tells it. It also refuses a
  new citation of a decision entry: the kit text cites only the kit entry 0001. A new block needs
  its marker lines in the kit file first. ``propose`` never commits and never pushes.

The tool finds the kit checkout with ``--kit PATH``, then ``kit`` in ``[sync]``, then ``../project``,
or two folders up when this repository is in the ``repos/`` folder of that checkout.

The tool writes LF line ends into each file that it writes. It reads CRLF as LF.

Exit codes: 0 for a pass, 1 for a failure or a refusal, 2 for a usage error. Standard library and
the git CLI only. Python 3.13 or later.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

KIT_FOLDER = "agents-and-adr-process"
MANIFEST = "manifest.toml"
CONFIG = "kit.toml"
STATE_HEADER = "# The table [kit] is written by tools/kit_sync.py pull and propose. Do not edit it."
STATE_TABLES = ("[kit]", "[kit.hashes]", "[kit.pending]")

MARKER = re.compile(
    r"^[ \t]*(?:<!--[ \t]*(?:kit:(?P<html>[a-z0-9-]+)|(?P<html_end>/kit))[ \t]*-->"
    r"|#[ \t]*(?:kit:(?P<hash>[a-z0-9-]+)|(?P<hash_end>/kit)))[ \t]*$"
)
PLACEHOLDER = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
# A citation of a decision entry other than the kit entry 0001: ADR-<ID>, (decision <ID>) or an entry
# link. XXXX is the example ID of the docs, not an entry.
CITATION = re.compile(
    r"ADR-(?!0001\b|XXXX\b)[0-9A-Z]{4}\b|\(decisions? (?!0001\b|XXXX\b)[0-9A-Za-z]{4}[),; ]|entries/(?!0001-)[0-9A-Za-z]{4}-"
)
GIT = shutil.which("git") or "git"


class KitError(Exception):
    """A refusal or a failure. The message tells what to do."""


@dataclass(frozen=True)
class Unit:
    path: str  # the path in the repository
    kit: str  # the path in the kit folder
    block: str = ""  # the marker name; "" for a file unit

    @property
    def id(self) -> str:
        return f"{self.path}#{self.block}" if self.block else self.path


# Text and blocks.


def norm(text: str) -> str:
    return text.replace("\r\n", "\n")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def blocks(text: str, where: str) -> dict[str, tuple[int, int]]:
    """The line range [start, end) of the text of each block, between its marker lines."""
    found: dict[str, tuple[int, int]] = {}
    name, start = "", 0
    for number, line in enumerate(norm(text).split("\n")):
        marker = MARKER.match(line)
        if not marker:
            continue
        new = marker.group("html") or marker.group("hash")
        if new and name:
            raise KitError(f"{where}:{number + 1}: kit:{new} starts inside kit:{name}; blocks do not nest")
        if new and new in found:
            raise KitError(f"{where}:{number + 1}: a second block kit:{new}")
        if new:
            name, start = new, number + 1
        elif not name:
            raise KitError(f"{where}:{number + 1}: an end marker closes no block")
        else:
            found[name], name = (start, number), ""
    if name:
        raise KitError(f"{where}:{start}: kit:{name} has no end marker")
    return found


def unit_text(text: str | None, unit: Unit, where: str) -> str | None:
    """The text of the unit in the text of its file, or None when the file or the block is missing."""
    if text is None:
        return None
    text = norm(text)
    if not unit.block:
        return text
    span = blocks(text, where).get(unit.block)
    if span is None:
        return None
    return "\n".join(text.split("\n")[span[0] : span[1]])


def put_unit(text: str | None, unit: Unit, new: str, where: str) -> str:
    """The text of the file with the new text of the unit, with LF line ends."""
    if not unit.block:
        return norm(new)
    assert text is not None
    lines = norm(text).split("\n")
    start, end = blocks(text, where)[unit.block]
    lines[start:end] = norm(new).split("\n") if new else []
    return "\n".join(lines)


def read_file(path: Path) -> str | None:
    """The text of the file with its line ends unchanged, or None when there is no file."""
    return path.read_bytes().decode("utf-8") if path.is_file() else None


def write_file(path: Path, text: str) -> None:
    """Write the text with LF line ends: each repository uses LF on each system."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(norm(text), encoding="utf-8", newline="\n")


# Values and placeholders.


def check_values(values: object) -> dict[str, str]:
    if not isinstance(values, dict):
        raise KitError(f"{CONFIG}: [values] must be a table")
    for name, value in values.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            raise KitError(f"{CONFIG}: [values] {name}: a name is upper case, digits and _")
        if not isinstance(value, str) or not value or "\n" in value or PLACEHOLDER.search(value):
            raise KitError(f"{CONFIG}: [values] {name}: a value is one line of text, not empty, with no placeholder")
    return values


def fill(text: str, values: dict[str, str], where: str) -> str:
    missing = sorted({name for name in PLACEHOLDER.findall(text) if name not in values})
    if missing:
        raise KitError(f"{where}: [values] of {CONFIG} has no value for {', '.join(missing)}")
    return PLACEHOLDER.sub(lambda m: values[m.group(1)], text)


def entry_citations(text: str, path: str) -> list[str]:
    """The citations of entries other than 0001. A test cites by ``(decision XXXX)`` only: its other IDs are data."""
    found = [m.group().rstrip("),; ") for m in CITATION.finditer(text)]
    return [c for c in found if c.startswith("(")] if path.startswith("tools/tests/") else found


def placeholder(name: str) -> str:
    return "{" * 2 + name + "}" * 2


def value_pattern(values: dict[str, str]) -> re.Pattern[str] | None:
    """A value as a whole token: not a part of a longer word, path or name. The longest value wins.

    A value with a / is a path. It can follow a /, for example in the link target ../../<value>.
    """
    if not values:
        return None

    def token(value: str) -> str:
        before = (r"(?<![\w.-])" if "/" in value else r"(?<![\w./-])") if re.match(r"\w", value[0]) else ""
        after = r"(?![\w/-]|\.\w)" if re.match(r"\w", value[-1]) else ""
        return before + re.escape(value) + after

    return re.compile("|".join(token(v) for v in sorted(set(values.values()), key=len, reverse=True)))


@dataclass
class Unfill:
    values: dict[str, str]
    fill_names: frozenset[str] = frozenset()
    literal_names: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        self.pattern = value_pattern(self.values)
        self.names: dict[str, list[str]] = {}
        for name, value in sorted(self.values.items()):
            self.names.setdefault(value, []).append(name)
        unknown = sorted((self.fill_names | self.literal_names) - set(self.values))
        if unknown:
            raise KitError(f"--fill and --literal name no value of {CONFIG}: {', '.join(unknown)}")
        both = sorted(self.fill_names & self.literal_names)
        if both:
            raise KitError(f"--fill and --literal both name {', '.join(both)}")

    def line(self, line: str, base: str | None) -> tuple[str, list[str]]:
        """The kit form of a changed line, and the problems. `base` is the kit line at that place.

        The filled kit line and the local line are compared character by character. A placeholder
        whose filled value is in an unchanged part stays a placeholder. A value in an unchanged part
        that is text in the kit stays text. Each other value goes by --fill and --literal, or it is
        a problem.
        """
        spans: dict[tuple[int, int], str | None] = {}
        unchanged: list[tuple[int, int]] = []
        if base is not None:
            filled, placeholders = self.fill_spans(base)
            matcher = difflib.SequenceMatcher(None, filled, line, autojunk=False)
            blocks = [(a, b, n) for a, b, n in matcher.get_matching_blocks() if n]
            unchanged = [(b, b + n) for _, b, n in blocks]
            for start, end, name in placeholders:
                for a, b, n in blocks:
                    if a <= start and end <= a + n:
                        spans[(b + start - a, b + end - a)] = name
                        break
        problems: list[str] = []
        for hit in self.pattern.finditer(line) if self.pattern else ():
            if any(s < hit.end() and hit.start() < e for s, e in spans):
                continue
            candidates = self.names[hit.group()]
            chosen = [n for n in candidates if n in self.fill_names]
            if any(s <= hit.start() and hit.end() <= e for s, e in unchanged):
                continue
            if len(chosen) == 1:
                spans[hit.span()] = chosen[0]
            elif not all(n in self.literal_names for n in candidates):
                problems.append(
                    f"`{hit.group()}` is the value of {', '.join(candidates)}, but the kit text has no"
                    " placeholder at this place; give --fill NAME or --literal NAME"
                )
        out, last = [], 0
        for (start, end), name in sorted(spans.items()):
            out += [line[last:start], placeholder(name) if name else line[start:end]]
            last = end
        return "".join(out) + line[last:], problems

    def fill_spans(self, base: str) -> tuple[str, list[tuple[int, int, str]]]:
        """The filled kit line, and the place and name of each filled placeholder in it."""
        out: list[str] = []
        spans: list[tuple[int, int, str]] = []
        last = length = 0
        for match in PLACEHOLDER.finditer(base):
            text = base[last : match.start()]
            value = self.values.get(match.group(1), match.group())
            out += [text, value]
            spans.append((length + len(text), length + len(text) + len(value), match.group(1)))
            length += len(text) + len(value)
            last = match.end()
        return "".join(out) + base[last:], spans

    def text(self, kit: str, local: str, where: str) -> tuple[str, list[str]]:
        """The kit form of the local text, and a note for each value that became a placeholder.

        A line that is the same as the filled kit text takes its kit line. Each other line goes
        through line(), with the most similar kit line of its changed part, for example after a
        paragraph is wrapped again. A raised KitError lists each problem.
        """
        base = kit.split("\n") if kit else []
        filled = fill(kit, self.values, where).split("\n") if kit else []
        mine = local.split("\n")
        out: list[str] = []
        notes: list[str] = []
        problems: list[str] = []
        matcher = difflib.SequenceMatcher(None, filled, mine, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                out += base[i1:i2]
                continue
            for j in range(j1, j2):
                ratio, near = max(
                    ((difflib.SequenceMatcher(None, filled[i], mine[j], autojunk=False).ratio(), i) for i in range(i1, i2)),
                    default=(0.0, -1),
                )
                new, found = self.line(mine[j], base[near] if ratio >= 0.5 else None)
                problems += [f"{where}: line {j + 1}: {p}" for p in found]
                if new != mine[j]:
                    notes.append(f"{where}: line {j + 1}: {new.strip()}")
                out.append(new)
        if problems:
            raise KitError("\n".join(problems))
        return "\n".join(out), notes


# The kit checkout.


def git_show(kit: Path, commit: str, path: str) -> str | None:
    out = subprocess.run(  # noqa: S603
        [GIT, "-C", str(kit), "show", f"{commit}:{KIT_FOLDER}/{path}"], capture_output=True, check=False
    )
    return out.stdout.decode("utf-8") if out.returncode == 0 else None


def resolve(kit: Path, commit: str) -> str:
    out = subprocess.run(  # noqa: S603
        [GIT, "-C", str(kit), "rev-parse", "--verify", "--quiet", commit + "^{commit}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        raise KitError(f"{kit.as_posix()}: no commit {commit}; fetch the kit checkout")
    return out.stdout.strip()


def find_kit(root: Path, config: dict, given: str | None) -> Path | None:
    configured = given or config.get("sync", {}).get("kit")
    if configured:
        path = (root / configured).resolve()
    elif root.resolve().parent.name == "repos":
        path = root.resolve().parents[1]
    else:
        path = (root / ".." / "project").resolve()
    return path if (path / KIT_FOLDER / MANIFEST).is_file() else None


def parse_manifest(text: str | None, where: str) -> list[Unit]:
    if text is None:
        raise KitError(f"{where}: no {KIT_FOLDER}/{MANIFEST}")
    data = tomllib.loads(text)
    units: list[Unit] = []
    for kind in ("file", "block"):
        for row in data.get(kind, []):
            path = row["path"]
            name = row.get("name", "") if kind == "block" else ""
            if kind == "block" and not re.fullmatch(r"[a-z0-9-]+", name):
                raise KitError(f"{where}: block {path}: the name is lower case, digits and -")
            units.append(Unit(path, row.get("kit", f"bootstrap/{path}"), name))
    seen = [u.id for u in units]
    twice = sorted({i for i in seen if seen.count(i) > 1})
    if twice:
        raise KitError(f"{where}: a unit two times: {', '.join(twice)}")
    return units


def kit_unit(kit: Path, commit: str, unit: Unit) -> str | None:
    return unit_text(git_show(kit, commit, unit.kit), unit, f"{commit[:12]}:{unit.kit}")


# kit.toml.


def load_config(root: Path) -> dict | None:
    path = root / CONFIG
    if not path.is_file():
        return None
    with path.open("rb") as file:
        return tomllib.load(file)


def chosen(units: list[Unit], config: dict) -> list[Unit]:
    sync = config.get("sync", {})
    adopt = sync.get("adopt")
    skip = set(sync.get("skip", []))
    return [u for u in units if (adopt is None or u.id in adopt) and u.id not in skip]


def toml_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_state(root: Path, commit: str, hashes: dict[str, str], pending: dict[str, str]) -> None:
    """Write the table [kit] at the end of kit.toml. The text above it stays."""
    path = root / CONFIG
    lines = norm(path.read_text(encoding="utf-8")).split("\n")
    cut = next((i for i, line in enumerate(lines) if line in (STATE_HEADER, "[kit]")), len(lines))
    later = [line for line in lines[cut:] if line.startswith("[") and line.strip() not in STATE_TABLES]
    if later:
        raise KitError(f"{CONFIG}: the table [kit] must be the last table; {later[0]} is after it")
    state = [STATE_HEADER, "[kit]", f"commit = {toml_string(commit)}", "", "[kit.hashes]"]
    state += [f"{toml_string(k)} = {toml_string(v)}" for k, v in sorted(hashes.items())]
    if pending:
        state += ["", "[kit.pending]"] + [f"{toml_string(k)} = {toml_string(v)}" for k, v in sorted(pending.items())]
    head = "\n".join(lines[:cut]).rstrip("\n")
    text = (head + "\n\n" if head else "") + "\n".join(state) + "\n"
    tomllib.loads(text)
    path.write_text(text, encoding="utf-8", newline="\n")


def unit_from_id(uid: str) -> Unit:
    path, _, block = uid.partition("#")
    return Unit(path, f"bootstrap/{path}", block)


def diff(old: str, new: str, old_name: str, new_name: str) -> str:
    lines = difflib.unified_diff(old.split("\n"), new.split("\n"), old_name, new_name, lineterm="")
    return "\n".join(lines)


# The commands.


def check(root: Path) -> tuple[list[str], list[str]]:
    """The errors and the notes of the offline check."""
    config = load_config(root)
    if config is None:
        return [], [f"kit: not adopted (no {CONFIG})"]
    state = config.get("kit", {})
    if not state.get("commit"):
        return [], [f"kit: {CONFIG} has no table [kit]; run `python tools/kit_sync.py pull`"]
    hashes, pending = state.get("hashes", {}), state.get("pending", {})
    errors: list[str] = []
    notes: list[str] = []
    for uid, expected in sorted(hashes.items()):
        unit = unit_from_id(uid)
        try:
            text = unit_text(read_file(root / unit.path), unit, unit.path)
        except KitError as error:
            errors.append(str(error))
            continue
        if text is None:
            errors.append(f"{uid}: missing; run `python tools/kit_sync.py pull`")
            continue
        found = digest(text)
        if found == expected:
            continue
        if pending.get(uid) == found:
            notes.append(f"{uid}: a local change that propose wrote into the kit; it waits for the kit")
            continue
        errors.append(
            f"{uid}: differs from the kit text of {state['commit'][:12]}; run `python tools/kit_sync.py pull`,"
            " or `propose` for a change that the kit must take"
        )
    notes.append(f"kit: {len(hashes)} units of kit commit {state['commit'][:12]} checked")
    return errors, notes


def newer_kit_note(root: Path, kit: Path) -> str | None:
    """A note when the kit HEAD has another text for a unit of this repository."""
    config = load_config(root) or {}
    commit = config.get("kit", {}).get("commit")
    if not commit:
        return None
    head = resolve(kit, "HEAD")
    if head == commit:
        return None
    old = {u.id: u for u in parse_manifest(git_show(kit, commit, MANIFEST), commit[:12])}
    units = chosen(parse_manifest(git_show(kit, head, MANIFEST), head[:12]), config)
    changed = [u.id for u in units if u.id not in old or kit_unit(kit, head, u) != kit_unit(kit, commit, old[u.id])]
    if not changed:
        return None
    return f"kit: the kit HEAD {head[:12]} has a newer text of {len(changed)} units; run `python tools/kit_sync.py pull`"


def pull(root: Path, kit: Path, target: str = "HEAD", replace: frozenset[str] = frozenset()) -> list[str]:
    """Take the kit at `target`. Return the notes. Raise KitError for a refusal; then nothing changes."""
    config = load_config(root)
    if config is None:
        raise KitError(f"no {CONFIG}; copy bootstrap/{CONFIG} of the kit and fill in [values] first")
    values = check_values(config.get("values", {}))
    state = config.get("kit", {})
    pin = state.get("commit")
    hashes, pending = dict(state.get("hashes", {})), dict(state.get("pending", {}))
    commit = resolve(kit, target)
    units = chosen(parse_manifest(git_show(kit, commit, MANIFEST), commit[:12]), config)
    old = {u.id: u for u in parse_manifest(git_show(kit, pin, MANIFEST), pin[:12])} if pin else {}
    unknown = sorted(replace - {u.id for u in units})
    if unknown:
        raise KitError(f"--replace names no unit of the kit: {', '.join(unknown)}")
    files: dict[str, str | None] = {}
    new_hashes: dict[str, str] = {}
    new_pending: dict[str, str] = {}
    refusals: list[str] = []
    notes: list[str] = []
    for unit in units:
        kit_text = kit_unit(kit, commit, unit)
        if kit_text is None:
            raise KitError(f"{commit[:12]}:{unit.kit}: the kit has no text for {unit.id}")
        filled = fill(kit_text, values, unit.id)
        if unit.path not in files:
            files[unit.path] = read_file(root / unit.path)
        current = files[unit.path]
        local = unit_text(current, unit, unit.path)
        if local is None and (unit.block or current is not None):
            what = f"{unit.path} has no block kit:{unit.block}" if current is not None else f"{unit.path} is missing"
            refusals.append(f"{unit.id}: {what}. Copy it from {unit.kit} of the kit, or add the two marker lines where the block goes.")
            continue
        new_hashes[unit.id] = digest(filled)
        if local == filled:
            continue
        # A unit with no hash and the text of the kit file, before the fill, is an unchanged copy.
        unchanged = local is None or digest(local) == hashes.get(unit.id) or (unit.id not in hashes and local == kit_text)
        if unchanged or unit.id in replace:
            files[unit.path] = put_unit(current, unit, filled, unit.path)
            notes.append(f"{unit.id}: took the kit text")
            continue
        if unit.id not in hashes:
            refusals.append(
                f"{unit.id}: the local text differs from the kit, and kit.toml has no hash for it."
                f" Give --replace {unit.id} to take the kit text.\n{diff(local, filled, 'local', 'kit')}"
            )
            continue
        base = kit_unit(kit, pin, old[unit.id]) if unit.id in old else None
        if base == kit_text:
            if pending.get(unit.id) == digest(local):
                new_pending[unit.id] = pending[unit.id]
            notes.append(f"{unit.id}: kept the local change; the kit did not change it. Run propose to give it to the kit.")
            continue
        refusals.append(
            f"{unit.id}: the kit and the local text both changed. Make the local text agree with the kit, or"
            f" give --replace {unit.id}, then propose the local change again.\n{diff(local, filled, 'local', 'kit')}"
        )
    if refusals:
        raise KitError("\n\n".join(refusals) + "\n\nkit: pull refused; nothing changed")
    for path, text in files.items():
        if text is not None and text != read_file(root / path):
            write_file(root / path, text)
    dropped = sorted(set(hashes) - set(new_hashes))
    notes += [f"{uid}: no longer taken from the kit; it is repo-owned now" for uid in dropped]
    write_state(root, commit, new_hashes, new_pending)
    notes.append(f"kit: took {len(units)} units of kit commit {commit[:12]}")
    return notes


def propose(
    root: Path,
    kit: Path,
    ids: list[str] | None = None,
    new: list[str] | None = None,
    fill_names: frozenset[str] = frozenset(),
    literal_names: frozenset[str] = frozenset(),
) -> list[str]:
    """Write the local changes into the kit working tree. Return the notes. Raise KitError to refuse."""
    config = load_config(root)
    if config is None or not config.get("kit", {}).get("commit"):
        raise KitError(f"no table [kit] in {CONFIG}; run pull first")
    values = check_values(config.get("values", {}))
    state = config["kit"]
    pin, hashes, pending = state["commit"], state.get("hashes", {}), dict(state.get("pending", {}))
    head = resolve(kit, "HEAD")
    pinned = {u.id: u for u in parse_manifest(git_show(kit, pin, MANIFEST), pin[:12])}
    at_head = {u.id: u for u in parse_manifest(git_show(kit, head, MANIFEST), head[:12])}
    manifest_path = kit / KIT_FOLDER / MANIFEST
    work = {u.id: u for u in parse_manifest(read_file(manifest_path), "kit working tree")}
    unfill = Unfill(values, fill_names, literal_names)
    new_units = [work.get(uid) or unit_from_id(uid) for uid in new or []]
    for unit in new_units:
        if unit.id in at_head:
            raise KitError(f"{unit.id}: the kit already has this unit; propose it without --new")
    if ids:
        units = [pinned[uid] for uid in ids if uid in pinned]
        missing = sorted(set(ids) - set(pinned))
        if missing:
            raise KitError(f"no unit of kit commit {pin[:12]}: {', '.join(missing)}; use --new for a new unit")
    else:
        units = []
        for uid in sorted(hashes):
            unit = pinned.get(uid)
            text = unit_text(read_file(root / unit.path), unit, unit.path) if unit else None
            if unit and text is not None and digest(text) not in (hashes[uid], pending.get(uid)):
                units.append(unit)
    writes: dict[Path, str] = {}
    notes: list[str] = []
    refusals: list[str] = []
    for unit in units + new_units:
        local = unit_text(read_file(root / unit.path), unit, unit.path)
        if local is None:
            refusals.append(f"{unit.id}: no local text")
            continue
        is_new = unit in new_units
        base = "" if is_new else kit_unit(kit, pin, unit)
        at_kit_head = kit_unit(kit, head, at_head[unit.id]) if unit.id in at_head else None
        if not is_new and (base is None or at_kit_head != base):
            refusals.append(f"{unit.id}: the kit HEAD {head[:12]} changed this unit after {pin[:12]}; run pull first")
            continue
        try:
            text, found = unfill.text(base, local, unit.id)
        except KitError as error:
            refusals.append(str(error))
            continue
        cited = sorted(set(entry_citations(text, unit.path)) - set(entry_citations(base or "", unit.path)))
        if cited:
            refusals.append(
                f"{unit.id}: the kit text cites only the kit entry 0001; remove or replace {', '.join(cited)}"
            )
            continue
        notes += found
        target = kit / KIT_FOLDER / unit.kit
        current = writes.get(target, read_file(target))
        now = unit_text(current, unit, unit.kit)
        if now is None and (unit.block or not is_new):
            refusals.append(f"{unit.id}: the kit file {unit.kit} has no block kit:{unit.block}; add its two marker lines first")
            continue
        if now is not None and now not in (base, text):
            refusals.append(f"{unit.id}: the kit working tree has another change of this unit; commit or remove it first")
            continue
        writes[target] = put_unit(current, unit, text, unit.kit)
        if not is_new:
            pending[unit.id] = digest(local)
        notes.append(f"{unit.id}: wrote the local change into {KIT_FOLDER}/{unit.kit}")
    if refusals:
        raise KitError("\n\n".join(refusals) + "\n\nkit: propose refused; nothing changed")
    for path, text in writes.items():
        write_file(path, text)
    added = [u for u in new_units if u.id not in work]
    if added:
        rows = [f'\n[[{"block" if u.block else "file"}]]\npath = {toml_string(u.path)}' + (f"\nname = {toml_string(u.block)}" if u.block else "") for u in added]
        write_file(manifest_path, norm(read_file(manifest_path) or "").rstrip("\n") + "\n" + "\n".join(rows) + "\n")
        notes.append(f"{MANIFEST}: added {', '.join(u.id for u in added)}")
    if writes:
        write_state(root, pin, hashes, pending)
        notes.append("kit: commit the kit files in a PR to freemocap/project; its subject cites the entry of this repository")
    else:
        notes.append("kit: no local change to propose")
    return notes


def main(argv: list[str]) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--kit", help="the path of the freemocap/project checkout")
    parser = argparse.ArgumentParser(prog="kit_sync.py", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", parents=[common])
    pull_parser = commands.add_parser("pull", parents=[common])
    pull_parser.add_argument("commit", nargs="?", default="HEAD")
    pull_parser.add_argument("--replace", action="append", default=[], metavar="UNIT")
    propose_parser = commands.add_parser("propose", parents=[common])
    propose_parser.add_argument("units", nargs="*")
    propose_parser.add_argument("--new", action="append", default=[], metavar="UNIT")
    propose_parser.add_argument("--fill", action="append", default=[], metavar="NAME")
    propose_parser.add_argument("--literal", action="append", default=[], metavar="NAME")
    try:
        args = parser.parse_args(argv[1:])
    except SystemExit as error:
        return 2 if error.code else 0
    root = Path.cwd()
    try:
        if args.command == "check":
            errors, notes = check(root)
            kit = find_kit(root, load_config(root) or {}, args.kit)
            try:
                note = newer_kit_note(root, kit) if kit and not errors else None
            except KitError as error:
                note = f"kit: no newer-kit note: {error}"
            print("\n".join(errors + notes + ([note] if note else [])))
            return 1 if errors else 0
        kit = find_kit(root, load_config(root) or {}, args.kit)
        if kit is None:
            print(f"kit: no {KIT_FOLDER}/{MANIFEST} found; clone https://github.com/freemocap/project to ../project or give --kit")
            return 1
        if args.command == "pull":
            notes = pull(root, kit, args.commit, frozenset(args.replace))
        else:
            notes = propose(root, kit, args.units, args.new, frozenset(args.fill), frozenset(args.literal))
        print("\n".join(notes))
        return 0
    except KitError as error:
        print(error)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
