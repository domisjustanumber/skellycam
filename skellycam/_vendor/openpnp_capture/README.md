# Vendored openpnp-capture binaries (local only)

Skellycam loads the **openpnp-capture** shared library from this tree at runtime (`skellycam.core.camera.openpnp_capture._lib_loader`). **Binaries are not committed** — download them after clone or before packaging.

## Refresh (required for camera capture)

From the repository root:

```bash
uv run python scripts/fetch_openpnp_capture_release.py
```

Options:

- `--tag v0.0.30` — pin a specific GitHub release instead of `latest`
- `--dry-run` — show what would be downloaded

CI runs this automatically before tests and PyInstaller builds (see `.github/workflows/`).

## Expected layout (after running the script)

| Directory        | File                         |
|-----------------|------------------------------|
| `win-x64/`      | `openpnp-capture.dll`        |
| `linux-x64/`    | `libopenpnp-capture.so`      |
| `linux-arm64/`  | `libopenpnp-capture.so`      |
| `macos-arm64/`  | `libopenpnp-capture.dylib`   |
| `macos-x64/`    | `libopenpnp-capture.dylib`   |

Upstream: [openpnp/openpnp-capture releases](https://github.com/openpnp/openpnp-capture/releases).

## When upstream renames release assets

Edit `ASSET_MAP` in `scripts/fetch_openpnp_capture_release.py` to match new filenames from the [latest release assets](https://github.com/openpnp/openpnp-capture/releases/latest).

## Packaging

PyInstaller includes this directory via `Tree(...)` in `skellycam.spec`. Run the fetch script **before** `pyinstaller` so the frozen app ships the native libs.
