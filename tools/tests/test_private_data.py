"""No tracked file contains private data (decision 0001).

The test strings are built from parts, so that this file does not contain the patterns that it checks.
"""

from __future__ import annotations

from pathlib import Path

import check_private_data as cpd
import pytest

REPO_ROOT = Path(cpd.__file__).resolve().parents[1]

USER = "al" + "ice"


def kinds(text: str, terms: list[str] | None = None) -> list[str]:
    return [f.kind for f in cpd.scan_text("doc.md", text, terms or [])]


def test_repository_has_no_private_data() -> None:
    assert [str(f) for f in cpd.check(REPO_ROOT)] == []


@pytest.mark.parametrize(
    "text",
    [
        "C:" + "\\Users\\" + USER + "\\GitHub\\repo",
        "c:" + "/Users/" + USER + "/GitHub",
        "/ho" + "me/" + USER + "/repo",
        "/ho" + "me/" + "user" + "name/repo",
        "/Us" + "ers/" + USER.title() + "/repo",
    ],
)
def test_user_paths_are_reported(text: str) -> None:
    assert kinds(text) == ["user path"]


@pytest.mark.parametrize(
    "text",
    [
        "C:" + "\\Users\\<you>\\GitHub",
        "/ho" + "me/$USER/repo",
        '"path": "/ho' + 'me/user/recordings"',
        "C:" + "\\Users\\%USERNAME%",
        "../other-repo/notes",
    ],
)
def test_placeholders_and_relative_paths_pass(text: str) -> None:
    assert kinds(text) == []


def test_email_addresses_are_reported_except_the_allowlist() -> None:
    at = "@"
    assert kinds(USER + at + "gmail.com") == ["email address"]
    assert kinds("a" + at + "example.com b" + at + "x.invalid") == []
    assert kinds("123+" + USER + at + "users.noreply.github.com") == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("192." + "168.1.20", ["private IP address"]),
        ("10." + "0.0.5", ["private IP address"]),
        ("172." + "20.3.4", ["private IP address"]),
        ("172." + "32.3.4", []),
        ("onnxruntime 1.20.1", []),
        ("TensorRT 10." + "0.1.6.post1", []),
        ("v10." + "0.0.5", []),
    ],
)
def test_private_ip_addresses(text: str, expected: list[str]) -> None:
    assert kinds(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "hf" + "_" + "a" * 34,
        "gh" + "p_" + "B" * 36,
        "AK" + "IA" + "ABCDEFGHIJKLMNOP",
        "sk" + "-ant-" + "x" * 30,
        "-----BEGIN " + "RSA PRIVATE" + " KEY-----",
    ],
)
def test_tokens_are_reported(text: str) -> None:
    assert kinds(text) == ["token"]


def test_private_terms_are_reported_without_the_term(tmp_path: Path) -> None:
    findings = cpd.scan_text("doc.md", "run on " + "Gera" + "ld today", ["gerald"])
    assert [str(f) for f in findings] == ["doc.md:1: private term: <from .private-terms>"]


def test_private_terms_file_is_read_without_comments(tmp_path: Path) -> None:
    (tmp_path / cpd.PRIVATE_TERMS).write_text("# hosts\nmyhost\n\n  other  \n", encoding="utf-8")
    assert cpd.private_terms(tmp_path) == ["myhost", "other"]


def test_private_terms_file_is_ignored_by_git() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert cpd.PRIVATE_TERMS in gitignore


def test_files_mode_checks_only_the_given_files_and_skips_lock_and_illustrator_files(
    tmp_path: Path,
) -> None:
    finding = USER + "@" + "gmail.com\n"
    for name in ("a.md", "package-lock.json", "logo.ai"):
        (tmp_path / name).write_text(finding, encoding="utf-8")
    (tmp_path / "b.md").write_text("clean\n", encoding="utf-8")
    assert cpd.check(tmp_path, ["b.md", "package-lock.json", "logo.ai", "gone.md"]) == []
    assert [f.path for f in cpd.check(tmp_path, ["a.md", "b.md"])] == ["a.md"]
    assert cpd.main(["check_private_data.py", "--files"]) == 0


def test_an_allowed_line_passes_only_while_its_text_is_unchanged(monkeypatch) -> None:
    """An allow entry is a path, a line number and the SHA-256 of the exact text of that line, with a reason
    (decision 0001). A finding on that line passes only when all three match: an edited line, the same text
    on another line, or the same line in another file is checked again."""
    import hashlib

    line = "// by " + USER + "@" + "corp-mail.org"
    digest = hashlib.sha256(line.encode("utf-8")).hexdigest()
    monkeypatch.setattr(cpd, "ALLOWED_LINES", {("ui/credit.tsx", 1): (digest, "upstream author credit")})
    assert cpd.scan_text("ui/credit.tsx", line + "\nok\n", []) == []
    assert [f.line for f in cpd.scan_text("ui/credit.tsx", "ok\n" + line + "\n", [])] == [2]
    assert [f.kind for f in cpd.scan_text("ui/other.tsx", line + "\n", [])] == ["email address"]
    assert [f.kind for f in cpd.scan_text("ui/credit.tsx", line + " edited\n", [])] == ["email address"]


def test_each_allowed_line_has_a_hash_and_a_reason() -> None:
    for (path, number), (digest, reason) in cpd.ALLOWED_LINES.items():
        assert number >= 1 and len(digest) == 64 and int(digest, 16) >= 0 and reason, path
