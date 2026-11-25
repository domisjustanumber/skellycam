# AA4X — Decisions of the user on exclusive access of a camera

**Status:** absorbed into [`specs/windows-capture.md#21-exclusive-access-of-a-camera`](../../specs/windows-capture.md#21-exclusive-access-of-a-camera),
[`specs/unix-capture.md#413-exclusive-access-of-a-camera-lands-with-phase-7`](../../specs/unix-capture.md#413-exclusive-access-of-a-camera-lands-with-phase-7),
[`specs/certify.md#97-cameras-busy-u-a-c-25`](../../specs/certify.md#97-cameras-busy-u-a-c-25),
[`specs/certify.md#20-exclusive-access-the-public-calls-for-freemocap-and-the-light-data`](../../specs/certify.md#20-exclusive-access-the-public-calls-for-freemocap-and-the-light-data),
2026-11-25 (commit to dom/exclusive-access-spec, Q813 of ADR-5PAR; was accepted, 2026-11-25 (user; the supervisor asked Q758, Q768, Q769, Q771, Q781 to Q788, Q796, Q797 and Q799 in a grilling session)).

## Decision

Where the user wrote his own words, they are quoted. Each other item is "yes" to the recommendation.

1. **Q758 (session Q30).** The user: "other processes on the machine might be holding the camera too. What are your
   thoughts - do we need to test for that, or just ask the user to close other processes?" Q768 answers it.
2. **Q768 (Q40).** skellycam scans no processes ahead and never closes a program. It detects at the open, and one
   line asks the person before a take and before certify: "Close other camera apps (for example LogiTune, Razer
   Synapse, Teams, browser tabs)". A "who" hint where the OS gives one. A read-back of the controls at the take start,
   so that a setting that another app changed shows as a warning.
3. **Q769 (Q41).** The user: "if we don't get exclusive use, it's an in-use result and we don't run the test. We need
   exclusive control of the camera".
4. **Q771 (Q43).** Exclusive control is a rule of the product too. A camera that skellycam does not hold exclusively
   is `camera-in-use` and is not used for a take.
5. **Q781 (Q53).** No OS gives a full lock. skellycam holds the strongest lock of each OS: Windows the controlling mode
   plus the activity monitor; Linux the buffer ownership plus the RECORD priority; macOS `lockForConfiguration` for
   the whole take plus the in-use flag.
6. **Q782 (Q54).** The user: "Q54 b": only a streaming other process means "in use". An attached process that does
   not stream (for example LogiTuneAgent) gives a warning with its name.
7. **Q783 (Q55).** A loss of exclusive use during a take: the take keeps recording, the UI warns at once with the name
   where the OS gives it, and the take records each affected interval ("shared from t1 to t2") and the control
   changes that it saw.
8. **Q784 (Q56).** Windows 11 22621 or later: the control monitor for each control, for the whole take. Older builds:
   no poll during a take; the activity monitor and one read-back at the take start and at the take end.
9. **Q785 (Q57).** Add `0x80070020` to the in-use set. At a failed open, the activity monitor tells "in use" from "USB
   bandwidth". Certify gets a case where a program that is not skellycam holds the camera.
10. **Q786 (Q58).** Linux: the RECORD priority right after the open (`EBUSY` from it is "in use"); `V4L2_EVENT_CTRL`
    for control changes by others; names through `/proc`, same user only; the gap of raw extension-unit queries is
    documented.
11. **Q787 (Q59).** macOS, reversing M-11: refuse a camera whose in-use flag is set before the open; hold
    `lockForConfiguration` for the whole take; watch the in-use flag with the marks of Q783; a certify check of
    whether CoreMediaIO hog mode can be set on UVC cameras, and phase 7 uses it if it can.
12. **Q788 (Q60).** Certify: a camera that another program holds at the run start is `not-run` `camera-in-use`;
    `<label>:in-use` passes only on a refusal with the in-use reason, and `shared` is a fail; a new check
    `<label>:in-use-mid-take` passes when the product warns and marks the interval.
13. **Q796 (Q68).** Only the processes of the same camera group are own processes. A camera that any other process
    holds, also another skellycam group such as the one of freemocap, is `not-run` `camera-in-use`. `cameras-busy`
    stays only for an open group in the calling process. freemocap still closes its own groups before a run.
14. **Q797 (Q69).** The gap of Q782 is accepted: on a build with no control monitor, a change by an attached tool is
    found only by the read-back at the take end. The warning at the take start names the tool.
15. **Q799 (Q71).** One spec agent drafts the changes to `windows-capture.md`, `unix-capture.md` and `certify.md`, then
    an independent review, then the user accepts them before any test or code. The Windows build lane starts after
    that; the Linux and macOS parts land with phase 7.

## Reason

The user needs settings that do not change during a take. On Windows a shared reader can change exposure during a
take, and the product did not notice it. LogiTuneAgent held all four cameras on the test machine, and a Kiyo Pro
wedged while Signal held the C930e.

## Evidence

The research of 2026-11-25, with its tags and sources:
[evidence/AA4X-exclusive-access-research.md](../evidence/AA4X-exclusive-access-research.md).

## Alternatives rejected

- Stop the take when exclusive use is lost: it loses the whole recording.
- An attached process that does not stream is "in use" (Q782 answer (a)): the user chose (b).
- A poll of the controls during a take on older builds: each read is a request, and the Kiyo Pro wedges around
  bursts of control requests.

## Open work

[open-work.md](../open-work.md)
