# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Dependency maintenance snapshot for the 2026-11-06 deps audit. No camera access.

GitHub via `gh api`; PyPI and crates.io JSON. Writes JSON to argv[1].
Per repo: license, archived, last default-branch commit, latest release, releases/tags in last 2 years,
open issues and open PRs (search API), distinct commit authors in last 12 months (bus-factor proxy, up to
1000 commits) and top-author share. Optional path filters for monorepos (FFmpeg, OpenCV, GStreamer, SDL).
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import time

NOW = dt.datetime(2026, 11, 6, tzinfo=dt.timezone.utc)
SINCE_2Y = "2024-11-06T00:00:00Z"
SINCE_1Y = "2025-11-06T00:00:00Z"

REPOS = {
    # repo: list of paths to check separately (empty = whole repo)
    "PyAV-Org/PyAV": [],
    "FFmpeg/FFmpeg": ["libavdevice/dshow.c", "libavdevice/dshow_pin.c", "libavdevice/v4l2.c", "libavdevice/avfoundation.m"],
    "opencv/opencv": ["modules/videoio/src/cap_msmf.cpp", "modules/videoio/src/cap_dshow.cpp",
                      "modules/videoio/src/cap_v4l.cpp", "modules/videoio/src/cap_avfoundation_mac.mm"],
    "opencv/opencv-python": [],
    "lukehugh/cv2_enumerate_cameras": [],
    "GStreamer/gstreamer": ["subprojects/gst-plugins-bad/sys/mediafoundation", "subprojects/gst-plugins-good/sys/v4l2",
                            "subprojects/gst-plugins-bad/sys/applemedia"],
    "libsdl-org/SDL": ["src/camera"],
    "Aermoss/PySDL3": [],
    "l1npengtul/nokhwa": [],
    "qt/qtmultimedia": [],
    "enthought/comtypes": [],
    "mhammond/pywin32": [],
    "andreaschiavinato/python_grabber": [],
    "allanhanan/duvc-ctl": [],
    "microsoft/windows-rs": [],
    "microsoft/Windows-Camera": [],
    "openpnp/openpnp-capture": [],
    "wjakob/nanobind": [],
    "pybind/pybind11": [],
    "pywinrt/pywinrt": [],
    "tiagocoutinho/linuxpy": [],
    "tiagocoutinho/v4l2py": [],
    "duanhongyi/pyv4l2": [],
    "soyersoyer/cameractrls": [],
    "gjasny/v4l-utils": [],
    "raymanfx/libv4l-rs": [],
    "ronaldoussoren/pyobjc": [],
    "madsmtm/objc2": [],
    "jtfrey/uvc-util": [],
    "itaybre/CameraController": [],
    "PyO3/pyo3": [],
    "pupil-labs/pyuvc": [],
    "libuvc/libuvc": [],
    "flatpak/xdg-desktop-portal": [],
    "joelpurra/uvcc": [],
}
GITLAB = {
    "gitlab.gnome.org": ["GNOME/pygobject"],
    "gitlab.freedesktop.org": ["pipewire/pipewire", "camera/libcamera", "gstreamer/gstreamer"],
}
PYPI = ["av", "opencv-python", "opencv-contrib-python", "cv2-enumerate-cameras", "gstreamer-bundle", "PyGObject",
        "PySDL3", "PySide6", "comtypes", "pywin32", "pygrabber", "duvc-ctl", "nanobind", "pybind11",
        "winrt-Windows.Media.Capture", "linuxpy", "v4l2py", "v4l2-python3", "pyv4l2", "cameractrls",
        "pyobjc-framework-AVFoundation", "pyobjc-framework-CoreMedia", "pyobjc-framework-CoreMediaIO", "pyobjc-core",
        "maturin", "pupil-labs-uvc"]
CRATES = ["nokhwa", "v4l", "v4l2-sys-mit", "linuxvideo", "windows", "windows-core", "objc2", "objc2-av-foundation",
          "objc2-core-media", "objc2-io-kit", "pyo3", "rusb", "nusb"]


def gh(path: str):
    p = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github+json", path],
                       capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        return None, (p.stderr or p.stdout).strip()[:300]
    try:
        return json.loads(p.stdout), None
    except json.JSONDecodeError as e:
        return None, str(e)


def gh_paged(path: str, max_pages: int = 10):
    out = []
    sep = "&" if "?" in path else "?"
    for page in range(1, max_pages + 1):
        r, err = gh(f"{path}{sep}per_page=100&page={page}")
        if r is None or not isinstance(r, list):
            break
        out.extend(r)
        if len(r) < 100:
            break
    return out


def search_count(q: str):
    time.sleep(2.3)
    r, err = gh("search/issues?q=" + urllib.parse.quote(q) + "&per_page=1")
    return r.get("total_count") if r else None


def authors(commits):
    c = collections.Counter()
    for x in commits:
        login = (x.get("author") or {}).get("login") or (x.get("commit", {}).get("author") or {}).get("name")
        if login and not login.endswith("[bot]") and login not in ("dependabot", "pre-commit-ci"):
            c[login] += 1
    total = sum(c.values())
    top = c.most_common(5)
    # bus factor proxy: smallest number of authors covering >= 50% of commits
    acc, bf = 0, 0
    for _, n in c.most_common():
        acc += n
        bf += 1
        if total and acc >= total / 2:
            break
    return {"n_commits_counted": total, "n_authors": len(c), "top5": top, "authors_for_50pct": bf}


def repo(name: str, paths: list[str]):
    info, err = gh(f"repos/{name}")
    if info is None:
        return {"repo": name, "error": err}
    br = info["default_branch"]
    d = {
        "repo": name, "license": (info.get("license") or {}).get("spdx_id"), "archived": info["archived"],
        "stars": info["stargazers_count"], "default_branch": br, "pushed_at": info["pushed_at"],
        "open_issues_plus_prs": info["open_issues_count"],
    }
    last, _ = gh(f"repos/{name}/commits?sha={br}&per_page=1")
    if last:
        d["last_commit_date"] = last[0]["commit"]["committer"]["date"]
    rels = gh_paged(f"repos/{name}/releases", 3)
    rels = [r for r in rels if not r.get("draft")]
    if rels:
        d["latest_release"] = {"tag": rels[0]["tag_name"], "published_at": rels[0]["published_at"]}
        d["releases_last_2y"] = sum(1 for r in rels if (r.get("published_at") or "") >= SINCE_2Y)
    else:
        tags = gh_paged(f"repos/{name}/tags", 1)
        d["latest_tag"] = tags[0]["name"] if tags else None
    d["open_issues"] = search_count(f"repo:{name} type:issue state:open")
    d["open_prs"] = search_count(f"repo:{name} type:pr state:open")
    if not paths:
        commits = gh_paged(f"repos/{name}/commits?sha={br}&since={SINCE_1Y}", 10)
        d["last_12mo"] = authors(commits)
        commits2 = gh_paged(f"repos/{name}/commits?sha={br}&since={SINCE_2Y}", 10)
        d["commits_last_2y"] = len(commits2) if len(commits2) < 1000 else ">=1000"
    else:
        d["paths"] = {}
        for p in paths:
            c2 = gh_paged(f"repos/{name}/commits?sha={br}&since={SINCE_2Y}&path={urllib.parse.quote(p)}", 5)
            c1 = [x for x in c2 if x["commit"]["committer"]["date"] >= SINCE_1Y]
            lastp = c2[0]["commit"]["committer"]["date"] if c2 else None
            if not c2:
                l1, _ = gh(f"repos/{name}/commits?sha={br}&per_page=1&path={urllib.parse.quote(p)}")
                lastp = l1[0]["commit"]["committer"]["date"] if l1 else None
            d["paths"][p] = {"commits_last_2y": len(c2), "commits_last_12mo": len(c1), "last_commit": lastp,
                             "authors_last_2y": authors(c2)}
    return d


def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "skellycam-research deps audit (github.com/freemocap)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def gitlab(host: str, proj: str):
    base = f"https://{host}/api/v4/projects/{urllib.parse.quote(proj, safe='')}"
    try:
        info = get_json(base)
        d = {"repo": f"{host}/{proj}", "last_activity_at": info.get("last_activity_at"),
             "default_branch": info.get("default_branch"), "open_issues": info.get("open_issues_count")}
        try:
            rel = get_json(base + "/releases?per_page=20")
            d["latest_release"] = (rel[0]["tag_name"], rel[0]["released_at"]) if rel else None
            d["releases_in_page_last_2y"] = sum(1 for r in rel if r["released_at"] >= SINCE_2Y)
        except Exception as e:  # noqa: BLE001
            d["release_err"] = str(e)
        try:
            tags = get_json(base + "/repository/tags?per_page=10")
            d["latest_tags"] = [(t["name"], (t.get("commit") or {}).get("committed_date")) for t in tags[:5]]
        except Exception as e:  # noqa: BLE001
            d["tags_err"] = str(e)
        try:
            mr = urllib.request.Request(base + "/merge_requests?state=opened&per_page=1",
                                        headers={"User-Agent": "skellycam-research"})
            with urllib.request.urlopen(mr, timeout=60) as r:
                d["open_mrs"] = r.headers.get("X-Total")
        except Exception as e:  # noqa: BLE001
            d["mr_err"] = str(e)
        return d
    except Exception as e:  # noqa: BLE001
        return {"repo": f"{host}/{proj}", "error": str(e)}


WHEEL_RE = re.compile(r"-(?P<py>[^-]+)-(?P<abi>[^-]+)-(?P<plat>[^-]+)\.whl$")


def pypi(name: str):
    try:
        d = get_json(f"https://pypi.org/pypi/{name}/json")
    except Exception as e:  # noqa: BLE001
        return {"name": name, "error": str(e)}
    info = d["info"]
    rel_dates = {}
    for v, files in d["releases"].items():
        ts = [f["upload_time_iso_8601"] for f in files]
        if ts:
            rel_dates[v] = min(ts)
    wheels = collections.defaultdict(set)
    for f in d["urls"]:
        m = WHEEL_RE.search(f["filename"])
        if m:
            for plat in m["plat"].split("."):
                wheels[plat].add(m["py"] + ("/" + m["abi"] if m["abi"] != "none" else ""))
    return {
        "name": name, "version": info["version"],
        "uploaded": min((f["upload_time_iso_8601"] for f in d["urls"]), default=None),
        "requires_python": info.get("requires_python"),
        "license": info.get("license_expression") or (info.get("license") or "")[:60],
        "releases_last_2y": sum(1 for t in rel_dates.values() if t >= SINCE_2Y),
        "sdist_only": not wheels and bool(d["urls"]),
        "wheels": {k: sorted(v) for k, v in sorted(wheels.items())},
        "classifiers_py": [c.split("::")[-1].strip() for c in info.get("classifiers", []) if "Python :: 3." in c],
        "dev_status": [c for c in info.get("classifiers", []) if "Development Status" in c],
    }


def crate(name: str):
    try:
        d = get_json(f"https://crates.io/api/v1/crates/{name}")
    except Exception as e:  # noqa: BLE001
        return {"name": name, "error": str(e)}
    vs = [v for v in d["versions"] if not v["yanked"]]
    newest = max(vs, key=lambda v: v["created_at"])
    return {"name": name, "max_stable": d["crate"].get("max_stable_version"), "newest": newest["num"],
            "newest_date": newest["created_at"], "versions_last_2y": sum(1 for v in vs if v["created_at"] >= SINCE_2Y),
            "license": newest.get("license"), "repository": d["crate"].get("repository"),
            "recent_downloads_90d": d["crate"].get("recent_downloads")}


def main():
    out = {"snapshot_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "github": [], "gitlab": [], "pypi": [], "crates": []}
    for name, paths in REPOS.items():
        print("gh", name, file=sys.stderr)
        out["github"].append(repo(name, paths))
    for host, projs in GITLAB.items():
        for p in projs:
            out["gitlab"].append(gitlab(host, p))
    for n in PYPI:
        out["pypi"].append(pypi(n))
    for n in CRATES:
        out["crates"].append(crate(n))
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=list)


if __name__ == "__main__":
    main()
