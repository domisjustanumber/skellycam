"""The values of this repository in kit.toml that a decision of this repository fixes.

The kit tests do not check them, because each repository has its own values.
"""

from __future__ import annotations

import check_decision_log as cdl


def test_the_pr_branch_is_upstream_development() -> None:
    """Pull requests go against upstream `development` (decision EQY4): an entry there wins a collision."""
    assert cdl.TARGET_BRANCH == "development"


def test_the_index_limit_is_24000() -> None:
    """The index limit is 24,000 characters (decisions N2NH and XT31)."""
    assert cdl.INDEX_LIMIT == 24_000
