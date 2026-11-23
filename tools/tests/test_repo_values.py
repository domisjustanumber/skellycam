"""The values of this repository in kit.toml that a decision of this repository fixes.

The kit tests do not check them, because each repository has its own values.
"""

from __future__ import annotations

from pathlib import Path

import check_decision_log as cdl
import check_other_systems as cos
import pytest

REPO_ROOT = Path(cos.__file__).resolve().parents[1]


def test_the_pr_branch_is_upstream_development() -> None:
    """Pull requests go against upstream `development` (decision EQY4): an entry there wins a collision."""
    assert cdl.TARGET_BRANCH == "development"


def test_the_index_limit_is_24000() -> None:
    """The index limit is 24,000 characters (decisions N2NH and XT31)."""
    assert cdl.INDEX_LIMIT == 24_000


def test_the_values_of_the_other_systems_check() -> None:
    """The product folders, the CI, the certify spec and the self-test (decisions VV4Q, K3BX, C307, K9B7)."""
    assert cos.EXEMPT_PATHS == ("skellycam/", "skellycam-ui/", "skellycam-docs/", ".github/")
    assert cos.CERTIFY_SPEC == "specs/certify.md"
    assert cos.PURPOSE_ADVICE.endswith("test other systems only through skellycam.certify (see AGENTS.md, Project Rules)")
    assert cos.ADD_CHECK_FIRST == (
        "the check must be in specs/certify.md first: follow sections 5.5 (How a package adds a check) and 5.6"
        " (When a check can exist, and its level) of report-format.md of the skellycertify repository (skill"
        " verify-on-other-systems)"
    )


@pytest.mark.parametrize(
    "name",
    ["skellycam/core/camera/capture/macos/source.py", "skellycam-ui/scripts/linux.sh", "skellycam-docs/linux.py"],
)
def test_the_product_folders_of_this_repository_are_exempt(name: str) -> None:
    assert not cos.in_scope(name)


def test_the_real_spec_holds_check_names_only() -> None:
    names = cos.spec_names(REPO_ROOT)
    assert names is not None
    real = {"detect", "system:disk", "<label>:usb3-trial", "session:exit", "report:rules", "pipeline:gate",
            "<model>:gate:rate", "<label>:detect:mjpg-mode", "probe:usb-alt", "release:<label>", "<name>:exit"}
    assert real <= names
    parts = {"vvvv:pppp", "vvvv:dddd", "a1-cmio-native:exposure", "clock:base", "rate:1280x720@60", "gate:mode"}
    forms = {"system:<check>", "<label>:<name>", "<label>:<group>:<condition>", "<group>:<condition>"}
    assert not (parts | forms | {"record-only", "046d:085c", "cam.media-foundation.046d-085c.0"}) & names
