"""The kit text of this repository is the kit text that kit.toml names (decision 0001).

The tests of pull and propose against a kit checkout are in tests/test_kit_sync.py of freemocap/project.
"""

from __future__ import annotations

from pathlib import Path

import kit_sync as ks
import pytest

REPO_ROOT = Path(ks.__file__).resolve().parents[1]
P = "{" * 2 + "DEFAULT_BRANCH" + "}" * 2  # the placeholder, built so that this file has none


def test_the_kit_text_of_this_repository_matches_kit_toml() -> None:
    errors, _ = ks.check(REPO_ROOT)
    assert errors == []


def test_a_repository_with_no_kit_toml_is_not_adopted_and_passes(tmp_path: Path) -> None:
    assert ks.check(tmp_path) == ([], ["kit: not adopted (no kit.toml)"])


def test_check_reports_a_changed_unit_and_passes_a_pending_change(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("a\n<!-- kit:rule -->\nkit text\n<!-- /kit -->\nb\n", encoding="utf-8")
    (tmp_path / "kit.toml").write_text("[values]\n", encoding="utf-8")
    ks.write_state(tmp_path, "0" * 40, {"AGENTS.md#rule": ks.digest("kit text")}, {}, ks.values_digest({}))
    assert ks.check(tmp_path)[0] == []
    (tmp_path / "AGENTS.md").write_text("A\n<!-- kit:rule -->\nkit text\n<!-- /kit -->\n", encoding="utf-8")
    assert ks.check(tmp_path)[0] == [], "the text outside the block is repo-owned"
    (tmp_path / "AGENTS.md").write_text("<!-- kit:rule -->\nnew text\n<!-- /kit -->\n", encoding="utf-8")
    assert [e.split(":")[0] for e in ks.check(tmp_path)[0]] == ["AGENTS.md#rule"]
    ks.write_state(tmp_path, "0" * 40, {"AGENTS.md#rule": ks.digest("kit text")}, {"AGENTS.md#rule": ks.digest("new text")}, ks.values_digest({}))
    assert ks.check(tmp_path)[0] == []
    config = (tmp_path / "kit.toml").read_text(encoding="utf-8")
    (tmp_path / "kit.toml").write_text(config.replace("[values]\n", '[values]\nAREAS = "x"\n'), encoding="utf-8")
    assert [e.split(":")[0] for e in ks.check(tmp_path)[0]] == ["kit"], "a value that pull did not fill in"


def test_write_state_keeps_the_text_above_the_kit_table(tmp_path: Path) -> None:
    (tmp_path / "kit.toml").write_text("# mine\n[values]\nA = \"1\"\n", encoding="utf-8")
    ks.write_state(tmp_path, "1" * 40, {"x": "a"}, {}, "v")
    ks.write_state(tmp_path, "2" * 40, {"x": "b"}, {"x": "c"}, "v")
    text = (tmp_path / "kit.toml").read_text(encoding="utf-8")
    assert text.startswith("# mine\n[values]\nA = \"1\"\n\n" + ks.STATE_HEADER)
    config = ks.load_config(tmp_path)
    assert config["kit"] == {"commit": "2" * 40, "values": "v", "hashes": {"x": "b"}, "pending": {"x": "c"}}


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("<!-- kit:a -->\n<!-- kit:b -->\n<!-- /kit -->\n", "blocks do not nest"),
        ("<!-- /kit -->\n", "closes no block"),
        ("# kit:a\n", "has no end marker"),
        ("<!-- kit:a -->\n<!-- /kit -->\n# kit:a\n# /kit\n", "a second block"),
    ],
)
def test_bad_markers_are_refused(text: str, error: str) -> None:
    with pytest.raises(ks.KitError, match=error):
        ks.blocks(text, "f")


def test_a_block_keeps_the_text_around_it_and_gets_lf_line_ends() -> None:
    unit = ks.Unit("f", "bootstrap/f", "a")
    text = "x\r\n  <!-- kit:a -->\r\nold\r\n  <!-- /kit -->\r\ny\r\n"
    assert ks.unit_text(text, unit, "f") == "old"
    assert ks.put_unit(text, unit, "new\nlines", "f") == "x\n  <!-- kit:a -->\nnew\nlines\n  <!-- /kit -->\ny\n"


def test_unfill_takes_the_placeholder_of_the_kit_line_and_refuses_a_new_value() -> None:
    unfill = ks.Unfill({"DEFAULT_BRANCH": "main"})
    kit = f"Open each PR against `{P}`.\nThe main rule."
    edited = "Open each PR against `main`, as a draft.\nThe main rule."
    assert unfill.text(kit, edited, "u")[0] == f"Open each PR against `{P}`, as a draft.\nThe main rule."
    with pytest.raises(ks.KitError, match="give --fill NAME or --literal NAME"):
        unfill.text(kit, edited + "\nA new line about main.", "u")
    flags = ks.Unfill({"DEFAULT_BRANCH": "main"}, literal_names=frozenset({"DEFAULT_BRANCH"}))
    assert flags.text(kit, edited + "\nA new line about main.", "u")[0].endswith("A new line about main.")


def test_a_value_is_a_whole_token() -> None:
    unfill = ks.Unfill({"DEFAULT_BRANCH": "main"})
    assert unfill.text("", "the domain, main.py and main-branch", "u")[0] == "the domain, main.py and main-branch"
