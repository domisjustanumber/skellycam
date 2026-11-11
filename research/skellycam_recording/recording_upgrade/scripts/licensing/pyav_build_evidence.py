"""Collect source evidence for how PyAV wheels bundle FFmpeg (needs the GitHub CLI `gh`, read-only API calls).

For PyAV tags v18.0.0 and v19.0.2: which pyav-ffmpeg release the wheel build pulls (scripts/ffmpeg-latest.json,
used by .github/workflows/tests.yml CIBW_BEFORE_BUILD_WINDOWS). For pyav-ffmpeg tags: the configure flags in
scripts/build-ffmpeg.py and the patch to FFmpeg's configure that moves libx264/libx265 out of
EXTERNAL_LIBRARY_GPL_LIST. Also FFmpeg's own LICENSE.md lines about libx264 at n8.1.2 and n9.0.2.
Usage: python pyav_build_evidence.py --out <json>
"""
import argparse
import json
import re
import subprocess


def gh_raw(repo, path, ref):
    r = subprocess.run(["gh", "api", f"repos/{repo}/contents/{path}?ref={ref}", "-H", "Accept: application/vnd.github.raw"],
                       capture_output=True, text=True, encoding="utf-8")
    return r.stdout if r.returncode == 0 else None


def gh_json(endpoint, jq):
    r = subprocess.run(["gh", "api", endpoint, "--jq", jq], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); a = ap.parse_args()
res = {"pyav": {}, "pyav_ffmpeg": {}, "ffmpeg": {}}
for t in ["v18.0.0", "v19.0.2"]:
    wf = gh_raw("PyAV-Org/PyAV", ".github/workflows/tests.yml", t) or ""
    res["pyav"][t] = {
        "tag_commit": gh_json(f"repos/PyAV-Org/PyAV/git/ref/tags/{t}", ".object.sha"),
        "ffmpeg_latest_json": json.loads(gh_raw("PyAV-Org/PyAV", "scripts/ffmpeg-latest.json", t) or "{}"),
        "windows_before_build": [l.strip() for l in wf.splitlines() if "CIBW_BEFORE_BUILD_WINDOWS" in l],
    }
for t in ["8.1.1-2", "9.0.2-1"]:  # 8.1.2-1 (used by PyAV 18.0.0) has no git tag on GitHub; nearest tags shown
    build = gh_raw("PyAV-Org/pyav-ffmpeg", "scripts/build-ffmpeg.py", t) or ""
    patch = gh_raw("PyAV-Org/pyav-ffmpeg", "patches/ffmpeg.patch", t) or ""
    res["pyav_ffmpeg"][t] = {
        "tag_commit": gh_json(f"repos/PyAV-Org/pyav-ffmpeg/git/ref/tags/{t}", ".object.sha"),
        "build_flags_with_gpl_or_x26x": [l.strip() for l in build.splitlines() if re.search(r"enable-(gpl|libx26[45]|version3|nonfree)", l)],
        "configure_patch_hunks": [l for l in patch.splitlines() if re.match(r"^[+-]\s+libx26[45]|^@@.*EXTERNAL_LIBRARY", l)],
    }
res["pyav_ffmpeg"]["patch_history"] = gh_json("repos/PyAV-Org/pyav-ffmpeg/commits?path=patches/ffmpeg.patch&per_page=10",
                                              '[.[] | .sha[0:10] + " " + .commit.author.date + " " + (.commit.message|split("\\n")[0])]')
res["pyav_ffmpeg"]["release_8.1.2-1"] = gh_json("repos/PyAV-Org/pyav-ffmpeg/releases/tags/8.1.2-1", ".tag_name") or "NOT FOUND via API"
res["pyav_ffmpeg"]["release_9.0.2-1"] = gh_json("repos/PyAV-Org/pyav-ffmpeg/releases/tags/9.0.2-1", ".tag_name + \" \" + .published_at")
for t in ["n8.1.2", "n9.0.2"]:
    lic = gh_raw("FFmpeg/FFmpeg", "LICENSE.md", t) or ""
    i = lic.find("The following libraries are under GPL version 2:")
    res["ffmpeg"][t] = {"tag_commit": gh_json(f"repos/FFmpeg/FFmpeg/git/ref/tags/{t}", ".object.sha"),
                        "LICENSE.md_gpl_section": lic[i:i + 330] if i >= 0 else None}
open(a.out, "w", encoding="utf-8").write(json.dumps(res, indent=1))
print(json.dumps(res, indent=1)[:3000])
