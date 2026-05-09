#!/usr/bin/env python3
"""
Download openpnp-capture prebuilt shared libraries from GitHub releases.

Artifacts are not committed; run this after clone or before PyInstaller/CI builds.

  uv run python scripts/fetch_openpnp_capture_release.py

Optional:

  uv run python scripts/fetch_openpnp_capture_release.py --tag v0.0.30
  uv run python scripts/fetch_openpnp_capture_release.py --dry-run

Upstream: https://github.com/openpnp/openpnp-capture/releases
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = "openpnp/openpnp-capture"

# (release asset name, path under skellycam/_vendor/openpnp_capture/)
ASSET_MAP: tuple[tuple[str, str], ...] = (
    ("libopenpnp-capture-windows-latest-x86_64.dll", "win-x64/openpnp-capture.dll"),
    ("libopenpnp-capture-ubuntu-22.04-x86_64.so", "linux-x64/libopenpnp-capture.so"),
    ("libopenpnp-capture-ubuntu-22.04-arm64.so", "linux-arm64/libopenpnp-capture.so"),
    ("libopenpnp-capture-macos-latest-arm64.dylib", "macos-arm64/libopenpnp-capture.dylib"),
    ("libopenpnp-capture-macos-latest-x86_64.dylib", "macos-x64/libopenpnp-capture.dylib"),
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _vendor_root() -> Path:
    return _repo_root() / "skellycam" / "_vendor" / "openpnp_capture"


def _request_headers_json() -> dict[str, str]:
    # GitHub API rejects some default clients without User-Agent.
    return {
        "Accept": "application/vnd.github+json",
        "User-Agent": "skellycam-fetch-openpnp-capture",
    }


def _fetch_json(url: str) -> dict:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers=_request_headers_json())
    with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
        return json.loads(resp.read().decode())


def _download(url: str, dest: Path, dry_run: bool) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        print(f"  would fetch -> {dest}")
        return
    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": "skellycam-fetch-openpnp-capture",
        },
    )
    with urllib.request.urlopen(req, timeout=300, context=ctx) as resp:
        dest.write_bytes(resp.read())
    print(f"  wrote {dest} ({dest.stat().st_size} bytes)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch openpnp-capture binaries from GitHub releases.")
    parser.add_argument(
        "--tag",
        default=None,
        help="Release tag (e.g. v0.0.30). Default: latest release.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned downloads only.",
    )
    args = parser.parse_args()

    if args.tag:
        api_url = f"https://api.github.com/repos/{REPO}/releases/tags/{args.tag}"
    else:
        api_url = f"https://api.github.com/repos/{REPO}/releases/latest"

    print(f"Release API: {api_url}")
    try:
        release = _fetch_json(api_url)
    except urllib.error.HTTPError as e:
        print(f"GitHub API error: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Network error: {e}", file=sys.stderr)
        return 1

    tag = release.get("tag_name", "?")
    print(f"Using release: {tag}")

    assets: dict[str, str] = {}
    for a in release.get("assets", []):
        name = a.get("name")
        url = a.get("browser_download_url")
        if name and url:
            assets[name] = url

    vendor = _vendor_root()
    missing: list[str] = []
    for upstream_name, rel_path in ASSET_MAP:
        url = assets.get(upstream_name)
        if not url:
            missing.append(upstream_name)
            continue
        dest = vendor / rel_path
        print(f"{upstream_name}")
        _download(url, dest, args.dry_run)

    if missing:
        print("\nMissing assets in this release (update ASSET_MAP if upstream renamed files):", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 2

    if args.dry_run:
        print("\nDry run complete.")
    else:
        print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
