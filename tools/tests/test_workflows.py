"""The rules of the CI workflows that the user decided (ADR-S1DJ; the form: ADR-C47T).

- One uv version (Q854): each `astral-sh/setup-uv` step of each workflow pins the uv version of
  `doc-checks.yml`. That file is kit text ("The same uv in each repo"), so it is the one source. The
  specs and the Active entries of the decision log name no other uv version.
- The push runs (Q915 item 4; ADR-PA3A for `test.yml`): `test.yml`, `capture.yml`, `recorder.yml`,
  `player.yml` and `ring-arm64.yml` run on each push to `dom/integration`.
- The type check of the UI test code (Q897): the job `frontend-typecheck` of `test.yml` also runs
  `npx tsc -p tsconfig.tests.json --noEmit`. `skellycam-ui/tsconfig.tests.json` extends the root
  `tsconfig.json`, includes `src` and excludes nothing, so it checks the test folders that the root
  file leaves out.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"
UV_STEP = re.compile(r'uses: astral-sh/setup-uv@\S+[^\n]*\n\s+with:\n\s+version: "([^"]+)"')
UV_IN_TEXT = re.compile(r"\buv\s+`?(\d+\.\d+\.\d+)")


def kit_uv() -> str:
    pins = UV_STEP.findall((WORKFLOWS / "doc-checks.yml").read_text(encoding="utf-8"))
    assert len(pins) == 1
    return pins[0]


def active_entries() -> list[Path]:
    index = (REPO / "decisions" / "README.md").read_text(encoding="utf-8")
    active = index.split("### Active", 1)[1].split("### Proposed", 1)[0]
    return [REPO / "decisions" / link for link in re.findall(r"\]\((entries/[^)]+\.md)\)", active)]


@pytest.mark.parametrize("workflow", sorted(p.name for p in WORKFLOWS.glob("*.yml")))
def test_each_uv_step_pins_the_uv_of_doc_checks(workflow: str) -> None:
    text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    pins = UV_STEP.findall(text)
    assert len(pins) == text.count("astral-sh/setup-uv@"), f"{workflow}: a setup-uv step with no version"
    assert set(pins) <= {kit_uv()}


def test_the_specs_and_the_active_entries_name_only_that_uv() -> None:
    files = sorted((REPO / "specs").glob("*.md")) + active_entries()
    named = {
        f"{path.relative_to(REPO).as_posix()}: uv {version}"
        for path in files
        for version in UV_IN_TEXT.findall(path.read_text(encoding="utf-8"))
        if version != kit_uv()
    }
    assert not named


@pytest.mark.parametrize("workflow", ["test.yml", "capture.yml", "recorder.yml", "player.yml", "ring-arm64.yml"])
def test_the_workflow_runs_on_each_push_to_dom_integration(workflow: str) -> None:
    text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    branches = re.search(r"^  push:\n    branches: \[([^\]]*)\]", text, re.MULTILINE)
    assert branches, f"{workflow}: no push branches"
    assert "dom/integration" in [b.strip() for b in branches.group(1).split(",")]


def test_the_ui_test_code_has_a_type_check() -> None:
    config = json.loads((REPO / "skellycam-ui" / "tsconfig.tests.json").read_text(encoding="utf-8"))
    assert config["extends"] == "./tsconfig.json"
    assert "src" in config["include"]
    assert config["exclude"] == []
    job = (WORKFLOWS / "test.yml").read_text(encoding="utf-8").split("  frontend-typecheck:", 1)[1]
    assert "run: npx tsc -p tsconfig.tests.json --noEmit" in job
