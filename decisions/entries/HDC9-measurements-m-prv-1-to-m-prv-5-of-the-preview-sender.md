# HDC9 — Measurements M-PRV-1 to M-PRV-5 of the preview sender

**Status:** evidence, 2026-11-20 (agent; commit to dom/preview).

## Evidence

Measurements M-PRV-1 to M-PRV-5 of section 8.5 of [`specs/preview.md`](../../specs/preview.md) were
made on 2026-11-20 on the code of step 4a (commit 048cc5640). The script is
[`scripts/measure_preview_m_prv.py`](../scripts/measure_preview_m_prv.py). The machine was an
Intel Core i7-14700K with Windows 11, Python 3.13.18, uvicorn 0.54.0 (`ws="auto"`, the sans-I/O
websockets implementation, as `skellycam/__main__.py`) and websockets 17.4. No camera was used. The
rings were real rings with random payloads of the largest real JPEG size: 276,269 bytes (720p) and
607,032 bytes (1080p). The writers ran in a second process, and the websocket client and a
`GET /health` probe every 20 ms ran in a third. The client offered permessage-deflate, as a browser
does. Each uvicorn run had 2 s of warm-up and 10 s of measurement.

**The finding.** uvicorn turns on permessage-deflate by default. Then the server compresses each
JPEG on the event-loop thread. A JPEG does not compress. Answer A9 of
[ADR-G651](G651-phase-4-live-preview-decisions-p1-to-p7.md) turns compression off. Thus the column
"deflate off" is the product configuration from commit 048cc5640.

In process (M-PRV-1, M-PRV-2 pack, M-PRV-4 pass interval), median / p99 in ms:

| Item | 720p | 1080p |
|---|---|---|
| M-PRV-1: `read` of one frame | 0.08 / 0.16 | 0.25 / 0.44 |
| M-PRV-2: `pack_camera_frame` | 0.005 / 0.014 | 0.11 / 0.16 |
| M-PRV-4: interval between passes, one ready camera with no new frame | 11.0 / 12.1 | |

Through uvicorn. "Keeps up" is a client that answers at once:

| Item | Target (8.4) | deflate on | deflate off |
|---|---|---|---|
| M-PRV-2: send of a 720p message, median / p99 (4 x 720p30) | | 7.7 / 10.1 ms | 0.13 / 0.63 ms |
| M-PRV-2: send of a 1080p message, median / p99 (4 x 1080p30) | | 16.9 / 20.8 ms | 0.23 / 1.11 ms |
| M-PRV-3: event-loop thread CPU, 4 x 720p30, keeps up | | 97 % | 12 % |
| M-PRV-3: event-loop thread CPU, 4 x 1080p30, keeps up | 10 %; 19 % after A10 | 99 % | 17 % (six runs: 13 to 19 %, median 16 %) |
| M-PRV-3: event-loop thread CPU, 8 x 1080p60, keeps up | | 99 % | 37 % |
| M-PRV-3: event-loop thread CPU, 4 x 1080p30 / 8 x 1080p60, never answers | | 11 % / 21 % | 4 % / 7 % |
| M-PRV-3: event-loop thread CPU, 8 x 1080p60, no client | | 4 % | 3 % |
| M-PRV-3: `GET /health` p99, 8 x 1080p60, keeps up | at most 50 ms | 142 ms | 16 ms |
| M-PRV-3: `GET /health` p99, 8 x 1080p60, never answers | | 103 ms | 14 ms |
| M-PRV-4: `published_ns` to the start of the send, p99, 4 x 1080p30 / 8 x 1080p60, keeps up | at most 25 ms | 33 / 17 ms | 13 / 14 ms |
| Messages sent each second, 4 x 1080p30 / 8 x 1080p60, keeps up | 120 / 480 | 55 / 54 | 120 / 475 |
| Frames not shown, 30 fps, keeps up (4 x 720p30 and 4 x 1080p30) | none | 3 % and 54 % | none |
| M-PRV-5: frames not shown, 8 x 1080p60, keeps up | | 89 % | 1.2 % mean, 3.8 % largest camera |

- The first run, on 2026-11-19, used the legacy websockets implementation of uvicorn
  (`ws="websockets"`). It gave 12.7 ms against 0.31 ms for the send of a 1080p message, and an
  event-loop thread CPU of 12.2 % at 4 x 1080p30 with compression off.
- In 30 runs of 8 x 1080p60 with compression off, 2 runs (sans-I/O) and 1 run (legacy) sent less
  than 400 messages each second (157 to 262 and 176). The other runs sent 467 to 480. The cause is
  not known. The client process, in Python, reads about 290 MB each second in this case.
- With the legacy implementation and compression off, 6 of 30 runs of 8 x 1080p60 logged an
  `AssertionError` in `_drain_helper` of `websockets/legacy/protocol.py` ("data transfer failed").
  The client closes the connection while a send of the sender waits for the transport. Then the
  library writes its close frame and waits for the transport again, and the assert finds the first
  waiter. This race is in the library. With compression on, 0 of 30 runs logged it. With the
  implementation of the product (`ws="auto"`), 0 of 30 runs logged it.
- Target "read of a 1080p JPEG, p99 at most 0.5 ms": met (0.44 ms; 0.39 ms in the first run).
- The never-answers runs have a `published_ns` to send time of 33 ms p99 at 30 fps. The safety net
  sends the newest frame at a time that does not follow a commit. The target applies to a client
  that keeps up.

Limits: one machine, Windows only. M-PRV-4 on Linux is not measured. The payloads were random
bytes. Real JPEGs are smaller (8.1), so these loads are high limits for the sizes. The event-loop
CPU includes uvicorn, the `/health` route and the sender.

## Open work

See [open-work.md](../open-work.md).
