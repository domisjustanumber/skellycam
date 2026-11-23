"""The values of this repository in kit.toml that a decision of this repository fixes.

The kit tests do not check them, because each repository has its own values.
"""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

import check_camera_media as ccm
import check_decision_log as cdl
import check_links as cl
import check_other_systems as cos
import check_private_data as cpd
import pytest

REPO_ROOT = Path(cos.__file__).resolve().parents[1]
# Each table of kit.toml that a tool reads. A misspelt or a missing table gives the kit defaults with no error.
TOOL_TABLES = ("check_decision_log", "check_private_data", "check_links", "check_camera_media", "check_other_systems")


def test_kit_toml_has_each_table_that_a_tool_reads() -> None:
    with (REPO_ROOT / "kit.toml").open("rb") as file:
        config = tomllib.load(file)
    assert {"sync", "values", "kit", *TOOL_TABLES} == set(config)


def test_there_are_no_golden_paths() -> None:
    """skellycam has no golden reference files (decision G5S0), so the camera media check allows none."""
    assert ccm.GOLDEN_PATHS == ()


def test_the_allow_lists_of_the_private_data_check() -> None:
    """The contact address of the project and the two reviewed lines (decision JMS0, item I). The test
    compares the SHA-256 of the address, so that it does not hold the address."""
    others = sorted(a for a in cpd.ALLOWED_EMAILS if a != "noreply@anthropic.com")
    assert len(cpd.ALLOWED_EMAILS) == 2
    assert hashlib.sha256("\n".join(others).encode()).hexdigest() == (
        "f8ef582e5bb914d184f1d3971de7eb529a9746152ae42795914fe7de11480516"
    )
    assert cpd.ALLOWED_LINES == {
        ("skellycam-ui/src/hooks/floatingOnboarding.tsx", 1):
            ("70d514cd447c3acfa67678f424813f7219a6820a0d1bb02bd319800e482e93b0", "upstream author credit"),
        ("skellycam-ui/src/hooks/useDraggableTooltips.tsx", 1):
            ("2b9a3455ee945850201dde0ba48d187a94f492d5fdf3964dfe818d1b3252ee4e", "upstream author credit"),
    }


def test_the_docs_of_the_link_check() -> None:
    assert (cl.DOC_PATHS, cl.SKIPPED_FOLDERS) == ((".claude/skills/", "specs/", "notes/"), ())


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
