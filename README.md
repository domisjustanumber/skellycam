<p align="center">
    <img src="https://github.com/user-attachments/assets/55dea5bb-6823-4773-b41e-a43a4d84c2ba" height="240" alt="SkellyCam Logo">
</p>

<h3 align="center">SkellyCam</h3>
<p align="center">Frame-perfect multi-camera synchronization for USB webcams 💀📸</p>
<p align="center">
    <a href="https://github.com/freemocap/skellycam/releases/latest">
        <img src="https://img.shields.io/github/release/freemocap/skellycam.svg" alt="Latest Release">
    </a>
    <a href="https://github.com/freemocap/skellycam/blob/main/LICENSE">
        <img src="https://img.shields.io/badge/license-AGPLv3+-blue.svg" alt="AGPLv3+">
    </a>
    <a href="https://github.com/freemocap/skellycam/actions/workflows/test.yml">
        <img src="https://github.com/freemocap/skellycam/actions/workflows/test.yml/badge.svg" alt="Tests">
    </a>
</p>

---

## What SkellyCam Does

SkellyCam turns a handful of cheap USB webcams into a synchronized multi-camera system. It guarantees **frame-perfect synchronization** — every camera produces the exact same number of frames, and each "multi-frame" event delivers one image from every camera captured at the same moment. This makes it suitable for applications like markerless motion capture, 3D reconstruction, and multi-view computer vision where frame-number identity across cameras is non-negotiable.

SkellyCam is the camera backend for the [FreeMoCap](https://github.com/freemocap/freemocap) markerless motion capture project.

### Key Features

- **Synchronized recording** — all cameras produce videos with precisely the same frame count, with high-resolution `perf_counter_ns` timestamps for post-hoc analysis
- **Live streaming** — WebSocket protocol delivers synchronized multi-frame payloads (one image per camera per frame event) in real time
- **Frame-locked playback** — recorded videos always display the exact same frame number across all cameras, with frame-stepping, variable-speed, and keyboard shortcuts
- **Audio capture** — optional microphone recording alongside video
- **Recording browser** — browse saved sessions with metadata (camera count, file size, duration, FPS, frame count), sorted newest-first
- **Internationalization** — UI available in 36+ languages ([help us translate!](TRANSLATING.md))

---

## Quick Start

### Download

The easiest way to get started is to download the installer for your platform:

**[Download SkellyCam](https://freemocap.github.io/skellycam/download)** | [GitHub Releases](https://github.com/freemocap/skellycam/releases/latest)

The installer bundles everything you need — no Python or Node.js required.

### Run from Source

For developers who want to run from the source code:

```bash
# Clone and install the Python server
git clone https://github.com/freemocap/skellycam
cd skellycam
uv venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv sync

# Start the server
python -m skellycam
# or just: skellycam

# In another terminal — install and start the UI
cd skellycam-ui
npm install
npm run dev
```

Server starts on `http://localhost:53117`. Swagger docs at `http://localhost:53117/docs`.

See the [Development guide](https://freemocap.github.io/skellycam/docs/development/) for full setup instructions including prerequisites and troubleshooting.

#### Linux Only

Audio recording requires additional system packages:

```bash
sudo apt update && sudo apt install clang portaudio19-dev
```

---

## How It Works

Each camera runs in its own OS process to avoid the GIL. USB webcam capture uses **[openpnp-capture](https://github.com/openpnp/openpnp-capture)** (native library + vendored binaries; see [`skellycam/_vendor/openpnp_capture/README.md`](skellycam/_vendor/openpnp_capture/README.md)). Workers rendezvous before opening streams so bandwidth negotiation behaves reliably across cameras. Inside each worker, the `CameraOrchestrator` keeps frame counts aligned so every camera advances together; one multi-frame payload still carries exactly one synchronized frame index per camera plus high-resolution `perf_counter_ns` timestamps around capture.

OpenCV (`cv2`) stays in the stack for **`VideoWriter`**, rotation helpers, **`putText`** overlays, and writer-side fourcc / file-extension helpers — not for enumerating cameras or decoding the live capture path.

### Trade-offs (openpnp-capture vs OpenCV grab/retrieve)

openpnp-capture returns **already decoded RGB**. Decompression runs on **the library’s internal worker thread** while polling the OS driver; the Python side reads the latest decoded frame with a memcpy-style copy. That replaces the older OpenCV pattern where **`grab()`** latched raw driver buffers (cheap, easy to timestamp at dequeue time) and **`retrieve()`** did heavy decode afterward on the worker thread — deliberately ordered across cameras so decode did not widen inter-camera timing spread.

| | OpenCV grab/retrieve (previous) | openpnp-capture (current) |
| --- | --- | --- |
| **Timestamp meaning** | Could bracket dequeue vs decode separately | Timestamps bracket “copy decoded RGB”; decode time is invisible from Python |
| **Main-thread work** | `retrieve()` competed with coordinated `grab()` timing | Hot loop variability often **drops**; decode happens off the per-camera thread that runs the capture loop |
| **Practical emphasis** | Finer notion of OS delivery time | Typically **better cross-camera consistency** with less variability on the coordinated capture step |

For backward compatibility, frame metadata still exposes separate `*_grab_*` and `*_retrieve_*` timestamp fields; under openpnp they are set identically each frame (one call brackets both), so downstream code that expected the old dtype shape keeps working.

Recovering separate grab-vs-decode visibility *and* this lower-jitter behavior would mean extending or **forking** openpnp-capture to expose dequeue and decode as distinct C API stages (discussion and breadcrumbs in [`openpnp_get_frame`](skellycam/core/camera/openpnp/openpnp_helpers/openpnp_get_frame.py) and contributor notes).

For the full architecture (process model, IPC, data flow, playback sync), see the [Architecture docs](https://freemocap.github.io/skellycam/docs/technical/architecture).

---

## Documentation

| Page | Description |
|------|-------------|
| [Quick Start](https://freemocap.github.io/skellycam/docs/getting-started/quick-start) | Installation, first run, and basic workflow |
| [Beginner Tutorial](https://freemocap.github.io/skellycam/docs/getting-started/beginner-tutorial) | Camera selection, configuration, and recording |
| [Advanced Tutorial](https://freemocap.github.io/skellycam/docs/getting-started/advanced-tutorial) | Data model, folder structure, server configuration |
| [Architecture](https://freemocap.github.io/skellycam/docs/technical/architecture) | Synchronization protocol, process model, data flow |
| [API Reference](https://freemocap.github.io/skellycam/docs/technical/api-reference) | HTTP and WebSocket endpoint documentation |
| [WebSocket Protocol](https://freemocap.github.io/skellycam/docs/technical/websocket-protocol) | Binary frame format, JSON messages, backpressure |
| [Development](https://freemocap.github.io/skellycam/docs/development/) | Running from source, testing, linting, CI, and contributing |

---

## API at a Glance

| Method   | Path                                        | Description                        |
|----------|---------------------------------------------|------------------------------------|
| `GET`    | `/health`                                   | Health check                       |
| `GET`    | `/shutdown`                                 | Graceful shutdown                  |
| `POST`   | `/skellycam/camera/detect`                  | Detect available cameras           |
| `GET`    | `/skellycam/camera/microphone/detect`       | Detect available microphones       |
| `POST`   | `/skellycam/camera/group/apply`             | Create or update camera group      |
| `POST`   | `/skellycam/camera/group/all/record/start`  | Start recording                    |
| `GET`    | `/skellycam/camera/group/all/record/stop`   | Stop recording                     |
| `DELETE` | `/skellycam/camera/group/close/all`         | Close all camera groups            |
| `GET`    | `/skellycam/camera/group/all/pause_unpause` | Toggle pause                       |
| `GET`    | `/skellycam/playback/recordings`            | List recordings with stats         |
| `POST`   | `/skellycam/playback/load`                  | Load a recording for playback      |
| `GET`    | `/skellycam/playback/videos`                | List loaded videos                 |
| `GET`    | `/skellycam/playback/video/{video_id}`      | Stream a video file                |
| `GET`    | `/skellycam/playback/timestamps`            | Get timestamps for all loaded videos |
| `GET`    | `/skellycam/playback/timestamps/{video_id}` | Get timestamp metadata for a video |
| `WS`     | `/skellycam/websocket/connect`              | Real-time frames and logs          |

Full details in the [API Reference](https://freemocap.github.io/skellycam/docs/technical/api-reference).

---

## Development

```bash
uv sync --group dev                     # Install dev dependencies
uv run pytest skellycam/tests/ -v       # Run tests
uv run ruff check skellycam/            # Lint
uv run poe test                         # Via task runner
```

See the [Development guide](https://freemocap.github.io/skellycam/docs/development/) for the full setup.

---

## License

**AGPL-3.0-or-later** — see [LICENSE](LICENSE). Contact the FreeMoCap team for alternative licensing.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Translations welcome — see [TRANSLATING.md](TRANSLATING.md).
