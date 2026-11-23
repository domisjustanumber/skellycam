"""Each script that names or guards for a system states its purpose.

You can test only on the system that you work on. Each other system is reached only through the
self-test of the project (``SELF_TEST``). A script outside the product code that names or guards for
any system has the comment ``script-purpose: <kind> ...`` in its first lines. A ``certify-check``
name must be a check name of the spec ``CERTIFY_SPEC``. Each mode gives the same result on each
system. The product folders and the CI workflows (``EXEMPT_PATHS``) and the tests are exempt. The
pre-commit hook runs the tool on the files that a commit adds. The values come from ``kit.toml``.
Each repository tests its own values in a test of its own.
"""

from __future__ import annotations

import codecs
import subprocess
import sys
from pathlib import Path

import check_other_systems as cos
import pytest

REPO_ROOT = Path(cos.__file__).resolve().parents[1]
PLATFORMS = ("win32", "darwin", "linux")

DARWIN_GUARD = 'import sys\nif sys.platform == "darwin":\n    print(1)\n'
SPEC = "Checks: `system:disk`, `detect`, `<label>:usb3-trial`, `<label>:rate:<w>x<h>@60`, `record-only`.\n"
WORKFLOW = {".github/workflows/ring-arm64.yml": "name: ring\n"}
ADVICE = (
    ": add the comment 'script-purpose: <kind> ...' in the first 5 lines; the kinds are 'certify-check <name>',"
    " 'local-study (<what>)', 'tool (<what>)' and 'ci (<workflow>)'; test other systems only through"
    f" {cos.SELF_TEST} (see AGENTS.md, Project Rules)"
)


def write(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = root / name.replace("\\", "/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def refused(tmp_path: Path, files: dict[str, str]) -> list[str]:
    write(tmp_path, {cos.CERTIFY_SPEC: SPEC, **WORKFLOW, **files})
    return [line.split(":")[0] for line in cos.check(list(files), tmp_path)]


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
    write(root, files)
    git(root, "add", *files)
    git(root, "commit", "-q", "-m", "add")


def test_the_repository_has_no_finding() -> None:
    assert cos.check(cos.tracked_files(REPO_ROOT), REPO_ROOT) == []


def test_the_pre_commit_hook_runs_the_tool_on_added_files() -> None:
    config = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    hook = config.split("- id: other-systems", 1)[1].split("- id:", 1)[0]
    assert "entry: uv run python tools/check_other_systems.py\n" in hook
    assert "pass_filenames: false" in hook


@pytest.mark.parametrize(
    "guard",
    [
        'sys.platform == "win32"',
        "sys.platform != 'darwin'",
        'sys.platform.startswith("linux")',
        'not sys.platform.startswith("win")',
        'sys.platform in ("win32", "darwin")',
        'sys.platform not in ["linux"]',
        'platform.system() == "Windows"',
        'platform.system() != "Darwin"',
        'platform.system() in ("Linux",)',
    ],
)
def test_each_guard_is_a_signal(tmp_path: Path, guard: str) -> None:
    text = f"import platform, sys\nif {guard}:\n    print(1)\n"
    assert refused(tmp_path, {"decisions/scripts/probe.py": text}) == ["decisions/scripts/probe.py"]


@pytest.mark.parametrize(
    "name",
    [
        "x/run_windows.ps1",
        "x/win/probe.py",
        "x/WIN32-probe.sh",
        "scripts/run_macos.py",
        "scripts/mac/run.sh",
        "x/run-suite-mac.command",
        "x/darwin_probe.py",
        "x/run_osx.bash",
        "research/Linux-probe.ps1",
        "x/LINUX.ZSH",
    ],
)
def test_each_system_name_in_a_path_is_a_signal(tmp_path: Path, name: str) -> None:
    assert refused(tmp_path, {name: "print(1)\n"}) == [name]


@pytest.mark.parametrize(
    "name", ["scripts/machine.py", "scripts/emacs.py", "x/window.py", "x/winner.py", "x/twin.py", "notes/linux.md"]
)
def test_a_similar_name_a_document_or_no_signal_passes(tmp_path: Path, name: str) -> None:
    assert refused(tmp_path, {name: "import sys\nprint(sys.platform)\n"}) == []


def test_the_refusal_line_names_the_signal(tmp_path: Path) -> None:
    write(tmp_path, {"scripts/run_linux.sh": "echo 1\n", "probe.py": 'import sys\nif sys.platform.startswith("win"):\n  pass\n'})
    assert cos.check(["scripts\\run_linux.sh", "probe.py"], tmp_path) == [
        "probe.py: it has a system guard (sys.platform startswith \"win\")" + ADVICE,
        "scripts/run_linux.sh: its path names a system (Linux)" + ADVICE,
    ]


def test_a_guard_in_a_shell_script_is_not_read(tmp_path: Path) -> None:
    assert refused(tmp_path, {"scripts/probe.sh": DARWIN_GUARD}) == []


@pytest.mark.parametrize(
    "purpose",
    [
        "# script-purpose: certify-check system:disk",
        "// script-purpose: certify-check <label>:usb3-trial",
        "# script-purpose: certify-check <label>:rate:<w>x<h>@60",
        "# script-purpose: certify-check detect",
        "  # script-purpose: local-study (frame timing of the cameras of this system)",
        "# script-purpose: tool (formats the evidence tables)",
        "# script-purpose: ci (ring-arm64.yml)",
    ],
)
def test_each_valid_kind_passes(tmp_path: Path, purpose: str) -> None:
    text = "#!/usr/bin/env python3\n" + "\n" * 3 + purpose + "\n" + DARWIN_GUARD
    assert refused(tmp_path, {"scripts/run_macos.py": text}) == []


@pytest.mark.parametrize(
    ("purpose", "reason"),
    [
        ("# script-purpose: probe (x)", "its script-purpose kind 'probe' is not one of certify-check, local-study, tool, ci"),
        ("# script-purpose:", "its script-purpose kind '' is not one of certify-check, local-study, tool, ci"),
        ("# script-purpose: local-study ()", "its script-purpose 'local-study' has no text in brackets"),
        ("# script-purpose: tool", "its script-purpose 'tool' has no text in brackets"),
        ("# script-purpose: tool formats files", "its script-purpose 'tool' has no text in brackets"),
        ("# script-purpose: ci (no-such.yml)", "its script-purpose 'ci' names no file .github/workflows/no-such.yml"),
        ("# script-purpose: ci (../workflows/ring-arm64.yml)",
         "its script-purpose 'ci' names no file .github/workflows/../workflows/ring-arm64.yml"),
    ],
)
def test_an_invalid_purpose_field_is_refused(tmp_path: Path, purpose: str, reason: str) -> None:
    write(tmp_path, {cos.CERTIFY_SPEC: SPEC, **WORKFLOW, "probe.py": purpose + "\nprint(1)\n"})
    assert cos.check(["probe.py"], tmp_path) == [f"probe.py: {reason}" + ADVICE]


@pytest.mark.parametrize(
    "name",
    [
        "system:disks",  # not in the spec
        "cam.media-foundation.046d-085c.0:usb3-trial",  # a filled-in name of a template
        "<label>:rate:1920x1080@60",
        "record-only",  # a code span of the spec, but not a check name
        "",
    ],
)
def test_a_certify_check_name_that_is_not_in_the_spec_is_refused(tmp_path: Path, name: str) -> None:
    write(tmp_path, {cos.CERTIFY_SPEC: SPEC, "probe.py": f"# script-purpose: certify-check {name}\nprint(1)\n"})
    assert cos.check(["probe.py"], tmp_path) == [
        f"probe.py: its certify-check name {name!r} is not a check name of {cos.CERTIFY_SPEC}: " + cos.ADD_CHECK_FIRST
    ]


def test_a_missing_spec_refuses_each_certify_check(tmp_path: Path) -> None:
    write(tmp_path, {"probe.py": "# script-purpose: certify-check system:disk\nprint(1)\n", "lab.py": "print(1)\n"})
    assert cos.check(["probe.py", "lab.py"], tmp_path) == [
        f"probe.py: its certify-check name 'system:disk' is not a check name of {cos.CERTIFY_SPEC}"
        " (the file is missing): " + cos.ADD_CHECK_FIRST
    ]


def test_the_pointer_to_the_process_is_one_constant() -> None:
    assert "sections 5.5 (How a package adds a check) and 5.6" in cos.ADD_CHECK_FIRST
    assert f"of {cos.CERTIFY_CONTRACT} (skill verify-on-other-systems)" in cos.ADD_CHECK_FIRST
    assert cos.ADD_CHECK_FIRST.startswith(f"the check must be in {cos.CERTIFY_SPEC} first: ")


@pytest.mark.parametrize(
    "marker", ["# certify-check: system:disk", "# other-systems: not applicable (lab only)"]
)
def test_an_old_marker_is_refused_and_named(tmp_path: Path, marker: str) -> None:
    write(tmp_path, {cos.CERTIFY_SPEC: SPEC, "run_mac.py": marker + "\nprint(1)\n"})
    assert cos.check(["run_mac.py"], tmp_path) == [
        "run_mac.py: its path names a system (macOS); its marker 'certify-check:' or 'other-systems:' is not valid now"
        + ADVICE
    ]


def test_a_purpose_field_is_checked_also_with_no_signal(tmp_path: Path) -> None:
    assert refused(tmp_path, {"plain.py": "# script-purpose: certify-check x:y\nprint(1)\n"}) == ["plain.py"]


@pytest.mark.parametrize(
    "text",
    [
        "\n" * 5 + "# script-purpose: tool (late)\n" + DARWIN_GUARD,
        "print('# script-purpose: tool (in a string)')\n" + DARWIN_GUARD,
    ],
)
def test_a_late_or_string_field_does_not_count(tmp_path: Path, text: str) -> None:
    assert refused(tmp_path, {"scripts/probe.py": text}) == ["scripts/probe.py"]


@pytest.mark.parametrize("bom", [codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE])
def test_a_utf16_powershell_field_counts(tmp_path: Path, bom: bytes) -> None:
    encoding = "utf-16-le" if bom == codecs.BOM_UTF16_LE else "utf-16-be"
    (tmp_path / "run_mac.ps1").write_bytes(bom + "# script-purpose: tool (packs the logs)\n".encode(encoding))
    (tmp_path / "run_linux.ps1").write_bytes(bom + "Write-Output 1\n".encode(encoding))
    assert [line.split(":")[0] for line in cos.check(["run_mac.ps1", "run_linux.ps1"], tmp_path)] == ["run_linux.ps1"]


@pytest.mark.parametrize(
    "name",
    [f"{prefix}scripts/macos.sh" for prefix in cos.EXEMPT_PATHS]
    + ["tools/tests/test_macos.py", "decisions/scripts/tests/test_probe.py"],
)
def test_the_product_the_tests_and_ci_are_exempt(tmp_path: Path, name: str) -> None:
    assert refused(tmp_path, {name: "# script-purpose: nonsense\n" + DARWIN_GUARD}) == []


def test_each_mode_gives_the_same_result_on_each_system(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"run_windows.py": "print(1)\n", "run_macos.py": "print(1)\n", "lab.py": DARWIN_GUARD}
    commit(repo, {"ok.py": "# script-purpose: tool (x)\n" + DARWIN_GUARD, **files})
    assert cos.main(["check_other_systems.py", "--all"]) == 1
    all_out = capsys.readouterr().out
    assert [line.split(":")[0] for line in all_out.splitlines()] == ["lab.py", "run_macos.py", "run_windows.py"]
    assert cos.main(["check_other_systems.py", *files]) == 1
    assert capsys.readouterr().out == all_out
    write(repo, {"new_linux.py": "print(1)\n"})
    git(repo, "add", "new_linux.py")
    assert cos.main(["check_other_systems.py"]) == 1
    assert capsys.readouterr().out.startswith("new_linux.py: its path names a system (Linux)")
    # git needs the real sys.platform, so the lists are read first; check() reads no git.
    tracked, added = cos.tracked_files(repo), cos.added_files(repo)
    expected = (cos.check(tracked, repo), cos.check(added, repo))
    for platform in PLATFORMS:
        with monkeypatch.context() as patch:
            patch.setattr(sys, "platform", platform)
            assert (cos.check(tracked, repo), cos.check(added, repo)) == expected


def test_default_mode_checks_only_added_files(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    commit(repo, {"old_macos.py": "print(1)\n"})
    write(repo, {"old_macos.py": "print(2)\n", "notes.md": "text\n"})
    git(repo, "add", "old_macos.py", "notes.md")
    assert cos.added_files(repo) == ["notes.md"]
    assert cos.main(["check_other_systems.py"]) == 0
    assert "other systems: no findings (1 files, 0 scripts in scope)" in capsys.readouterr().out
    assert cos.main(["check_other_systems.py", "--all"]) == 1
    assert capsys.readouterr().out.startswith("old_macos.py: its path names a system (macOS)")


def test_a_moved_script_is_a_new_file(repo: Path) -> None:
    commit(repo, {"probe.py": "import sys\n" + "print('a long body that git can match')\n" * 20})
    git(repo, "mv", "probe.py", "probe_macos.py")
    assert cos.added_files(repo) == ["probe_macos.py"]
    assert cos.main(["check_other_systems.py"]) == 1


def test_a_delete_plus_a_similar_add_is_a_new_file(repo: Path) -> None:
    body = "import sys\n" + "print('a long body that git can match')\n" * 20
    commit(repo, {"probe.py": body})
    git(repo, "rm", "-q", "probe.py")
    write(repo, {"run_on_mac.py": body + "print(1)\n"})
    git(repo, "add", "run_on_mac.py")
    assert cos.added_files(repo) == ["run_on_mac.py"]
    assert cos.main(["check_other_systems.py"]) == 1


def test_a_run_from_a_subfolder_checks_the_whole_repository(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    commit(repo, {"sub/notes.md": "text\n", "tracked_linux.sh": "echo 1\n"})
    write(repo, {"run_on_mac.py": "print(1)\n"})
    git(repo, "add", "run_on_mac.py")
    monkeypatch.chdir(repo / "sub")
    assert cos.main(["check_other_systems.py"]) == 1
    assert capsys.readouterr().out.startswith("run_on_mac.py: its path names a system (macOS)")
    assert cos.main(["check_other_systems.py", "--all"]) == 1
    assert capsys.readouterr().out.startswith("run_on_mac.py:")
    assert cos.main(["check_other_systems.py", "../tracked_linux.sh"]) == 1
    assert capsys.readouterr().out.startswith("tracked_linux.sh: its path names a system (Linux)")


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
    write(repo, {"ok.py": "print(1)\n", "run_mac.sh": "echo 1\n"})
    assert cos.main(["check_other_systems.py", "ok.py", "missing_linux.py"]) == 0
    assert cos.main(["check_other_systems.py", "ok.py", "run_mac.sh"]) == 1
    with pytest.raises(SystemExit) as stop:
        cos.main(["check_other_systems.py", "--all", "ok.py"])
    assert stop.value.code == 2
