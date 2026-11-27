"""The camera steps of a certify run (specs/certify.md 4.2 to 4.5, 8.3, 10.2), through the product calls of 2.2 only.

`run_session` runs in the session child, or in a test in a thread of the test process, with one
`CameraGroupManager`. The caller gives three callables:

- `begin(name)` returns after the caller sent the progress message of that check (9.6). It raises `Stopped` after
  a cancel or at the end of the budget.
- `done(row)` gives the result of one check.
- `fact(kind, value)` gives a fact for the caller: `touched` (labels that an apply opens), `before` (the first
  "before" values of a camera), `release` (a camera that is not healthy after the run, 8.3), `prior` (the reason
  of the checks of a camera that the session does not judge).

A camera that hung, crashed or was removed is never opened again in the run (2.3).
"""

import asyncio
import contextlib
import hashlib
import json
import logging
import re
import signal
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from skellycam.core.camera.capture.failure_codes import WEDGE_CODES
from skellycam.core.camera.capture.modes import rates_equal
from skellycam.core.camera.capture.source import CONTROL_NAMES, HASH_COUNT
from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.certify import catalog
from skellycam.core.ipc.frame_ring import FrameRingReader, ReadResult
from skellycam.core.recorders.videos.recording_info import RecordingInfo
from skellycam.core.take_recorder import folder_files, sidecar
from skellycam.core.take_recorder.placeholder import parse_sof

logger = logging.getLogger(__name__)

EXPOSURE_OPEN, EXPOSURE_CHANGED = -7, -8  # 4.3
TAKE_S = 3.0  # 4.5
SETTLE_LIMIT_S = 20.0
HASH_WAIT_S = 6.0
NEAR_ARRIVAL_MS = 200.0  # 10.2, cap 4.2
END_ROWS = 3  # 4.5: a gap in the last three rows is in `end_gaps`
WEDGED = {"hung": "hung", "process-ended": "crashed", "device-removed": "device-removed"}  # code: reason (10.5)


class Stopped(Exception):
    """A cancel or the end of the budget: no new check starts (C 2.4)."""


@dataclass
class Unit:
    """One camera to check."""
    label: str
    camera_id: str
    index: int
    base: tuple | None  # (width, height, rate) or None
    module: str
    device: object  # the CameraDeviceInfo of the detection


def row(name, result, reason=None, module=None, **numbers):
    out = dict(name=name, result=result, reason=reason)
    if module is not None:
        out["module"] = module
    numbers = {k: v for k, v in numbers.items() if v is None or isinstance(v, (bool, int, float, str))}
    if numbers:
        out["numbers"] = numbers
    return out


class RingWatch:
    """Reads each frame of one JPEG ring in a thread: the SHA-256 of each payload by its source frame number, the
    first 30 payloads and the last 3 (4.4, 4.6). No frame leaves the process; certify keeps no frame."""

    def __init__(self, name: str):
        self.reader = FrameRingReader.attach(name)
        self.hashes: dict[int, str] = {}
        self.first: list[bytes] = []
        self.last = deque(maxlen=3)
        self.flagged = 0  # frames that the JPEG check of capture flagged (no SOI or EOI, a driver error): damaged
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"certify ring {name}", daemon=True)
        self._thread.start()

    def _run(self):
        newest = self.reader.read_newest()
        number = max(0, newest.frame_number - 64) if newest.result is ReadResult.OK else 0
        while not self._stop.is_set():
            read = self.reader.read(number)
            if read.result is ReadResult.OK:
                payload = bytes(read.payload)
                self.hashes[read.source_frame_number] = hashlib.sha256(payload).hexdigest()
                if len(self.first) < HASH_COUNT:
                    self.first.append(payload)
                self.last.append(payload)
                number += 1
            elif read.result is ReadResult.NOT_YET_WRITTEN:
                time.sleep(0.002)
            elif read.result is ReadResult.CLOSED:
                return
            else:
                self.flagged += read.result is ReadResult.FLAGGED
                number += 1

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5)
        with contextlib.suppress(Exception):
            self.reader.close()


class NoWatch:
    """The ring watch of a `ready` camera whose ring certify could not attach (4.4): no frame and no hash. The camera
    goes on to the next steps; `native-jpeg:source-equals-ring` is then `not-run` `ring-lapped` [ADR-2HW5]."""
    first: tuple = ()
    last: tuple = ()
    hashes: dict = {}
    flagged = 0


NO_WATCH = NoWatch()


def luma(payloads) -> float | None:
    """The mean grey value of the frames, decoded at 1/8 size in memory (4.6)."""
    values = []
    for payload in payloads:
        image = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_REDUCED_GRAYSCALE_8)
        if image is not None:
            values.append(float(image.mean()))
    return round(sum(values) / len(values), 1) if values else None


def decodes(payload: bytes) -> bool:
    return (payload[:2] == b"\xff\xd8" and payload.rstrip(b"\x00")[-2:] == b"\xff\xd9"
            and cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_REDUCED_GRAYSCALE_8) is not None)


def _number(text: str | None) -> int | None:
    found = re.search(r"exit code (-?\d+)", text or "")
    return int(found.group(1)) if found else None


def failure_facts(failure: dict, data: dict, code: str, reason: str) -> dict:
    """3.5.3: the failure facts of a failure row, each only with a value [ADR-0Z6Q item 5]: `stage` of the failure object, `call`,
    `native_code` (with `native_domain`) and `first_fail_code` (when it differs from the code) of the diagnostics;
    `exit_code` from the failure of the status, on each `crashed` row (also `null`) and on a `hung` row that has it.
    The failure text is never copied (9.4)."""
    facts = dict(stage=(failure.get("stage") or "").replace(" ", "-") or None, call=data.get("call"),
                 native_code=data.get("native_code"))
    if facts["native_code"] is not None:
        facts["native_domain"] = data.get("native_domain")
    if data.get("first_fail_code") not in (None, code):
        facts["first_fail_code"] = data["first_fail_code"]
    out = {key: value for key, value in facts.items() if value is not None}
    exit_code = _number(failure.get("reason"))
    if reason == "crashed" or (reason == "hung" and exit_code is not None):
        out["exit_code"] = exit_code
    return out


class Session:
    def __init__(self, manager, units, work_folder, level, unix, begin, done, fact, sleep):
        self.manager, self.units, self.work = manager, list(units), Path(work_folder)
        self.level, self.unix = level, unix
        self.fact, self.sleep = fact, sleep
        self._begin, self._done = begin, done
        # 3.6.1 [U Q902]: the steps still compute the six checks of full only; a quick run sends no message or row of
        # them [KXQ9 item 2]
        self.left_out = set() if level == "full" else {f"{u.label}:{c}" for u in self.units for c in catalog.FULL_ONLY}
        self.hidden: str | None = None  # the left-out check that began last and has not ended [KXQ9 item 6]
        self.results: set[str] = set()  # the names of the checks that have a result
        self.watches: dict[str, RingWatch] = {}
        self.live: list[Unit] = []  # the cameras that are `ready`
        self.facts: dict[str, dict] = {}  # numbers that later checks of a camera use
        self.wedged: dict[str, str] = {}  # label: the reason of the wedge (2.3)
        self.left: dict[str, str] = {}  # label: the failure code of a live camera that left the run (3.6.1 B1)
        self.sent_before: set[str] = set()
        self.touched: list[Unit] = []
        self.closing: list[Unit] = []  # the cameras whose `live-at-close` the close judges [U Q646]
        self.takers: list[Unit] = []
        self.code_at_take: dict[str, str | None] = {}
        # cameras whose loop failed: label -> the code of the status failure (the main process writes it, so a late
        # dict of the camera cannot change it); no restore after a wedge code (unix 4.7) [Z7F3]
        self.failed: dict[str, str | None] = {}

    # ----- helpers -----

    def begin(self, name: str) -> None:
        self.hidden = name if name in self.left_out else None
        if self.hidden is None:
            self._begin(name)

    def done(self, result: dict) -> None:
        if result["name"] in self.left_out:
            if self.hidden == result["name"]:
                self.hidden = None
            return
        self.results.add(result["name"])
        self._done(result)

    def all_names(self, unit) -> dict:
        """The check names of a camera by step with the six of full only, for the steps that compute them by
        position (ready, settings, take); `begin` and `done` drop them in quick."""
        return catalog.camera_names(unit.label, unit.base, "full", self.unix)

    def next_shown(self, name: str) -> str | None:
        """The next check of the camera of `name`, in the order of the plan, that the level has and that has no
        result."""
        unit = next(u for u in self.units if name.startswith(u.label + ":"))
        shown = {n for names in catalog.camera_names(unit.label, unit.base, self.level, self.unix).values() for n in names}
        order = [n for names in self.all_names(unit).values() for n in names]
        return next((n for n in order[order.index(name) + 1:] if n in shown and n not in self.results), None)

    def status(self, unit):
        group = self.group()
        return group.cameras.orchestrator.camera_statuses[unit.camera_id].serialize() if group else {}

    def group(self):
        return next(iter(self.manager.camera_groups.values()), None)

    def diagnostics(self, unit) -> dict:
        group = self.group()
        live = group.camera_diagnostics.get(unit.camera_id) if group is not None else None
        return dict(live or self.manager.closed_diagnostics.get(unit.camera_id) or {})

    def config(self, unit, **changes) -> CameraConfig:
        width, height, rate = unit.base
        values = dict(camera_id=unit.camera_id, camera_index=unit.index, resolution=ImageResolution(width=width,
                      height=height), framerate=rate, exposure_mode="MANUAL", exposure=EXPOSURE_OPEN,
                      capture_fourcc="MJPG")
        values.update(changes)
        return CameraConfig(**values)

    def prior(self, unit, reason):
        self.fact("prior", (unit.label, reason))

    def leave_code(self, unit) -> tuple:
        """(code, failure object): a wedge code (`hung`, `process-ended`, `device-removed`) from the status of the
        camera or its last dict; for a live camera that failed or died, also another product code of its status
        (`stalled`, `stream-error`, ...) [ADR-0Z6Q item 1]. Else (None, the failure object)."""
        group = self.group()
        status = group.cameras.orchestrator.camera_statuses.get(unit.camera_id) if group is not None else None
        info = status.info_dict() if status is not None else {}
        failure = info.get("failure") or {}
        code = failure.get("code")
        if (code or self.diagnostics(unit).get("fail_code")) in WEDGED:
            return code or self.diagnostics(unit).get("fail_code"), failure
        if unit in self.live and code and status.state in ("failed", "dead"):
            return code, failure
        return None, failure

    def first_without_result(self, unit) -> str | None:
        """3.6.1 B1: the first check of a live camera, in the order of the plan, that has no result yet; the checks
        of the open are never one [ADR-0Z6Q items 2, 3]."""
        names = catalog.camera_names(unit.label, unit.base, self.level, self.unix)
        return next((name for step in ("ready", "settings", "take", "clock", "close") for name in names[step]
                     if name not in self.results), None)

    def scan(self, units, running=None) -> list:
        """2.3, 8.3: a camera that hung, whose process ended or that was removed is wedged. It is never opened again,
        its later checks are `prior-failure`, and phase G gives `camera-wedged`. 3.6.1 B1: a live camera (one that
        passed its open) that leaves the run with another product code (`stalled`, `stream-error`, ...) is not
        judged again; its later checks are `prior-check-failed`, and it counts as failed for the restore of 8.3
        [ADR-0Z6Q items 1, 4, 14]. A live camera that leaves gets one `fail` row with
        the reason of its code (`process-ended` gives `crashed`) and the failure facts of 3.5.3: on `running(unit)`,
        the check that ran, else on its first check with no result. Returns the units that are wedged or left."""
        found = []
        for unit in units:
            if unit.label not in self.wedged and unit.label not in self.left:
                code, failure = self.leave_code(unit)
                if code is None:
                    continue
                reason = WEDGED.get(code, code)
                if code in WEDGED:
                    self.wedged[unit.label] = reason
                    self.fact("release", (unit.label, "camera-wedged"))
                    self.prior(unit, "prior-failure")
                else:
                    self.left[unit.label] = reason
                    self.failed[unit.label] = code
                    self.prior(unit, "prior-check-failed")
                name = running(unit) if running is not None else self.first_without_result(unit) if (
                    unit in self.live) else None
                if name:
                    self.done(row(name, "fail", reason, unit.module,
                                  **failure_facts(failure, self.diagnostics(unit), code, reason)))
            found.append(unit)
        return found

    def send_before(self, unit):
        """8.3: the first "before" values of a camera go to the caller as soon as the diagnostics hold them, so that
        phase G can set them back after a kill."""
        if unit.label in self.sent_before:
            return
        data = self.diagnostics(unit)
        before = {name: dict(value=data.get(f"{name}_before"), auto=data.get(f"{name}_before_auto"))
                  for name in CONTROL_NAMES if data.get(f"{name}_before_auto") is not None}
        if before:
            self.sent_before.add(unit.label)
            self.fact("before", (unit.label, before))

    async def wait_states(self, units, states, limit_s=SETTLE_LIMIT_S):
        deadline = time.monotonic() + limit_s
        while time.monotonic() < deadline:
            wedged = {unit.label for unit in self.scan(units)}
            for unit in units:
                self.send_before(unit)
            if all(unit.label in wedged or self.status(unit).get("state") in states for unit in units):
                return
            await asyncio.sleep(0.01)

    # ----- steps -----

    async def run(self):
        try:
            self.detect_rows()
            await self.open_step()
            if self.live:
                await self.ready_step()
                await self.settings_step()
            await self.take_step()
            # Q646 [ADR-0Z6Q item 15]: look once more after the take rows; `live-at-close` of each camera that is
            # still live starts here and ends at the end of the close
            self.scan(self.live)
            for unit in self.takers:  # a camera whose take checks have their results [ADR-0Z6Q item 15]
                if (unit.label not in self.wedged and unit.label not in self.left
                        and f"{unit.label}:records:rows-complete" in self.results):
                    self.begin(f"{unit.label}:{catalog.LIVE}")
                    self.closing.append(unit)
        except Exception as error:
            # 3.6.1 [KXQ9 item 6]: a fault in a left-out check: the next check of the camera that the level has is
            # the running check, so the caller gives it the class name of the error
            if self.hidden and not isinstance(error, Stopped):
                with contextlib.suppress(Exception):  # never replaces the error of the session
                    following = self.next_shown(self.hidden)
                    if following is not None:
                        self._begin(following)
            raise
        finally:
            for watch in self.watches.values():
                watch.stop()
            await self.close_step()

    def detect_rows(self):
        for unit in self.units:
            modes = unit.device.supported_modes
            sizes = [(m.width, m.height) for m in modes]
            rates = [r for m in modes for r in m.framerates]
            numbers = dict(mjpg_sizes=len(sizes), has_720p30=any(m.width == 1280 and m.height == 720 for m in modes),
                           has_1080p30=any(m.width == 1920 and m.height == 1080 for m in modes),
                           has_60=any(r >= 59.9 for r in rates), max_fps=max(rates, default=None),
                           largest_w=max(sizes, key=lambda s: s[0] * s[1], default=(None, None))[0],
                           largest_h=max(sizes, key=lambda s: s[0] * s[1], default=(None, None))[1],
                           modes_read=unit.device.modes_read)
            self.begin(f"{unit.label}:detect")
            self.done(row(f"{unit.label}:detect", "record-only", None, unit.module, **numbers))
            self.begin(f"{unit.label}:detect:mjpg-mode")
            self.done(row(f"{unit.label}:detect:mjpg-mode", "pass" if sizes else "fail", None if sizes else
                          "no-mjpg-mode", unit.module, mjpg_sizes=len(sizes)))

    async def open_step(self):
        usable = []
        for unit in self.units:
            if unit.base is None:  # each check after the detection is a filled row `no-mjpg-mode` [ADR-0Z6Q item 11]
                self.prior(unit, "no-mjpg-mode")
            else:
                usable.append(unit)
        if not usable:
            return
        for unit in usable:
            for name in catalog.camera_names(unit.label, unit.base, self.level, self.unix)["open"]:
                self.begin(name)
        self.touched = usable
        self.fact("touched", [unit.label for unit in usable])
        t0 = time.monotonic()
        refused = None
        watching = asyncio.create_task(self.watch_rings(usable))
        try:
            try:
                await self.manager.create_or_update_camera_group({u.camera_id: self.config(u) for u in usable})
            except Exception as error:  # a refused request (RequestRefused) or a failed start of the group
                refused = type(error).__name__
                logger.warning(f"certify: the apply failed: {error!r}")
            seconds = round(time.monotonic() - t0, 2)
            if refused is None:
                await self.wait_states(usable, ("ready", "failed", "dead", "too_slow"))
        finally:  # also on a cancel or an error: no look after the open step attaches a watch that nothing stops
            watching.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watching
        # 4.4 [ADR-2HW5]: one more look, so a camera whose ring opened after the last look of `watch_rings` (it
        # waited in `waiting` for a hung camera and was `ready` at once) has its watch at the judge
        self.attach_watches(usable)
        for unit in usable:
            self.judge_open(unit, seconds, refused)

    async def watch_rings(self, units):
        """Attach a ring watch as soon as the ring of a camera exists, so that it sees the first frames after `ready`
        (the hash set of D-11 hashes them) before the ring laps them."""
        while True:
            self.attach_watches(units)
            for unit in units:
                self.send_before(unit)
            self.scan(units)  # a wedge in the open reaches the caller at once, also when a kill comes next
            await asyncio.sleep(0.005)

    def attach_watches(self, units):
        """A ring watch for each camera whose ring exists and that has none (4.4)."""
        group = self.group()
        for unit in units:
            info = group.ring_infos.get(unit.camera_id) if group is not None else None
            if info is not None and unit.label not in self.watches:
                with contextlib.suppress(FileNotFoundError, OSError, ValueError):
                    self.watches[unit.label] = RingWatch(info.jpeg_ring_name)

    def judge_open(self, unit, seconds, refused):
        self.send_before(unit)
        status = self.status(unit) if refused is None else {}
        failure = status.get("failure") or {}
        code, state = failure.get("code"), status.get("state")
        names = catalog.camera_names(unit.label, unit.base, self.level, self.unix)["open"]
        diagnostics = self.diagnostics(unit)
        first_frame = diagnostics.get("t_first_frame_ms")
        opened = dict(seconds_to_first_frame=None if first_frame is None else round(first_frame / 1000, 3),
                      seconds_to_ready=seconds, stage=(failure.get("stage") or "").replace(" ", "-") or None)
        rate_failed = code in ("rate-low", "rate-high")
        if refused is not None:  # the apply of certify was refused or failed: no camera is to blame
            self.done(row(names[0], "not-run", refused, unit.module, **opened))
            self.prior(unit, "prior-check-failed")
            return
        if code == "camera-in-use":
            self.done(row(names[0], "not-run", "camera-in-use", unit.module, **opened))
            self.prior(unit, "camera-in-use")
            return
        if failure:
            self.failed[unit.label] = code
        if state == "ready" or rate_failed:
            self.done(row(names[0], "pass", None, unit.module, **opened))
        else:
            reason = WEDGED.get(code) or code or ("not-ready" if state else "open-failed")
            self.done(row(names[0], "fail", reason, unit.module, exit_code=_number(failure.get("reason")), **opened))
            self.prior(unit, "prior-failure" if code in WEDGED else "prior-check-failed")
            if code in WEDGED and unit.label not in self.wedged:
                self.wedged[unit.label] = reason
                self.fact("release", (unit.label, "camera-wedged"))
            return
        mode = status.get("mode") or {}
        mode_fps = mode["fps_num"] / mode["fps_den"] if mode.get("fps_den") else None
        rate_numbers = dict(mode_fps=mode_fps, measured_fps=status.get("measured_fps"), luma_mean=None,
                            jpeg_kb_mean=None)
        if state == "ready":  # 4.4 [ADR-2HW5]: also with no ring watch (`NO_WATCH`)
            self.live.append(unit)
        elif unit.label in self.watches:
            self.watches.pop(unit.label).stop()
        self.facts[unit.label] = dict(rate=rate_numbers, mode=mode)
        if rate_failed:  # 4.6 [Q773]: a failed start-up rate check writes no ring frame; the D-3 key (P5) gives it
            rate_numbers["luma_mean"] = diagnostics.get("rate_luma_mean")
            self.done(row(names[1], *catalog.in_the_dark(("fail", code), rate_numbers["luma_mean"]), unit.module,
                          **rate_numbers))
        width, height, rate = unit.base
        granted = (mode.get("format") == "MJPG" and mode.get("width") == width and mode.get("height") == height
                   and mode_fps is not None and rates_equal(round(mode_fps, 2), round(rate, 2)))
        self.done(row(names[2], "pass" if granted else "fail", None if granted else "mode-not-granted", unit.module,
                      requested_fourcc="MJPG", granted_fourcc=mode.get("format"), granted_w=mode.get("width"),
                      granted_h=mode.get("height"), granted_fps_num=mode.get("fps_num"),
                      granted_fps_den=mode.get("fps_den")))
        if rate_failed:
            self.prior(unit, "prior-check-failed")

    async def wait_hashes(self, unit) -> dict:
        deadline = time.monotonic() + HASH_WAIT_S
        while True:
            data = self.diagnostics(unit)
            if (data.get("sha256_trigger") == "ready" and data.get(f"sha256_{HASH_COUNT - 1:02d}")) or (
                    time.monotonic() > deadline):
                return data
            await asyncio.sleep(0.02)

    async def ready_step(self):
        """The rate numbers, the "before" values, and the JPEG checks of the frames after the first `ready` (4.4)."""
        for unit in self.live:
            names = self.all_names(unit)
            data = await self.wait_hashes(unit)
            self.send_before(unit)
            watch = self.watches.get(unit.label, NO_WATCH)
            facts = self.facts[unit.label]
            payloads = list(watch.first)
            facts["luma_m7"] = luma(list(watch.last))
            numbers = dict(facts["rate"], luma_mean=facts["luma_m7"],
                           jpeg_kb_mean=round(sum(map(len, payloads)) / len(payloads) / 1000, 1) if payloads else None)
            self.done(row(names["open"][1], "pass", None, unit.module, **numbers))
            mode = facts["mode"]
            jpeg = dict(format=mode.get("format"), delivered=data.get("delivered"), frames_checked=len(payloads),
                        encoded_by_skellycam=data.get("encoded_by_skellycam"),
                        decoded_by_skellycam=data.get("decoded_by_skellycam"), dht_inserted=data.get("dht_inserted"),
                        dqt_distinct=data.get("dqt_distinct"), dqt_sha256=data.get("dqt_sha256"))
            facts["jpeg"] = jpeg
            self.begin(names["ready"][0])
            if self.scan([unit], running=lambda u: names["ready"][0]):
                continue
            native = mode.get("format") == "MJPG" and data.get("delivered") == "jpeg"
            self.done(row(names["ready"][0], "pass" if native else "fail", None if native else "no-native-jpeg",
                          unit.module, **jpeg))
            self.begin(names["ready"][1])
            encoded = data.get("encoded_by_skellycam")
            self.done(row(names["ready"][1], "pass" if encoded == 0 else "fail" if encoded else "not-run",
                          None if encoded == 0 else "no-native-jpeg" if encoded else "not-built", unit.module, **jpeg))
            self.begin(names["ready"][2])
            pairs = [(data.get(f"sha256_frame_{i:02d}"), data.get(f"sha256_{i:02d}")) for i in range(HASH_COUNT)]
            compared = [(watch.hashes.get(sfn), digest) for sfn, digest in pairs if sfn is not None and sfn in watch.hashes]
            differ = sum(1 for got, want in compared if got != want)
            result = ("fail", "jpeg-damaged") if differ else ("pass", None) if compared else ("not-run", "ring-lapped")
            self.done(row(names["ready"][2], *result, unit.module, frames_compared=len(compared), frames_differ=differ))

    async def settings_step(self):
        """4.3: one live change of each camera with manual exposure from -7 to -8."""
        manual, lacking = [], []
        # N1: a wedged or not-ready camera gets no change; the apply names no retry list, so the product opens no
        # `failed` or `dead` camera again, also one that dies after this scan (windows-capture.md 8.3) [Z7F3]
        self.scan(self.live)
        ready = [u for u in self.live if u.label not in self.wedged and u.label not in self.left
                 and self.status(u).get("state") == "ready"]
        for unit in self.live:
            if unit not in ready and unit.label not in self.wedged and unit.label not in self.left:
                self.prior(unit, "prior-check-failed")
        for unit in ready:
            warnings = self.status(unit).get("warnings") or []
            (lacking if any(w.get("kind") == "no_manual_exposure" for w in warnings) else manual).append(unit)
        for unit in lacking:
            for name in catalog.camera_names(unit.label, unit.base, self.level, self.unix)["settings"]:
                self.done(row(name, "not-run", "no-manual-exposure", unit.module))
        if not manual:
            return
        group = self.group()
        opened_at = {unit.label: group.configs[unit.camera_id].exposure for unit in manual}
        for unit in manual:
            for name in catalog.camera_names(unit.label, unit.base, self.level, self.unix)["settings"]:
                self.begin(name)
        await self.manager.create_or_update_camera_group(
            {u.camera_id: group.configs[u.camera_id].model_copy(update=dict(exposure=EXPOSURE_CHANGED)) for u in manual})
        readback = {u.label: ((self.status(u).get("controls") or {}).get("exposure") or {}).get("value") for u in manual}
        await self.wait_states(manual, ("ready", "too_slow", "failed", "dead"))
        luma_m8 = {u.label: luma(list(self.watches.get(u.label, NO_WATCH).last)) for u in manual}
        await asyncio.to_thread(time.sleep, 1.1)  # the control thread reads the controls each second (cap 11.4)
        later = {u.label: ((self.status(u).get("controls") or {}).get("exposure") or {}).get("value") for u in manual}
        self.scan(manual)  # a camera that left in the change: the running check is the read-back (B1)
        for unit in manual:
            names = self.all_names(unit)["settings"]
            if unit.label in self.wedged or unit.label in self.left:
                continue
            data = self.diagnostics(unit)
            m7, m8 = self.facts[unit.label]["luma_m7"], luma_m8[unit.label]
            ratio = round(m8 / m7, 3) if m7 and m8 is not None else None
            unit_kind = data.get("exposure_unit")
            numbers = dict(exposure_set=EXPOSURE_CHANGED, exposure_readback_open=opened_at[unit.label],
                           exposure_readback=readback[unit.label], exposure_later=later[unit.label], luma_at_m7=m7,
                           luma_at_m8=m8, luma_ratio=ratio, exposure_unit=unit_kind,
                           control_path=data.get("control_path"))
            read_ok = opened_at[unit.label] == EXPOSURE_OPEN and readback[unit.label] == EXPOSURE_CHANGED
            self.done(row(names[0], "pass" if read_ok else "fail", None if read_ok else "readback-differs", unit.module,
                          **numbers))
            if not read_ok:
                self.done(row(names[1], "not-run", "prior-check-failed", unit.module, **numbers))
                self.done(row(names[2], "not-run", "prior-check-failed", unit.module, **numbers))
                continue
            holds = later[unit.label] == EXPOSURE_CHANGED
            self.done(row(names[1], "pass" if holds else "fail", None if holds else "setting-reverted", unit.module,
                          **numbers))
            if names[2] in self.left_out:  # quick: running only while its own rule runs [KXQ9 item 6]
                self.begin(names[2])
            self.done(row(names[2], *catalog.image_effect(m7, m8, unit_kind), unit.module, **numbers))
            self.facts[unit.label]["control_path"] = data.get("control_path")

    async def take_step(self):
        """4.5: a take of 3 s with each camera that is `ready`, then the checks of its files."""
        group = self.group()
        self.scan(self.live)
        takers = [u for u in self.live if u.label not in self.wedged and u.label not in self.left
                  and self.status(u).get("state") == "ready"]
        self.takers = takers
        # the failure code of each camera at the record start: `live-at-close` counts only a new code [ADR-0Z6Q item 15]
        self.code_at_take = {u.label: (self.status(u).get("failure") or {}).get("code") for u in takers}
        for unit in self.live:
            if unit not in takers:
                self.prior(unit, "prior-check-failed")
                if failure := self.status(unit).get("failure"):
                    self.failed[unit.label] = failure.get("code")
        if group is None or not takers:
            self.fact("prior", ("group", "prior-check-failed"))
            return
        others = [camera_id for camera_id in group.camera_ids if camera_id not in {u.camera_id for u in takers}]
        if others:  # a camera that is not `ready` blocks a record start (8.3): it leaves the group
            await self.manager.create_or_update_camera_group(
                {camera_id: group.configs[camera_id].model_copy(update=dict(use_this_camera=False))
                 for camera_id in others})
        for name in catalog.TAKE:
            self.begin(name)
        statuses = group.cameras.orchestrator.camera_statuses
        before = {u.label: self.diagnostics(u) for u in takers}
        # 4.5: the replaced count of a window that holds each row of the take (from before the start to after the stop)
        replaced_start = {u.label: statuses[u.camera_id].replaced_count.value for u in takers}
        try:
            await self.manager.start_recording_all_groups(
                RecordingInfo(recording_name="take", recording_directory=str(self.work)))
        except Exception as error:
            text = str(getattr(error, "detail", error))
            self.done(row(catalog.TAKE[0], "fail", "fat-disk" if "FAT" in text else "take-not-finished"))
            self.fact("prior", ("group", "prior-check-failed"))
            for unit in takers:
                self.prior(unit, "prior-check-failed")
            return
        await asyncio.to_thread(self.sleep, TAKE_S)
        summary = (await self.manager.stop_recording_all_groups())[0]
        replaced = {u.label: statuses[u.camera_id].replaced_count.value - replaced_start[u.label] for u in takers}
        after = {u.label: self.diagnostics(u) for u in takers}
        files = self.take_files(summary, takers)
        self.group_take_rows(summary, takers, files)
        rows_complete = lambda u: self.all_names(u)["take"][3]  # noqa: E731
        wedged = {u.label for u in self.scan(takers, running=rows_complete)}
        for unit in takers:
            if unit.label in wedged:
                continue
            self.camera_take_rows(unit, files.get(unit.camera_id), replaced[unit.label], after[unit.label])
            self.clock_rows(unit, before[unit.label], after[unit.label])

    def take_files(self, summary, takers) -> dict:
        """{camera_id: (rows, mkv bytes)} of each camera of the take; a camera whose files cannot be read is absent."""
        folder = self.work / "take"
        out = {}
        try:
            manifest = json.loads((folder / "recording_manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return out
        self.facts["manifest"] = manifest
        for item in manifest.get("cameras", []):
            camera_id = item["camera_key"][:4]
            try:
                out[camera_id] = (sidecar.read_strict(folder / item["timing"]).rows, (folder / item["video"]).read_bytes())
            except (OSError, ValueError, KeyError):
                continue
        return out

    def group_take_rows(self, summary, takers, files):
        stop = summary.stop_response
        manifest = self.facts.get("manifest") or {}
        warnings = manifest.get("warnings", [])
        frame_count = stop.get("number_of_frames") or 0
        rate = takers[0].base[2]
        rows_by_camera = [files[u.camera_id][0] for u in takers if u.camera_id in files]
        spreads = sorted((max(t) - min(t)) / 1e6 for t in zip(*[[r.arrival_ns for r in rows] for rows in rows_by_camera])
                         if None not in t) if len(rows_by_camera) > 1 else []
        numbers = dict(cameras=len(takers), frame_count=frame_count, seconds=_finite(stop.get("total_duration_sec")),
                       rate=_finite(stop.get("mean_framerate")), file_system=folder_files.file_system(self.work),
                       spread_p50_ms=round(spreads[len(spreads) // 2], 2) if spreads else None,
                       spread_p95_ms=round(spreads[min(len(spreads) - 1, len(spreads) * 95 // 100)], 2) if spreads else None)
        errors = [w.get("detail") or "" for w in warnings if w.get("code") == "take_error"]
        if manifest.get("state") == "finished" and not errors:
            finished = ("pass", None)
        elif any("disk stall" in e for e in errors):
            finished = ("fail", "disk-stall")
        elif any("write" in e for e in errors):
            finished = ("fail", "write-error")
        else:
            finished = ("fail", "take-error" if errors else "take-not-finished")
        self.done(row(catalog.TAKE[0], *finished, **numbers))
        counts_ok = len(rows_by_camera) == len(takers) and all(len(rows) == frame_count for rows in rows_by_camera)
        self.done(row(catalog.TAKE[1], "pass" if counts_ok else "fail", None if counts_ok else "rows-differ", **numbers))
        missing = any(r.flags & sidecar.MISSING for rows in rows_by_camera for r in rows) or any(
            w.get("code") in ("camera_dead", "camera_file_short") for w in warnings)
        self.done(row(catalog.TAKE[2], "fail" if missing else "pass", "missing-rows" if missing else None, **numbers))
        enough = frame_count >= 0.8 * TAKE_S * rate
        self.done(row(catalog.TAKE[3], "pass" if enough else "fail", None if enough else "too-few-frames", **numbers))
        measured = numbers["rate"]
        rate_ok = measured is not None and abs(measured - rate) <= 0.01 * rate
        self.done(row(catalog.TAKE[4], "pass" if rate_ok else "fail", None if rate_ok else "group-rate-off", **numbers))

    def camera_take_rows(self, unit, files, replaced, diagnostics):
        names = self.all_names(unit)["take"]
        if files is None:
            self.prior(unit, "prior-check-failed")
            return
        rows, mkv = files
        blocks = [(r, mkv[r.byte_offset:r.byte_offset + r.byte_size]) for r in rows
                  if r.byte_offset is not None and r.byte_size]
        real = [(r, block) for r, block in blocks if not r.flags & sidecar.MISSING]
        watch = self.watches.get(unit.label, NO_WATCH)
        frames = list(watch.first) + [block for _, block in real]
        width, height, _ = unit.base
        jpeg = self.facts[unit.label].get("jpeg", {})
        self.begin(names[0])
        damaged = sum(1 for payload in frames if not decodes(payload)) + watch.flagged
        self.done(row(names[0], "fail" if damaged else "pass", "jpeg-damaged" if damaged else None, unit.module,
                      **dict(jpeg, frames_checked=len(frames) + watch.flagged, frames_damaged=damaged)))
        self.begin(names[1])
        sizes = []
        for payload in frames:
            with contextlib.suppress(ValueError, IndexError):
                layout = parse_sof(payload)
                sizes.append((layout.width, layout.height))
        wrong = sum(1 for size in sizes if size != (width, height))
        self.done(row(names[1], "fail" if wrong else "pass", "jpeg-size-differs" if wrong else None, unit.module,
                      frames_checked=len(sizes), frames_wrong_size=wrong))
        self.begin(names[2])
        compared = [(watch.hashes[r.source_frame_number], hashlib.sha256(block).hexdigest()) for r, block in real
                    if r.source_frame_number in watch.hashes]
        recorded = {diagnostics.get(f"sha256_frame_{i:02d}"): diagnostics.get(f"sha256_{i:02d}")
                    for i in range(HASH_COUNT)} if diagnostics.get("sha256_trigger") == "recording" else {}
        compared += [(recorded[r.source_frame_number], hashlib.sha256(block).hexdigest()) for r, block in real
                     if r.source_frame_number in recorded]
        differ = sum(1 for a, b in compared if a != b)
        result = ("fail", "jpeg-damaged") if differ else ("pass", None) if compared else ("not-run", "ring-lapped")
        self.done(row(names[2], *result, unit.module, frames_compared=len(compared), frames_differ=differ))
        sfns = [r.source_frame_number for r, _ in real]
        steps = [b - a - 1 for a, b in zip(sfns, sfns[1:])]
        cut = max(0, len(steps) - END_ROWS)
        gaps, end_gaps = sum(steps[:cut]), sum(steps[cut:])
        offsets = sorted((r.sample_ns - r.arrival_ns) / 1e6 for r, _ in real if r.sample_ns is not None
                         and r.arrival_ns is not None and r.sample_ns > 0)
        numbers = dict(rows=len(rows), missing=len(rows) - len(real), gaps=gaps, replaced=replaced, end_gaps=end_gaps,
                       sample_minus_arrival_p50_ms=round(offsets[len(offsets) // 2], 3) if offsets else None,
                       sample_minus_arrival_p95_ms=round(offsets[min(len(offsets) - 1, len(offsets) * 95 // 100)], 3)
                       if offsets else None)
        self.begin(names[3])
        complete = numbers["missing"] == 0
        self.done(row(names[3], "pass" if complete else "fail", None if complete else "missing-rows", unit.module,
                      **numbers))
        self.begin(names[4])
        failures = sum(1 for _, block in blocks if cv2.imdecode(np.frombuffer(block, np.uint8),
                                                               cv2.IMREAD_REDUCED_GRAYSCALE_8) is None)
        failures += len(rows) - len(blocks)
        self.done(row(names[4], "fail" if failures else "pass", "frame-not-decodable" if failures else None,
                      unit.module, **dict(numbers, decode_failures=failures)))
        self.begin(names[5])
        explained = catalog.gaps_explained(gaps, replaced)
        self.done(row(names[5], "pass" if explained else "fail", None if explained else "gaps-unexplained", unit.module,
                      **numbers))

    def clock_rows(self, unit, before, data):
        """10.2: the clock, the sequence and the time gaps, from the diagnostics of the source (on Linux and macOS in
        quick, on each system in full). A key that the source does not fill gives `not-run` `not-built`; a `clock` of
        `unknown` (the source cannot tell its clock: Media Foundation) gives `not-run` `clock-unknown` [Z7F3]."""
        names = catalog.camera_names(unit.label, unit.base, self.level, self.unix)["clock"]
        if not names:
            return
        clock = data.get("clock")
        self.begin(names[0])
        result = (("pass", None) if clock in ("monotonic", "host") else ("fail", "clock-base-differs")
                  if clock in ("realtime", "device") else ("not-run", "clock-unknown") if clock == "unknown"
                  else ("not-run", "not-built"))
        self.done(row(names[0], *result, unit.module, clock=clock, tstamp_src=data.get("tstamp_src"),
                      ts_conversion=data.get("ts_conversion"), sample_time_kept=data.get("sample_time_kept")))
        self.begin(names[1])
        later = data.get("later_than_arrival")
        result = ("not-run", "not-built") if later is None else ("pass", None) if later == 0 else (
            "fail", "sample-after-arrival")
        self.done(row(names[1], *result, unit.module, later_than_arrival=later,
                      sample_minus_arrival_p5_ms=data.get("sample_minus_arrival_p5_ms")))
        self.begin(names[2])
        p95 = data.get("sample_minus_arrival_p95_ms")
        result = ("not-run", "not-built") if p95 is None else ("pass", None) if abs(p95) <= NEAR_ARRIVAL_MS else (
            "fail", "sample-too-early")
        self.done(row(names[2], *result, unit.module, sample_minus_arrival_p50_ms=data.get("sample_minus_arrival_p50_ms"),
                      sample_minus_arrival_p95_ms=p95))
        available = data.get("sequence_available")
        long_now, long_before = data.get("long_intervals"), before.get("long_intervals")
        sequence_numbers = dict(sequence_available=available, sequence_gaps=data.get("sequence_gaps"),
                                sequence_lost=data.get("sequence_lost"), long_intervals=long_now,
                                long_intervals_with_seq_gap=data.get("long_intervals_with_seq_gap"),
                                discontinuity_flags=data.get("discontinuity_flags"),
                                drops_reported=data.get("drops_reported"))
        if available is False:
            self.done(row(names[3], "not-run", "no-sequence", unit.module, **sequence_numbers))
            self.begin(names[4])
            result = (("not-run", "not-built") if long_now is None or long_before is None else ("pass", None)
                      if long_now == long_before else ("fail", "frame-gaps"))
            self.done(row(names[4], *result, unit.module, long_intervals=long_now, drops_reported=data.get(
                "drops_reported"), frames=data.get("frames")))
            return
        self.begin(names[3])
        with_gap = data.get("long_intervals_with_seq_gap")
        result = (("not-run", "not-built") if available is None or long_now is None or with_gap is None else
                  ("pass", None) if long_now == with_gap else ("fail", "sequence-unreliable"))
        self.done(row(names[3], *result, unit.module, **sequence_numbers))
        self.done(row(names[4], "not-run", "has-sequence" if available else "not-built", unit.module))

    async def close_step(self):
        """Phase G of quick (8.3): the close restores each camera. `camera-not-restored`: a restore that failed, or a
        camera whose loop failed with a wedge code after its controls were set, because the product does not restore
        it (unix-capture.md 4.7) [Z7F3]; the product restores a camera that failed for another reason. (The close
        dict of a good camera can come after the close returns, so a missing
        `restore_ok` alone proves nothing.) A wedge code in the last dict gives `camera-wedged`."""
        group = self.group()
        if group is None:
            return
        self.fact("closing", None)  # 9.3: from here the caller does not kill the tree before the close limit
        workers = dict(group.cameras.camera_workers)
        await self.manager.close_all_camera_groups()
        late = self.late_codes(group, workers)
        for label, (code, _, _) in late.items():
            if code in WEDGED:  # 2.3: a camera that hung or whose process ended at the close is wedged (replug)
                self.wedged[label] = WEDGED[code]
                self.fact("release", (label, "camera-wedged"))
            else:
                self.failed[label] = code  # as a B1 row [ADR-0Z6Q item 14]
        for unit in self.touched:  # also a camera that left the group before the take: its last dict is here
            data = group.camera_diagnostics.get(unit.camera_id, {})
            if unit.label in self.wedged:
                continue
            if data.get("fail_code") in WEDGED:
                self.wedged[unit.label] = WEDGED[data["fail_code"]]
                self.fact("release", (unit.label, "camera-wedged"))
            elif data.get("restore_ok") is False or (
                    unit.label in self.failed and (self.failed[unit.label] or data.get("fail_code")) in WEDGE_CODES
                    and data.get("restore_ok") is not True
                    and any(data.get(f"{name}_before_auto") is not None for name in CONTROL_NAMES)):
                self.fact("release", (unit.label, "camera-not-restored"))
        for unit in self.closing:  # 3.6.2 [U Q646]: the camera gave no product failure code up to the end of the close
            name = f"{unit.label}:{catalog.LIVE}"
            if name in self.results:
                continue
            if unit.label in late:
                code, failure, data = late[unit.label]
                reason = WEDGED.get(code, code)
                self.done(row(name, "fail", reason, unit.module, **failure_facts(failure, data, code, reason)))
            else:
                self.done(row(name, "pass", None, unit.module))

    def late_codes(self, group, workers) -> dict:
        """label: (code, failure object, last dict) of each camera of `closing` with a product failure code after
        the close [U Q646, ADR-0Z6Q item 15]: `hung` when the status has the flag `hung`; else a code of its status,
        else of its last dict, that it did not have at the record start; else from the exit code of its camera
        process: -SIGTERM or -SIGKILL (the product ended a close that did not return) is `hung`, each other code that
        is not 0 is `process-ended`."""
        out = {}
        statuses = group.cameras.orchestrator.camera_statuses
        for unit in self.closing:
            if unit.label in self.wedged or unit.label in self.left:
                continue
            status = statuses.get(unit.camera_id)
            info = {}
            with contextlib.suppress(Exception):
                info = (status.info_dict() or {}) if status is not None else {}
            failure = info.get("failure") or {}
            data = dict(group.camera_diagnostics.get(unit.camera_id) or {})
            code = failure.get("code") or data.get("fail_code")
            if code is not None and code == self.code_at_take.get(unit.label):
                code = None  # not new since the record start
            if info.get("hung"):
                code = "hung"
            elif not code:
                exit_code = None
                with contextlib.suppress(Exception):
                    exit_code = workers[unit.camera_id].worker.exitcode
                ended_by_product = (-signal.SIGTERM, -getattr(signal, "SIGKILL", 9))
                if isinstance(exit_code, int) and exit_code in ended_by_product:
                    code, failure = "hung", dict(stage="close")
                elif isinstance(exit_code, int) and exit_code != 0:
                    code, failure = "process-ended", dict(stage="close", reason=f"exit code {exit_code}")
            if code:
                out[unit.label] = (code, failure, data)
        return out


def _finite(value):
    return value if isinstance(value, (int, float)) and value == value else None


async def run_session(manager, units, work_folder, level, unix, begin, done, fact, sleep=time.sleep) -> None:
    await Session(manager, units, work_folder, level, unix, begin, done, fact, sleep).run()
