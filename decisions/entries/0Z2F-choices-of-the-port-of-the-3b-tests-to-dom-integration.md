# 0Z2F — Choices of the port of the 3b tests to dom/integration

**Status:** proposed, 2026-11-25 (agent).

## Decision

On 2026-11-25 the user asked for the JPEG encode at capture for uncompressed cameras, tests first
(Q689). The accepted spec is section 13 of [`specs/windows-capture.md`](../../specs/windows-capture.md)
([ADR-4CQC](4CQC-phase-3-windows-capture-spec-and-test-list.md)), with the answers V1 to V7
([ADR-8MTY](8MTY-answers-v1-to-v7-of-the-user-to-the-3b-and-3c-tests.md)). The failing tests of step
3b were on `dom/3bc-tests` (2026-11-19). That branch did not merge, and `dom/integration` is now 537
commits ahead of its base. An agent chose the items below for the port. Section 21 of the spec states
the result.

1. **Scope.** Only the fake tests of step 3b move to `dom/integration`: T-CAP-61 to T-CAP-67, T-CAP-70,
   T-CAP-71 (step 3b by V1), T-CAP-89, and the four V tests of item 2. They are in
   `skellycam/tests/capture/test_uncompressed.py`, with the helpers in `uncompressed.py`, their
   self-tests in `test_helpers_uncompressed.py`, and the raw path of `fake_source.py`. The 3c tests
   (T-CAP-72 to T-CAP-78, the OpenCV control tests of V5), the hardware tests (T-CAP-68, T-CAP-69,
   T-CAP-79) and the 3c spec edits of V5 and V7 stay on `dom/3bc-tests`.
2. **Test numbers.** T-CAP-105, T-CAP-106, T-CAP-109 and T-CAP-110 of `dom/3bc-tests` and of ADR-8MTY
   are T-CAP-150, T-CAP-151, T-CAP-152 and T-CAP-153 here. On `dom/integration`, T-CAP-105 to
   T-CAP-113 are other tests. T-CAP-114 to T-CAP-149 stay free for the lanes that edit 16.2 now.
3. **Place of the spec text.** A new section 21, not edits in 7.4, 8.4, 13, 14 and 16. Another lane
   holds 16.2, 16.6 and 16.7 now. When the two lanes merge, the rows of 21.3 move to 16.2, and 16.6
   and 16.7 get the new counts. Section 21.2 states the rules of V1 to V4 and V6 one time. Sections
   7.4, 8.4 and 14 get the same text when the rows move.
4. **The range in the log.** [`recorder.md`](../../specs/recorder.md) 6.7 gives `input_range` to the
   log of the camera process only. Thus "the recording info holds it" (T-CAP-65 on `dom/3bc-tests`)
   is "the log holds it": at least one log line of the camera with the words "input range" and the
   decision, and no such line with the other value. "`input_range` is null in the recording info" of
   V4 is "no range line in the log" for a camera of the OpenCV source (T-CAP-150).
5. **T-CAP-67 on the take recorder.** The note of 2026-11-20 changed T-CAP-67: the recorder takes the
   encoded JPEG. The test checks that each frame that the camera writer gets is the Quick Sync JPEG,
   with the same bytes as the ring frame of the same source frame, with no gap in the frame numbers,
   and that each block of the camera file of the take is one of these JPEGs (JPEG-MKV, Q689).
6. **Failure for the right reason.** Before the product code, a test fails on an assertion or on a
   named missing module, never at collection. The fake gives `os_range` only when the product
   `OpenedMode` has the field. The detection result has `capture_modes` only when
   `modes.capture_modes` exists. `QuickSyncFake(available=False)` replaces nothing when
   `capture.encoder` does not exist; `available=True` then fails the test with the module name. The
   tests assert that the status has `jpeg_encoder` before they read it. T-CAP-70 also checks that the
   422 names the one-rate rule: today the YUY2 request alone is refused, so a bare 422 passes.
7. **Helpers outside `capture_session.py`.** That file is held by another lane now. Thus
   `uncompressed.BgrImages` keeps a copy of each BGR ring image (the `Spies` keep only its hash), and
   `uncompressed.stop_line_count(messages, camera_id, word)` reads the `encoder fallbacks` stop line.
   The `dom/3bc-tests` changes of `Spies` and of `stop_line_count` are not ported.
8. **T-CAP-150 on the virtual clock.** `OpenCVFakeFactory` of `dom/integration` runs the OpenCV fake on a
   virtual clock. Thus T-CAP-150 no longer runs in real time. It checks "no Quick Sync check" only
   when `capture.encoder` exists, because no check can run without it.

## Reason

- Items 1 and 2: the brief of the lane is the encode at capture, with no timed test and no camera.
  Numbers must be unique on the branch that merges.
- Items 3 and 7: the lane must not edit the files and sections that another lane holds.
- Items 4 and 5: the take recorder of step 5a replaced the old recorder and its recording info.
- Item 6: the brief asks for failures for the right reason, not import errors.

## Alternatives rejected

- A merge of `dom/3bc-tests`: five files conflict, and its 3c tests use helpers that changed since.
- New numbers in 16.2 now: another lane edits that section.

## Open work

See [open-work.md](../open-work.md).
