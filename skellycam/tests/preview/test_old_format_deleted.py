"""T-PRV-30: the old group message is deleted (specs/preview-4b.md 3.1, 7.7) [P5].

search. The rule is the deletion itself. The test searches the files of 7.7 for the names of 7.7, and checks that
each deleted file of 3.1 does not exist. It does not search the decision log, `specs/`, `skellycam/tests/preview/`,
`node_modules`, build output or `.venv`. A name matches only as a whole word: `FRAME_HEADER_SIZE` must not match
`CAMERA_FRAME_HEADER_SIZE`, the constant of the new parser (5.2) [ADR-70WD]. `WebsocketServer._send_json` is
checked as an attribute, not as a name: `PreviewRelay` keeps a `_send_json` of its own (7.7) [Q871].
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKIP_DIRS = {"node_modules", ".venv", "__pycache__", "build", "dist", "dist-electron", "dist-player-harness",
             ".docusaurus", "test-results"}
PREVIEW_TESTS = ROOT / "skellycam" / "tests" / "preview"

OLD_KEYS = ("frameNumber", "frameAcknowledgment", "backend_framerate", "frontend_framerate")
PYTHON_ONLY = ("frontend_payload_bytearray", "FRONTEND_FRAME_HEADER_DTYPE", "FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE",
               "get_latest_ring_payload", "get_latest_frontend_payloads", "get_backend_framerate_updates",
               "_frontend_image_relay", "check_frame_acknowledgment_status", "last_received_frontend_confirmation",
               "BACKPRESSURE_WARNING_THRESHOLD", "FramerateUpdateMessage", "parse_relay",
               "read_latest_ring_frames")  # Q871
UI_KEYS = ("frameAcknowledgment", "backend_framerate", "frontend_framerate")  # not frameNumber: CameraMessage has it
UI_AND_DOCS = ("parseMultiFramePayload", "PAYLOAD_FOOTER", "FRAME_HEADER_SIZE", "FrameProcessor", "CanvasManager",
               "transferControlToOffscreen", "bitmaprenderer", "frame-decode.worker", "offscreen-renderer.worker")

AREAS = {  # area: (root, file pattern, names)
    "python": (ROOT / "skellycam", "*.py", OLD_KEYS + PYTHON_ONLY),
    "ui": (ROOT / "skellycam-ui" / "src", "*", UI_KEYS + UI_AND_DOCS),
    "docs": (ROOT / "skellycam-docs" / "docs", "*", OLD_KEYS + UI_AND_DOCS),
    "docs-i18n": (ROOT / "skellycam-docs" / "i18n", "*", OLD_KEYS + UI_AND_DOCS),
}

DELETED = (
    "skellycam/core/types/frontend_payload_bytearray.py",
    "skellycam-ui/src/services/server/server-helpers/frame-processor",
    "skellycam-ui/src/services/server/server-helpers/canvas-manager.ts",
    "skellycam-ui/src/services/server/server-helpers/offscreen-renderer.worker.ts",
)


def files_of(root, pattern):
    for path in root.rglob(pattern):
        parts = set(path.relative_to(ROOT).parts)
        if not path.is_file() or parts & SKIP_DIRS or path.is_relative_to(PREVIEW_TESTS):
            continue
        yield path


def whole_word(name):
    return re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")


def test_t_prv_30_the_names_of_the_old_format_are_gone():
    """T-PRV-30: no file of 7.7 holds a name of 7.7."""
    hits = []
    for area, (root, pattern, names) in AREAS.items():
        patterns = {name: whole_word(name) for name in names}
        for path in files_of(root, pattern):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            hits += [f"{path.relative_to(ROOT).as_posix()}: {name}" for name, rx in patterns.items() if rx.search(text)]
    assert hits == [], f"{len(hits)} hits:\n" + "\n".join(hits[:40])


def test_t_prv_30_the_deleted_files_do_not_exist():
    """T-PRV-30: each deleted file of 3.1 does not exist."""
    assert [path for path in DELETED if (ROOT / path).exists()] == []


def test_t_prv_30_the_server_has_no_send_json():
    """T-PRV-30, 7.7 [Q871]: `WebsocketServer` has no `_send_json`; nothing sent JSON through it after 4b."""
    from skellycam.api.websocket.websocket_server import WebsocketServer

    assert not hasattr(WebsocketServer, "_send_json")
