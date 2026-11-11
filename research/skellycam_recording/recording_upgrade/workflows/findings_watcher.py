"""Poll the workflow journal; when an agent returns FINDINGS.md text because Write was blocked, save it."""
import json, re, time, pathlib, sys

J = pathlib.Path(r"C:/Users/Dom/.claude/projects/c--Users-Dom-GitHub-freemocap-skellycam/106dc0c8-f977-4082-9d8d-367e9a9f721d/subagents/workflows/wf_2e122ed0-a3f/journal.jsonl")
ROOT = pathlib.Path(r"C:/Users/Dom/GitHub/freemocap/skellycam")
LOG = pathlib.Path(__file__).with_name("findings_watcher.log")
seen = set()

def log(m):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S ") + m + "\n")

while True:
    try:
        lines = J.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        log(f"read error {e}"); time.sleep(20); continue
    done = False
    for i, l in enumerate(lines):
        if i in seen:
            continue
        seen.add(i)
        try:
            j = json.loads(l)
        except Exception:
            continue
        if j.get("type") == "completed" or j.get("type") == "finished":
            done = True
        r = j.get("result", j.get("value"))
        if not isinstance(r, str) or "FINDINGS.md" not in r or "block" not in r[:600].lower():
            continue
        m = re.search(r"results/(\w+)/FINDINGS\.md", r)
        if not m:
            log(f"line {i}: blocked text without topic path"); continue
        topic = m.group(1)
        mk = re.search(r"^=+ *FINDINGS\.md CONTENT *=+\s*$", r, re.M)
        if mk:
            body = r[mk.end():].lstrip("\n")
        else:
            h = re.search(r"^# .+$", r, re.M)
            if not h:
                log(f"line {i}: {topic}: no content marker or heading"); continue
            body = r[h.start():]
        out = ROOT / "research/skellycam_recording/recording_upgrade/results" / topic / "FINDINGS.md"
        if out.exists():
            # keep a copy rather than overwrite (a revise agent may have edited it)
            out = out.with_name(f"FINDINGS.blocked_line{i}.md")
        out.write_text(body, encoding="utf-8")
        log(f"line {i}: saved {out} ({len(body)} chars)")
    if done:
        log("workflow finished; exiting"); break
    time.sleep(20)
