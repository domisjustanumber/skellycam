r"""Protect the original result folders while the documented commands (which write into them) are re-run.
NOT SkellyCam code.

The documented commands of baseline/, prototypes/ and cpp/ write into their own results/ folders (and build.bat into cpp/build/),
so a re-run would overwrite the originals the re-run is being compared against. This helper:
  snapshot  : copies baseline/results, prototypes/results, cpp/results, cpp/build to the scratch backup folder and writes a
              SHA-256 manifest of every file (reproducibility/originals_manifest.json)
  collect   : copies every file that is new or changed relative to the manifest into reproducibility/rerun/<area>/... (same
              relative path), and lists them in reproducibility/collected_files.json
  restore   : removes new files and restores changed files from the backup, then verifies every hash (reproducibility/restore_check.json)

Run from C:\Users\Dom\GitHub\freemocap\skellycam:
  .venv\Scripts\python.exe research\frame_ring_buffer\reproducibility\protect_originals.py snapshot|collect|restore
"""
import hashlib, json, shutil, sys, time
from pathlib import Path

FP = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
AREAS = ["baseline/results", "prototypes/results", "cpp/results", "cpp/build"]
BACKUP = Path(r"C:\Users\Dom\AppData\Local\Temp\skellycam_frame_pipeline_tmp\repro_backup")
MAN = HERE / "originals_manifest.json"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def scan():
    out = {}
    for a in AREAS:
        for p in sorted((FP / a).rglob("*")):
            if p.is_file():
                out[p.relative_to(FP).as_posix()] = sha(p)
    return out


def main(cmd):
    if cmd == "snapshot":
        m = scan()
        if BACKUP.exists():
            shutil.rmtree(BACKUP)
        for rel in m:
            d = BACKUP / rel
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(FP / rel, d)
        MAN.write_text(json.dumps(dict(time=time.strftime("%Y-%m-%d %H:%M:%S"), files=m), indent=1))
        print("snapshot", len(m), "files")
    elif cmd == "collect":
        m = json.loads(MAN.read_text())["files"]
        now = scan()
        rows = []
        for rel, h in now.items():
            st = "new" if rel not in m else ("changed" if m[rel] != h else None)
            if st:
                d = HERE / "rerun" / rel
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(FP / rel, d)
                rows.append(dict(path=rel, status=st, bytes=(FP / rel).stat().st_size))
        missing = [r for r in m if r not in now]
        (HERE / "collected_files.json").write_text(json.dumps(dict(time=time.strftime("%Y-%m-%d %H:%M:%S"), collected=rows, missing_after_run=missing), indent=1))
        print("collected", len(rows), "missing", len(missing))
    elif cmd == "restore":
        m = json.loads(MAN.read_text())["files"]
        now = scan()
        removed, restored = [], []
        for rel in now:
            if rel not in m:
                (FP / rel).unlink(); removed.append(rel)
        for rel, h in m.items():
            if not (FP / rel).exists() or sha(FP / rel) != h:
                (FP / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(BACKUP / rel, FP / rel); restored.append(rel)
        # remove now-empty dirs created by the re-run
        for a in AREAS:
            for d in sorted((FP / a).rglob("*"), key=lambda p: -len(p.parts)):
                if d.is_dir() and not any(d.iterdir()) and not (BACKUP / d.relative_to(FP)).exists():
                    d.rmdir()
        final = scan()
        ok = final == m
        (HERE / "restore_check.json").write_text(json.dumps(dict(time=time.strftime("%Y-%m-%d %H:%M:%S"), removed=removed, restored=restored, all_hashes_match_original=ok), indent=1))
        print("removed", len(removed), "restored", len(restored), "ok", ok)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1])
