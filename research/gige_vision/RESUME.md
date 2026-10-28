# GigE Vision support: resume guide

Paused 2026-10-25 ~15:37 EDT (UTC−4) at the user's request (corrected 2026-10-28; was "EST"). On 2026-10-28 this folder was committed on branch `dom/research` in commit dba82026 (corrected 2026-10-28; was "Nothing is committed.").

**Moved 2026-10-28.** This folder is now `research/gige_vision/` (it was `plans/gige-vision/`). At Dom's request the stand-alone hardware tests also moved out of the skellycam package, from `skellycam/system/diagnostics/gige/` to `research/gige_vision/hardware_tests/`, and their pytest moved from `skellycam/tests/test_gige_diagnostics_selftest.py` to `research/gige_vision/hardware_tests/tests/test_gige_diagnostics_selftest.py`. The import name `skellycam.system.diagnostics.gige` no longer exists, and beartype (`beartype_this_package`) no longer checks these scripts. The future SkellyCam GigE backend plan should decide where shipped diagnostics live (back inside the package, or kept here as research tooling). Run the selftests from the repo root with `python -m pytest research/gige_vision/hardware_tests/tests -q`.

Paths recorded before 2026-10-28 in results/ and journals (`workflows/*.journal.jsonl`, `scratch/**/*.log`, raw output JSON/CSV) refer to the old locations `plans/gige-vision/` and `skellycam/system/diagnostics/gige/` (moved to `research/gige_vision/` and `research/gige_vision/hardware_tests/`).

## Goal (original request)

1. Add capture support for GigE Vision cameras to SkellyCam, focusing on PTP single-cable sync.
2. Explain how frames arrive (raw or compressed).
3. Explain how PTP sync timing is managed.

Every claim needs a link to code, a test or docs. No cameras are available here, so the deliverables include stand-alone tests for other machines (Windows, macOS, Linux). The written report is [docs/gige_vision_report.md](docs/gige_vision_report.md) (moved from Claude Docs to this repo on 2026-10-28).

## Where things stand

| Step | Status | Where |
| --- | --- | --- |
| Research: 9 topics, each adversarially fact-checked | Done | `scratch/digest/*.md` (summary, verifier corrections, missed points), `scratch/digest/*.claims.json`, full notes in `scratch/research/*.md` |
| Report | 4 of 8 sections filled | [docs/gige_vision_report.md](docs/gige_vision_report.md) |
| viva-genicam API reference (tested on Windows + Docker) | Done | `scratch/impl/viva_api.md`, `scratch/impl/viva_api_example.py`, `scratch/impl/prep-viva-api.result.md` |
| Stand-alone hardware test suite | Done; committed 2026-10-28 on branch `dom/research` (dba82026) (corrected 2026-10-28; was "Done, uncommitted") | `hardware_tests/` + `hardware_tests/tests/test_gige_diagnostics_selftest.py` (moved out of `skellycam/system/diagnostics/gige/` on 2026-10-28); log in `scratch/impl/hwtests.md`, `scratch/impl/prep-hardware-tests.result.md` |
| SkellyCam GigE backend (Python) | **Not started**: the agent was interrupted before changing any tracked file | (to be created under `skellycam/core/camera/gige/`) |
| UI pass-through | Not started | `skellycam-ui/` |
| Adversarial review (3 lenses) + fix pass | Not started | |

### Report sections

| Section | Status |
| --- | --- |
| GigE Vision versions | Filled |
| How frames arrive | Filled |
| How PTP sync is managed | Filled |
| Library options compared | Filled |
| Summary | Pending |
| Recommendation and SkellyCam integration design | Pending |
| Stand-alone test suite | Pending |
| Open questions, risks, sources | Pending |

A diagram of the PTP and scheduled-action flow was also planned for the PTP section.

## Key findings (verified)

- **The premise needs correcting.** IEEE 1588 PTP and scheduled action commands came in **GigE Vision 2.0 (2011)**. GigE Vision 3.0 (May 2026) adds optional RDMA/RoCEv2 streaming (GVRSP, 10G and up) and larger control packets. "Single cable" means PoE plus PTP plus scheduled action commands. PTP is optional in every version: check GVCP capability register 0x0934, bits 0x00080000 and 0x00020000.
- **Frames arrive uncompressed:** raw PFNC Bayer or Mono over GVSP/UDP. Compressed payload types (JPEG/J2K/H.264) exist but are rare, and none of the open-source stacks checked (Aravis, Harvesters, pyGigEVision, viva-genicam) decodes them (corrected 2026-10-28; was "no open-source stack decodes them").
- **PTP sync** = PTP clock sync (BMCA elects a camera grandmaster) + scheduled `ACTION_CMD` (0x0100, flag 0x80, 64-bit time) or a vendor PTP free-run mode, or post-hoc pairing by the leader timestamp.
- **Chosen library: viva-genicam 0.10.0** (MIT, Rust, Python wheels for win_amd64, macOS arm64 and manylinux x86_64). It is the only open-source library found that sends scheduled action commands (corrected 2026-10-28; was "the only open-source library"). Its `FakeGigeCamera` works natively on Windows.
  - Gaps: no PTP helpers, no SO_RCVBUF control from Python, a fixed 4-frame drop-oldest queue, and no open-by-IP.
  - Fallback: telegenic (Apache-2.0, no action commands).
- **Rejected options:**
  - pyGigEVision: numerous verified bugs, no GenApi or PTP.
  - Aravis: no PyPI or conda packages, no action commands.
  - Harvesters: stale, holds the GIL, needs a vendor producer.
  - Vendor SDKs: vendor-locked.
- **SkellyCam architecture:** see `scratch/digest/skellycam-arch.md`. Points that matter for the backend:
  - OpenCV is hard-wired in `CameraWorker.create`.
  - Frames are paired by host `frame_number` lockstep.
  - Device timestamps must go in a separate metadata record, not the lifecycle-timestamp dtype.
  - The PFNC BayerRG8 pattern maps to `cv2.COLOR_BayerBG2BGR`.

## How to resume

The workflow resume cache (`resumeFromRunId`) only works inside the original Claude session, which is gone. In a new session:

1. Read this file, `scratch/digest/skellycam-arch.md`, `scratch/impl/viva_api.md` and `hardware_tests/README.md`.
2. Start from `workflows/gige-implement-wf_d9795230-c81.js`:
    - Its `SCRATCH` constant already points at this folder's `scratch/` directory, which has `digest/`, `impl/` and `research/` (updated 2026-10-28). Paths inside the digests still reference the old temp scratchpad, so map them to `scratch/...` here.
    - Delete the `Prep` phase, which is already done. Pass the viva API notes into the implement prompt directly. The text of the completed prep results is in `scratch/impl/prep-*.result.md`.
    - The remaining stages are: implement-backend, implement-ui, 3 review lenses, fix.
3. The research workflow script and both journals, which hold every agent's full structured result, are in `workflows/` for reference.
4. When implementation is done, fill the 4 pending report sections in `docs/gige_vision_report.md`. Optionally add the PTP flow diagram.

## Environment notes

- The repo `.venv` is broken (missing `polars`), so don't use it. Create a separate env with `UV_PROJECT_ENVIRONMENT=<some dir> uv sync --all-extras`.
- The pytest process may hang on exit.
- The test suite already had about 15 beartype/MagicMock failures and 4 errors before this work.
- Docker Desktop and WSL2 Ubuntu are available:
    - The Aravis emulator is `apt install aravis-tools`, then `arv-fake-gv-camera-0.8 -i lo`.
    - Use `--network none` or a dedicated network.
- Docker images built earlier: `skellycam-viva-api:1`, `skellycam-gige-hwtest:1`.
- Large or untrusted items were not copied: cloned third-party repos, venvs, pcaps, Aravis build trees. The old temp scratchpad that held them was deleted on 2026-10-28. Re-clone or rebuild them if needed; the repo URLs and commits are cited in `scratch/digest/*.md` and `scratch/research/*.md`.

## Not part of this work

These folders (under `research/` since 2026-10-28, and committed with this one in dba82026) came from other sessions; this GigE work did not create them (corrected 2026-10-28; was "These untracked folders"):

- `research/arduino_sync/` (was `plans/arduino-sync-PLAN.md`)
- `research/usb_cameras/`
- `research/frame_ring_buffer/` (was `benchmarks/frame_pipeline/`)
