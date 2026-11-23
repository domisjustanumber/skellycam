"""No commit adds a script for a person to run on another system (decisions VV4Q and K3BX).

You can test only on the system that you work on. Each other system is reached only through
``skellycam.certify(level)``. The product folders, the tests and the CI workflows are exempt. A
comment marker in the first lines declares a valid exception. A ``certify-check`` name must be a
check name of ``specs/certify.md``, in each mode. The pre-commit hook runs the tool on the files
that a commit adds.
"""

from __future__ import annotations

import codecs
import subprocess
from pathlib import Path

import check_other_systems as cos
import pytest

REPO_ROOT = Path(cos.__file__).resolve().parents[1]

DARWIN_GUARD = 'import sys\nif sys.platform == "darwin":\n    print(1)\n'
LINUX_PREFIX = 'import sys\nif sys.platform.startswith("linux"):\n    print(1)\n'
LAB_GUARD = 'import sys\nif sys.platform != "win32":\n    raise SystemExit("Windows only")\n'
LAB_ONLY = 'import sys\nif sys.platform == "win32":\n    print(1)\n'
SPEC = "Checks: `system:disk`, `detect`, `<label>:usb3-trial`, `<label>:rate:<w>x<h>@60`, `record-only`.\n"
REFUSAL_TAIL = (
    ": test other systems only through skellycam.certify (see AGENTS.md, Project Rules); add a certify"
    " check, or put the comment 'certify-check: <name>' or 'other-systems: not applicable (<reason>)' in"
    " the first 5 lines"
)


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


def commit(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    git(root, "add", *files)
    git(root, "commit", "-q", "-m", "add")


def test_repository_has_no_manual_script_for_another_system() -> None:
    assert cos.check(cos.tracked_files(REPO_ROOT), REPO_ROOT) == []


def test_the_pre_commit_hook_runs_the_tool_on_added_files() -> None:
    config = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    hook = config.split("- id: other-systems", 1)[1].split("- id:", 1)[0]
    assert "entry: uv run python tools/check_other_systems.py\n" in hook
    assert "pass_filenames: false" in hook


@pytest.mark.parametrize(
    "guard",
    [
        'sys.platform == "darwin"',
        "sys.platform != 'linux'",
        'sys.platform.startswith("linux")',
        'sys.platform in ("win32", "darwin")',
        'sys.platform not in ["linux"]',
        'platform.system() == "Darwin"',
        'platform.system() != "Linux"',
    ],
)
def test_a_guard_for_another_system_is_refused(tmp_path: Path, guard: str) -> None:
    text = f"import platform, sys\nif {guard}:\n    print(1)\n"
    assert refused(tmp_path, {"decisions/scripts/probe.py": text}) == ["decisions/scripts/probe.py"]


@pytest.mark.parametrize(
    "guard",
    [
        'sys.platform == "win32"',
        'sys.platform != "win32"',
        'sys.platform.startswith("win")',
        'not sys.platform.startswith("win")',
        'sys.platform in ("win32",)',
        'sys.platform not in ["win32"]',
        'platform.system() == "Windows"',
        'platform.system() != "Windows"',
    ],
)
def test_a_guard_for_the_lab_passes(tmp_path: Path, guard: str) -> None:
    text = f"import platform, sys\nif {guard}:\n    raise SystemExit('Windows only')\n"
    assert refused(tmp_path, {"decisions/scripts/probe.py": text}) == []


def test_the_refusal_names_the_guard(tmp_path: Path) -> None:
    (tmp_path / "probe.py").write_text(LINUX_PREFIX, encoding="utf-8")
    assert cos.check(["probe.py"], tmp_path) == [
        "probe.py: it has a guard for another system (sys.platform startswith 'linux')" + REFUSAL_TAIL
    ]


def test_a_guard_in_a_shell_script_is_not_read(tmp_path: Path) -> None:
    assert refused(tmp_path, {"scripts/probe.sh": DARWIN_GUARD}) == []


@pytest.mark.parametrize(
    "name",
    [
        "scripts/run_macos.py",
        "scripts/mac/run.sh",
        "research/Linux-probe.ps1",
        "x/run-suite-mac.command",
        "x/darwin_probe.py",
        "x/run_osx.bash",
        "x/MACOS.ZSH",
    ],
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
    [
        "# certify-check: system:disk",
        "// certify-check: <label>:usb3-trial",
        "# certify-check: <label>:rate:<w>x<h>@60",
        "# certify-check: detect",
        "  # other-systems: not applicable (it only reads a report)",
    ],
)
def test_a_comment_marker_in_the_first_lines_passes(tmp_path: Path, marker: str) -> None:
    text = "#!/usr/bin/env python3\n" + "\n" * 3 + marker + "\n" + DARWIN_GUARD
    assert refused(tmp_path, {"specs/certify.md": SPEC, "scripts/run_macos.py": text}) == []


@pytest.mark.parametrize(
    "name",
    [
        "system:disks",  # not in the spec
        "cam.media-foundation.046d-085c.0:usb3-trial",  # a filled-in name of a template
        "<label>:rate:1920x1080@60",
        "record-only",  # a code span of the spec, but not a check name
    ],
)
def test_a_certify_check_name_that_is_not_in_the_spec_is_refused(tmp_path: Path, name: str) -> None:
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "certify.md").write_text(SPEC, encoding="utf-8")
    (tmp_path / "probe.py").write_text(f"# certify-check: {name}\nprint(1)\n", encoding="utf-8")
    assert cos.check(["probe.py"], tmp_path) == [
        f"probe.py: its certify-check name {name!r} is not a check name of specs/certify.md: " + cos.ADD_CHECK_FIRST
    ]


def test_a_missing_spec_refuses_each_certify_check_marker(tmp_path: Path) -> None:
    (tmp_path / "probe.py").write_text("# certify-check: system:disk\nprint(1)\n", encoding="utf-8")
    (tmp_path / "lab.py").write_text("print(1)\n", encoding="utf-8")
    assert cos.check(["probe.py", "lab.py"], tmp_path) == [
        "probe.py: its certify-check name 'system:disk' is not a check name of specs/certify.md"
        " (the file is missing): " + cos.ADD_CHECK_FIRST
    ]


def test_the_pointer_to_the_process_is_one_constant() -> None:
    assert "skill verify-on-other-systems" in cos.ADD_CHECK_FIRST
    assert "report-format.md" in cos.ADD_CHECK_FIRST


def test_the_real_spec_holds_the_names_of_the_catalogue() -> None:
    names = cos.spec_names(REPO_ROOT)
    assert names is not None
    assert {"detect", "system:disk", "<label>:usb3-trial", "session:exit", "<label>:detect:mjpg-mode"} <= names
    assert not {"record-only", "046d:085c", "cam.media-foundation.046d-085c.0"} & names


def test_all_mode_refuses_an_unknown_name_in_a_tracked_script(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    commit(repo, {"specs/certify.md": SPEC, "ok.py": "# certify-check: system:disk\n", "bad.py": "# certify-check: x:y\n"})
    assert cos.main(["check_other_systems.py", "--all"]) == 1
    assert capsys.readouterr().out.startswith("bad.py: its certify-check name 'x:y' is not a check name")


@pytest.mark.parametrize(
    "text",
    [
        "\n" * 5 + "# certify-check: cam0:open\n" + DARWIN_GUARD,
        "# other-systems: not applicable ()\n" + DARWIN_GUARD,
        "# other-systems: not applicable\n" + DARWIN_GUARD,
        "# certify-check:\n" + DARWIN_GUARD,
        'X = "certify-check: cam0:open"\n' + DARWIN_GUARD,
        "print('# other-systems: not applicable (lab only)')\n" + DARWIN_GUARD,
    ],
)
def test_a_late_empty_or_string_marker_does_not_pass(tmp_path: Path, text: str) -> None:
    assert refused(tmp_path, {"scripts/probe.py": text}) == ["scripts/probe.py"]


@pytest.mark.parametrize("bom", [codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE])
def test_a_utf16_powershell_marker_passes(tmp_path: Path, bom: bytes) -> None:
    encoding = "utf-16-le" if bom == codecs.BOM_UTF16_LE else "utf-16-be"
    (tmp_path / "run_mac.ps1").write_bytes(bom + "# other-systems: not applicable (lab only)\n".encode(encoding))
    (tmp_path / "run_linux.ps1").write_bytes(bom + "Write-Output 1\n".encode(encoding))
    assert [line.split(":")[0] for line in cos.check(["run_mac.ps1", "run_linux.ps1"], tmp_path)] == ["run_linux.ps1"]


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
    assert cos.LAB_SYSTEMS == ("Windows",)
    assert refused(tmp_path, {"scripts/probe.py": DARWIN_GUARD}, lab=("darwin",)) == []


def test_windows_separators_and_the_refusal_line(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run_linux.sh").write_text("echo 1\n", encoding="utf-8")
    assert cos.check(["scripts\\run_linux.sh"], tmp_path) == [
        "scripts/run_linux.sh: its path names another system (linux)" + REFUSAL_TAIL
    ]


def test_default_mode_checks_only_added_files(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    commit(repo, {"old_macos.py": "print(1)\n"})
    (repo / "old_macos.py").write_text("print(2)\n", encoding="utf-8")
    (repo / "notes.md").write_text("text\n", encoding="utf-8")
    git(repo, "add", "old_macos.py", "notes.md")
    assert cos.added_files(repo) == ["notes.md"]
    assert cos.main(["check_other_systems.py"]) == 0
    assert "other systems: no findings (1 files, 0 scripts in scope)" in capsys.readouterr().out
    assert cos.main(["check_other_systems.py", "--all"]) == 1
    assert capsys.readouterr().out.startswith("old_macos.py: its path names another system (macos)")


def test_default_mode_refuses_a_new_script(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "probe.py").write_text(DARWIN_GUARD, encoding="utf-8")
    git(repo, "add", "probe.py")
    assert cos.main(["check_other_systems.py"]) == 1
    assert capsys.readouterr().out.startswith("probe.py: it has a guard for another system")


def test_a_moved_script_is_a_new_file(repo: Path) -> None:
    commit(repo, {"probe.py": "import sys\n" + "print('a long body that git can match')\n" * 20})
    git(repo, "mv", "probe.py", "probe_macos.py")
    assert cos.added_files(repo) == ["probe_macos.py"]
    assert cos.main(["check_other_systems.py"]) == 1


def test_a_delete_plus_a_similar_add_is_a_new_file(repo: Path) -> None:
    body = "import sys\n" + "print('a long body that git can match')\n" * 20
    commit(repo, {"probe.py": body})
    git(repo, "rm", "-q", "probe.py")
    (repo / "run_on_mac.py").write_text(body + "print(1)\n", encoding="utf-8")
    git(repo, "add", "run_on_mac.py")
    assert cos.added_files(repo) == ["run_on_mac.py"]
    assert cos.main(["check_other_systems.py"]) == 1


def test_a_run_from_a_subfolder_checks_the_whole_repository(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    commit(repo, {"sub/notes.md": "text\n", "tracked_linux.sh": "echo 1\n"})
    (repo / "run_on_mac.py").write_text("print(1)\n", encoding="utf-8")
    git(repo, "add", "run_on_mac.py")
    monkeypatch.chdir(repo / "sub")
    assert cos.main(["check_other_systems.py"]) == 1
    assert capsys.readouterr().out.startswith("run_on_mac.py: its path names another system (mac)")
    assert cos.main(["check_other_systems.py", "--all"]) == 1
    assert capsys.readouterr().out.startswith("run_on_mac.py:")
    assert cos.main(["check_other_systems.py", "../tracked_linux.sh"]) == 1
    assert capsys.readouterr().out.startswith("tracked_linux.sh: its path names another system (linux)")


def test_outside_a_git_repository_exits_2_with_one_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    monkeypatch.chdir(tmp_path)
    assert cos.main(["check_other_systems.py"]) == 2
    out = capsys.readouterr().out
    assert out.startswith("other systems: cannot run git here: ")
    assert out.count("\n") == 1


def test_file_mode_and_exit_codes(repo: Path) -> None:
    (repo / "ok.py").write_text(LAB_ONLY, encoding="utf-8")
    (repo / "run_mac.sh").write_text("echo 1\n", encoding="utf-8")
    assert cos.main(["check_other_systems.py", "ok.py", "missing_linux.py"]) == 0
    assert cos.main(["check_other_systems.py", "ok.py", "run_mac.sh"]) == 1
    with pytest.raises(SystemExit) as stop:
        cos.main(["check_other_systems.py", "--all", "ok.py"])
    assert stop.value.code == 2
