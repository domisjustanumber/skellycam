# CQ2X — Decisions of the user on the overlaps of certify with freemocap

**Status:** accepted, 2026-11-25 (user; the supervisor asked Q778, Q779 and
Q789 to Q795 in a grilling session; the answer was "agree to all", after freemocap-e7 answered the five overlaps; commit to dom/exclusive-access-spec). The drafts
that state its rules wait for the acceptance of the user; the entry is absorbed in that commit.

## Decision

1. **Q778 (session Q50).** The overlaps of section 12 of the certify spec go into the open work, to settle with the
   freemocap session. The user: "there is now a session open in freemocap".
2. **Q779 (Q51).** The supervisor sends the five overlaps to freemocap-e7 and asks for agree or counter on each. Done:
   freemocap-e7 agreed to 1, 2, 3 and 5, and countered on 4 (settled by Q796 of
   [ADR-AA4X](AA4X-decisions-of-the-user-on-exclusive-access-of-a-camera.md)).
3. **Q789 (Q61).** (1) freemocap keeps its `data-folder` check (write, read back and delete a probe file; record the
   free space); skellycam owns the disk speed and the take load, and records no free space. (2) No whole-system CPU
   benchmark anywhere (freemocap ADR-4TK3). (3) freemocap makes no recording of its own; its full check `recording`
   downloads and cuts the sample recording, and both specs note the name clash; its post-processing checks use
   known-good media only, never a skellycam take, which holds private frames. (5) freemocap owns the new-model pop-up,
   the crash progress file (built) and the notice "wedged, please replug"; skellycam owns the checks and the record.
4. **Q790 (Q62).** A public call that answers "is this camera model checked on this system?", for the pop-up; and
   each `progress` message carries the complete state, with a `step` that names the running check. Spec and tests
   first, in the certify lane of Q772.
5. **Q791 (Q63).** When certify runs inside freemocap, freemocap asks for the macOS camera permission, and the certify
   of skellycam never asks again. The stand-alone skellycam app asks for itself (decided on 2026-11-20).
6. **Q792 (Q64).** A small public constructor for a camera group with no `CameraManager`, for the `realtime-session`
   check of freemocap; the busy check of skellycam ignores such a group. Spec and test first, in the lane of Q772.
7. **Q793 (Q65).** No third copy of host facts: freemocap writes the host block, and skellytracker owns the hardware
   facts. The report of skellycam keeps only camera, USB and backend facts, and drops each field that those two have.
   The check found that freemocap's host block (through `probe_host` of skellytracker) has `os.release` on Linux, so
   the kernel release of `system:kernel` is a third copy and goes. [NV] that it is `platform.release()`.
8. **Q794 (Q66).** The list of forbidden content of a merged report moves from freemocap's `report_file.py` into the
   certify contract (skellycertify). The tests of skellycam check its camera rows against the list of the contract.
   The owner of the contract decides the wording.
9. **Q795 (Q67).** The `fork` of freemocap's certify child on Linux stays in the wider review of freemocap on Linux
   ([ADR-T34M](T34M-decision-of-the-user-on-the-start-method-of-camera-processes.md)). The candidate fix sent to
   freemocap-e7: `ManagedProcess` of skellycam takes a multiprocessing context, so that freemocap can pass `spawn`.

## Reason

Each rule then has one owner. The subclass of `CameraGroup` in freemocap breaks whenever the internals change. A rule
of privacy in the code of one app cannot bind the other modules.

## Open work

[open-work.md](../open-work.md)
