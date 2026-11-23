"""No commit adds a script for a person to run on a system that is not the test machine (decision VV4Q).

A test on another system runs only through ``skellycam.certify(level)``. The product folders, the
tests and the CI workflows are exempt. A marker in the first lines declares a valid exception.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import check_other_systems as cos
import pytest

REPO_ROOT = Path(cos.__file__).resolve().parents[1]

DARWIN_GUARD = 'import sys\nif sys.platform == "darwin":\n    print(1)\n'
LINUX_PREFIX = 'import sys\nif sys.platform.startswith("linux"):\n    print(1)\n'
LAB_GUARD = 'import sys\nif sys.platform != "win32":\n    raise SystemExit("Windows only")\n'
LAB_ONLY = 'import sys\nif sys.platform == "win32":\n    print(1)\n'


def refused(tmp_path: Path, files: dict[str, str], lab: tuple[str, ...] = ("win32",)) -> list[str]:
    for name, text in files.items():
        path = tmp_path / name.replace("\\", "/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return [line.split(":")[0] for line in cos.check(list(files), tmp_path, lab)]


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_repository_has_no_manual_script_for_another_system() -> None:
    assert cos.check(cos.tracked_files(REPO_ROOT), REPO_ROOT) == []


@pytest.mark.parametrize("text", [DARWIN_GUARD, LINUX_PREFIX, DARWIN_GUARD.replace("==", "!=")])
def test_a_guard_for_another_system_is_refused(tmp_path: Path, text: str) -> None:
    assert refused(tmp_path, {"decisions/scripts/probe.py": text}) == ["decisions/scripts/probe.py"]


@pytest.mark.parametrize("text", [LAB_ONLY, LAB_GUARD])
def test_a_guard_for_the_lab_passes(tmp_path: Path, text: str) -> None:
    assert refused(tmp_path, {"decisions/scripts/probe.py": text}) == []


@pytest.mark.parametrize(
    "name", ["scripts/run_macos.py", "scripts/mac/run.sh", "research/Linux-probe.ps1", "x/run-suite-mac.command"]
)
def test_a_script_named_for_another_system_is_refused(tmp_path: Path, name: str) -> None:
    assert refused(tmp_path, {name: "print(1)\n"}) == [name]


@pytest.mark.parametrize(
    "name", ["scripts/machine.py", "scripts/emacs.py", "notes/linux-setup.md", "decisions/entries/X-macos.md"]
)
def test_a_similar_name_or_a_document_passes(tmp_path: Path, name: str) -> None:
    assert refused(tmp_path, {name: "print(1)\n"}) == []


def test_a_document_with_a_guard_passes(tmp_path: Path) -> None:
    assert refused(tmp_path, {"notes/setup.md": DARWIN_GUARD, "notes/setup.txt": DARWIN_GUARD}) == []


@pytest.mark.parametrize(
    "marker",
    ["# certify-check: cam0:detect:mjpg-mode", "# other-systems: not applicable (it only reads a report)"],
)
def test_a_marker_in_the_first_lines_passes(tmp_path: Path, marker: str) -> None:
    text = "#!/usr/bin/env python3\n" + marker + "\n" + DARWIN_GUARD
    assert refused(tmp_path, {"scripts/run_macos.py": text}) == []


@pytest.mark.parametrize(
    "text",
    [
        "\n" * 5 + "# certify-check: cam0:open\n" + DARWIN_GUARD,
        "# other-systems: not applicable ()\n" + DARWIN_GUARD,
        "# other-systems: not applicable\n" + DARWIN_GUARD,
        "# certify-check:\n" + DARWIN_GUARD,
    ],
)
def test_a_late_or_empty_marker_does_not_pass(tmp_path: Path, text: str) -> None:
    assert refused(tmp_path, {"scripts/probe.py": text}) == ["scripts/probe.py"]


@pytest.mark.parametrize(
    "name",
    [
        "skellycam/core/camera/capture/macos/source.py",
        "skellycam-ui/scripts/linux.sh",
        "skellycam-docs/linux.py",
        ".github/scripts/macos.sh",
        "tools/tests/test_macos.py",
        "decisions/scripts/tests/test_probe.py",
    ],
)
def test_the_product_the_tests_and_ci_are_exempt(tmp_path: Path, name: str) -> None:
    assert refused(tmp_path, {name: DARWIN_GUARD}) == []


def test_lab_platforms_is_set_for_the_repo(tmp_path: Path) -> None:
    assert cos.LAB_PLATFORMS == ("win32",)
    assert refused(tmp_path, {"scripts/probe.py": DARWIN_GUARD}, lab=("darwin",)) == []


def test_windows_separators_and_the_refusal_line(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run_linux.sh").write_text("echo 1\n", encoding="utf-8")
    assert cos.check(["scripts\\run_linux.sh"], tmp_path) == [
        "scripts/run_linux.sh: its path names another system (linux): test other systems only through"
        " skellycam.certify (see AGENTS.md, Project Rules); add a certify check, or put 'certify-check: <name>'"
        " or 'other-systems: not applicable (<reason>)' in the first 5 lines"
    ]


def test_default_mode_checks_only_added_files(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "old_macos.py").write_text("print(1)\n", encoding="utf-8")
    git(repo, "add", "old_macos.py")
    git(repo, "commit", "-q", "-m", "add")
    (repo / "old_macos.py").write_text("print(2)\n", encoding="utf-8")
    (repo / "notes.md").write_text("text\n", encoding="utf-8")
    git(repo, "add", "old_macos.py", "notes.md")
    assert cos.added_files(repo) == ["notes.md"]
    assert cos.main(["check_other_systems.py"]) == 0
    assert "other systems: no findings (1 files)" in capsys.readouterr().out
    assert cos.main(["check_other_systems.py", "--all"]) == 1
    assert capsys.readouterr().out.startswith("old_macos.py: its path names another system (macos)")


def test_default_mode_refuses_a_new_script(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "probe.py").write_text(DARWIN_GUARD, encoding="utf-8")
    git(repo, "add", "probe.py")
    assert cos.main(["check_other_systems.py"]) == 1
    assert capsys.readouterr().out.startswith("probe.py: it has a guard for another system")


def test_file_mode_and_exit_codes(repo: Path) -> None:
    (repo / "ok.py").write_text(LAB_ONLY, encoding="utf-8")
    (repo / "run_mac.sh").write_text("echo 1\n", encoding="utf-8")
    assert cos.main(["check_other_systems.py", "ok.py", "missing_linux.py"]) == 0
    assert cos.main(["check_other_systems.py", "ok.py", "run_mac.sh"]) == 1
    with pytest.raises(SystemExit) as stop:
        cos.main(["check_other_systems.py", "--all", "ok.py"])
    assert stop.value.code == 2
