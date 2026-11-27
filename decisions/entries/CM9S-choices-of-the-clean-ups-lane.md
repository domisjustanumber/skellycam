# CM9S — Choices of the clean-ups lane

**Status:** proposed, 2026-11-27 (agent: the clean-ups lane on `dom/cleanups-q871`, Q915 item 6).

## Decision

The user decided the work (Q871, Q873, Q892, Q900, Q909 of
[ADR-BPP8](BPP8-answers-of-the-user-q864-to-q873-on-the-step-4b-code.md),
[ADR-N2VE](N2VE-decisions-of-the-user-on-the-ci-triage-and-the-stall-watch-code.md) and
[ADR-Y2RN](Y2RN-decisions-of-the-user-on-the-size-floor-review-and-certify-quick-runs.md)). These choices fill gaps.

1. **Q871, the guard and the probes.** T-PRV-30 searches the Python files for `read_latest_ring_frames`, and
   checks that `WebsocketServer` has no attribute `_send_json`. `_send_json` is not a name search:
   `PreviewRelay` keeps its own `_send_json` (the JSON send that the server passes in). The two probes of
   `test_camera_requests.py` use a helper `shows_a_frame` with the lock, the gate check and the read of the
   deleted method. `test_group_watch.py` reads the ring reader on the event loop with no lock, as
   `PreviewRelay` does. The specs that said "stays" get one sentence each (`preview-4b.md` 1.3, 3.1, 3.2, 7.4,
   7.7; `preview.md` 2.3; `capture-timings.md` table 3.1 and 6.4).
2. **Q900, "the other three language files".** skellycam-ui has 40 locale files besides English, not three.
   The lane reads "three" as the three languages of the docs copies (`skellycam-docs/i18n/`: `es`, `zh-CN`,
   `ar`). The other 37 locales fall back to English, as the other keys of step 4 do
   ([`preview-4b.md`](../../specs/preview-4b.md) 5.8). No test checks that all locale files have the same keys
   (English has 63 keys that no other file has), so T-CAP-165 gets one small test: the three files have both
   keys, with "1280 × 720" and "640 × 360" unchanged (`windows-capture.md` 22.2).

## Reason

Each choice is the smallest change that does what the answer says, with a test that fails first.

## Open work

See [open-work.md](../open-work.md).
