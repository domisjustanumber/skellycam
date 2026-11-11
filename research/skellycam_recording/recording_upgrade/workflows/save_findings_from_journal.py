"""Save FINDINGS.md text returned by workflow agents (the harness blocks subagent writes to FINDINGS.md).

Usage: python save_findings_from_journal.py <journal.jsonl> [--dry-run]
An agent's label must end in ':<topic>' (e.g. 'findings:jpeg_passthrough', 'revise:licensing') and its
structured result must contain 'findings_md'. An existing FINDINGS.md is backed up once per run as
FINDINGS.prev_<n>.md before being replaced.
"""
import json
import pathlib
import sys

RESULTS = pathlib.Path(__file__).resolve().parent.parent / "results"


def main() -> None:
    journal = pathlib.Path(sys.argv[1])
    dry = "--dry-run" in sys.argv
    labels: dict[str, str] = {}
    latest: dict[str, str] = {}
    for line in journal.read_text(encoding="utf-8").splitlines():
        try:
            j = json.loads(line)
        except json.JSONDecodeError:
            continue
        if j.get("type") == "started":
            labels[j["key"]] = j.get("label", "")
        elif j.get("type") == "result":
            r = j.get("result")
            if isinstance(r, str):
                try:
                    r = json.loads(r)
                except json.JSONDecodeError:
                    continue
            if isinstance(r, dict) and isinstance(r.get("findings_md"), str) and r["findings_md"].strip():
                label = labels.get(j["key"], "")
                topic = label.rsplit(":", 1)[-1]
                if topic:
                    latest[topic] = r["findings_md"]
    for topic, body in latest.items():
        folder = RESULTS / topic
        out = folder / "FINDINGS.md"
        print(f"{topic}: {len(body)} chars -> {out}" + (" (dry run)" if dry else ""))
        if dry:
            continue
        folder.mkdir(parents=True, exist_ok=True)
        if out.exists():
            if out.read_text(encoding="utf-8") == body:
                continue
            n = 1
            while (folder / f"FINDINGS.prev_{n}.md").exists():
                n += 1
            out.rename(folder / f"FINDINGS.prev_{n}.md")
        out.write_text(body if body.endswith("\n") else body + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
