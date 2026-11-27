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
   keys, with "1280 × 720" and "640 × 360" unchanged (`windows-capture.md` 22.2). The texts are the lane's
   translations: es "El seguimiento de manos y cara será limitado con esta resolución. 1280 × 720 o más da el
   mejor seguimiento." and "El tamaño mínimo es 640 × 360"; zh-CN "在此分辨率下，手部和面部跟踪会受到限制。1280 × 720
   或更高可获得最佳跟踪效果。" and "最小尺寸为 640 × 360"; ar "سيكون تتبع اليدين والوجه محدودًا بهذه الدقة. تعطي دقة
   1280 × 720 أو أعلى أفضل تتبع." and "أصغر حجم هو 640 × 360". In the Arabic file each size is in a left-to-right
   isolate (`⁦` … `⁩`, written as escapes): in right-to-left text the bidi rules would show
   "720 × 1280". No native speaker checked them.
3. **Q892, the stall-watch test (T-UNX-109 of `unix-capture.md`).** The frames stop at the first read in
   `waiting` after the open of a reopen (a size change), by the read hook of the fake factory: that pass
   attaches the new rings, so the test runs the attach path of 4.10. A stop in the open itself (a held open)
   fails the camera at stage `warm-up` in `starting`, where the watch is off, so it tests nothing. The watch
   goes on the clock in the test only: in its thread, `time.monotonic` of the group module gives the clock
   time and `_stop_watch.wait` waits on the clock, so each round is 0.1 s of clock time; the thread leaves the
   clock at its end. The test checks that the watch did not trip (a spy on `CameraGroup._end_process`), the
   failure of the in-process rule, and at least 15 rounds of the watch in the 2 s after the stop. The failure
   text alone is not enough: with THREAD workers a tripped watch cannot end the loop, and the loop writes its
   own failure later over the failure of the watch. It has the marker `capture_timing`, as each test of its
   file. Evidence (not committed): with the in-process limit patched to 3 s the test fails ("the watch
   tripped"); with the count after the attach removed it still passes, because on the virtual clock the attach
   and its count take no time. The unit test of 4PPS item 10 guards that count.
4. **Q909, the kill rule.** `PreviewKit.close` still ends every step (each app, then each server), then throws
   one error that names each killed step. A kill counts both at a time-out of `close` and in `UiServer.stop`
   when the clean stop failed. The "hung step" note stays in the report.
5. **Step 8 nits.** The fixture of T-TIM-24 gets `window_ns` 1000500000 and the id `frame_hash` with 600
   samples: the oldest 88 are 90 ms, so a summary over all 600 would differ. `expected` comes from the Python
   `build_summary`. `capture-timings.md` 5.3 gets the sentence on the stamp of `PreviewTiles` when off.
6. **Q873, the docs page.** The new first section, "Each camera on its own", states only facts of
   `preview.md` 4.1, 4.3, 5.4 and `preview-4b.md` 4.1. The copies in `es`, `zh-CN` and `ar` get the same
   English section (the rule of [`preview-4b.md`](../../specs/preview-4b.md) 5.9). The front matter
   `description` and the feature text of `content.config` still describe one message for a group: not
   changed (outside the first section).

## Reason

Each choice is the smallest change that does what the answer says, with a test that fails first.

## Open work

See [open-work.md](../open-work.md).
