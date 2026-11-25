"""The names, the check list, the summary item rule, the gate, the name cleaning and the local record of a certify
run of skellycam (specs/certify.md 2.5, 3, 9.4, 11.3). Pure functions: no camera, no process.

The plan and the run use the same check list (`planned_checks`), so `total` of the plan is the count of the checks
that the run reports.
"""

import json
import os
import platform
import re
from pathlib import Path

from skellycam.core.camera.capture import camera_checks
from skellycam.core.camera.capture.modes import at_floor, auto_rate

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}$")  # C 3.4
BACKENDS = {"Windows": "media-foundation", "Linux": "v4l2", "Darwin": "avfoundation"}
DEFAULT_BASE = (1280, 720, 30.0)  # 3.4 `<base>`; the plan uses it when the modes were not read

# The quick checks of one camera (3.4, 4.2 to 4.5), by the step of the run that gives them (4.1).
DETECT = ("detect", "detect:mjpg-mode")
OPEN = ("opens", "rate", "modes:granted")  # `modes:granted` gets `:<base>`
AFTER_READY = ("native-jpeg:format", "native-jpeg:not-reencoded", "native-jpeg:source-equals-ring")
SETTINGS = ("settings-stick:readback", "settings-stick:holds", "settings-stick:image-effect")
AFTER_TAKE = ("native-jpeg:valid", "native-jpeg:size", "native-jpeg:ring-equals-mkv",
              "records:rows-complete", "records:blocks-decode", "records:gaps-explained")
CLOCK = ("clock:base", "clock:before-arrival", "clock:near-arrival", "sequence", "time-gaps")  # 10.2, 10.6
LIVE = "live-at-close"  # 3.6.2 [U Q646]: the last check of each camera [ADR-0Z6Q item 15]
TAKE = tuple(f"group:take:{c}" for c in ("finished", "csv-rows", "no-missing", "frame-count", "rate"))
QUICK_NOT_BUILT = ("group:open",)  # with the retry alone of 4.2
SELF_QUICK = ("self:hang-100ms:gap", "self:hang-100ms:hard-end")  # 7: not built in this step
# The camera block of `full` (5, 8.2, 10.2) that is not built, without the checks of a mode above `<base>`.
FULL_CAMERA_NOT_BUILT = (
    "identity:stable", "identity:unique", "controls", "controls:exposure-scale",
    "exposure:{base}", "exposure:{base}:readback", "settings-stick:each-open", "auto-exposure:searched:{base}",
    "auto-exposure:holds-rate:{base}", "control:gain", "control:focus", "auto-off:ae", "auto-off:af",
    "auto-off:ae-stays", "group-open", "timestamps", "in-use", "cycles")  # Q624 dropped `timings` and four controls
FULL_NOT_BUILT = (
    *(f"group:take-30:{c}" for c in ("finished", "csv-rows", "no-missing", "frame-count", "rate")), "group:contention",
    "system:usb", "system:disk", "system:disk-benchmark",  # Q624a, b: no `system:backend`, `system:virtual-cameras`
    "self:crash-take:finishes", "self:crash-take:equal-rows", "self:crash-take:others-record",
    "self:server-gone:ends", "self:server-gone:files-finished", "self:server-gone:source-closed",
    "self:stall:take-error", "self:stall:others-finished", "self:stall:stalled-failed", "self:stall:no-healthy-dead",
    "self:idle-cpu", "self:ring:torn", "self:ring:lapped", "self:scale-3", "self:scale-12",  # Q624f
    *(f"group:take-60:{c}" for c in ("finished", "csv-rows", "no-missing", "frame-count", "rate")))
SYSTEM_NOT_BUILT = {"media-foundation": ("system:camera-apps",), "v4l2": ("system:kernel", "system:camera-access"),
                    "avfoundation": ("system:camera-access", "system:video-effects")}
GATE_STEPS = ("opens", "mode", "rate", "native-jpeg", "timestamps", "sequence", "records", "no-hang")
HANG_REASONS = ("hung", "crashed", "stalled")  # the reasons that fail `<model>:gate:no-hang` (3.6.1 B1)

# The item groups of 3.4: Open, Rate and Records decide `fail`.
FATAL = ("opens", "rate", "modes:granted", "records:rows-complete", "records:blocks-decode", "records:gaps-explained",
         LIVE)
ITEM = FATAL + SETTINGS + ("native-jpeg:format", "native-jpeg:not-reencoded", "native-jpeg:valid",
                           "native-jpeg:size", "native-jpeg:ring-equals-mkv", "native-jpeg:source-equals-ring")

NOTICE_CODES = ("camera-wedged", "camera-not-restored")
DARK_LUMA, BRIGHT_LUMA = 24, 230  # 4.6, 4.3; not calibrated
TIME_UNIT_RATIO, UNITLESS_RATIO = 0.85, 0.97  # 4.3; not calibrated
UNITLESS = ("ev", "native", "native-data")  # 10.2: the exposure routes with no time unit
# Each reason code that this code can give (T-CERT-30); each one is in skellycam/REASON_CODES.md.
REASON_CODES = (
    "timed-out", "crashed", "bad-output", "hung-at-exit", "cancelled", "not-built", "no-version", "no-commit",
    "modified-tree", "cameras-busy", "over-budget", "backend-missing", "no-camera", "same-model", "ring-lapped",
    "no-mjpg-mode", "camera-in-use", "hung", "rate-low", "rate-high", "too-dark", "too-bright", "readback-differs",
    "setting-reverted", "no-image-effect", "no-native-jpeg", "jpeg-damaged", "jpeg-size-differs", "mode-not-granted",
    "take-not-finished", "take-error", "rows-differ", "missing-rows", "gaps-unexplained", "group-rate-off",
    "too-few-frames", "frame-not-decodable", "fat-disk", "disk-stall", "write-error", "clock-base-differs",
    "clock-unknown", "sample-after-arrival", "sample-too-early", "sequence-unreliable", "no-sequence", "has-sequence", "frame-gaps",
    "gate-check-failed", "gate-check-not-run", "no-manual-exposure", "prior-failure", "prior-check-failed",
    "camera-wedged", "camera-not-restored", "not-deleted", "no-frame",
    # the product failure codes of unix-capture.md 4.6.3 that a failed open gives as its reason
    "not-found", "no-access", "no-permission", "usb-bandwidth", "no-mode", "below-floor", "open-failed",
    "first-frame-timeout", "not-ready", "control-failed", "device-removed", "stalled",
    "previous-process-alive", "stream-error", "format-changed", "start-method-fork")
RISK = ("The full run opens each camera many times and at each of its modes. A camera can stop answering until it is "
        "unplugged and plugged in again. The run puts back the settings of each camera at the end.")
RISK_MACOS = ("The last part of the full run sends direct USB requests to each camera model and can make a camera stop "
              "until it is replugged.")


def system_backend() -> str:
    return BACKENDS.get(platform.system(), "v4l2")


def device_key(device) -> str | None:
    """`vvvv:pppp`, or None with no USB ids (3.4)."""
    if device.vendor_id is None or device.product_id is None:
        return None
    return f"{device.vendor_id:04x}:{device.product_id:04x}"


def model_name(backend: str, vendor_id: int | None, product_id: int | None) -> str:
    """`cam.<backend>.<vid>-<pid>` (3.1)."""
    ids = "nousb-nousb" if vendor_id is None or product_id is None else f"{vendor_id:04x}-{product_id:04x}"
    return f"cam.{backend}.{ids}"


def label(backend: str, vendor_id: int | None, product_id: int | None, n: int) -> str:
    return f"{model_name(backend, vendor_id, product_id)}.{n}"


def camera_labels(devices, backend: str) -> list:
    """(label, device) of each real camera, `<n>` for each model in the detection order (3.1)."""
    out, counts = [], {}
    for device in devices:
        if device.virtual:
            continue
        model = model_name(backend, device.vendor_id, device.product_id)
        out.append((f"{model}.{counts.get(model, 0)}", device))
        counts[model] = counts.get(model, 0) + 1
    return out


def mode_name(width: int, height: int, rate: float) -> str:
    """`<w>x<h>@<rate>`, the rate rounded as the mode list rounds it (3.1)."""
    return f"{width}x{height}@{round(rate, 2):g}"


def base_mode(device) -> tuple | None:
    """`<base>` of 3.4: 1280x720 at the floor, else the largest MJPG size below it in area with a rate at the floor;
    None for a camera with neither. With no mode list read, the default (the plan)."""
    sizes = {(m.width, m.height): [r for r in m.framerates if at_floor(r)] for m in device.supported_modes}
    sizes = {size: rates for size, rates in sizes.items() if rates}
    if not device.modes_read and not sizes:
        return DEFAULT_BASE
    if (1280, 720) in sizes:
        return (1280, 720, auto_rate(sizes[(1280, 720)]))
    below = [size for size in sizes if size[0] * size[1] < 1280 * 720]
    if not below:
        return None
    size = max(below, key=lambda s: s[0] * s[1])
    return (*size, auto_rate(sizes[size]))


def granted_name(base) -> str:
    return f"modes:granted:{mode_name(*base)}" if base else "modes:granted"


def camera_names(unit_label: str, base, level: str, unix: bool) -> dict:
    """The check names of one camera by step (4.1): {step: [name, ...]}."""
    open_names = [f"{unit_label}:opens", f"{unit_label}:rate", f"{unit_label}:{granted_name(base)}"]
    names = {
        "detect": [f"{unit_label}:{c}" for c in DETECT],
        "open": open_names,
        "ready": [f"{unit_label}:{c}" for c in AFTER_READY],
        "settings": [f"{unit_label}:{c}" for c in SETTINGS],
        "take": [f"{unit_label}:{c}" for c in AFTER_TAKE],
        "clock": [f"{unit_label}:{c}" for c in CLOCK] if unix or level == "full" else [],
        "close": [f"{unit_label}:{LIVE}"],
    }
    return names


def planned_checks(level: str, units: list, backend: str) -> list:
    """(name, module) of each check of the run that has code, in the order of the report. `units`: (label, base,
    module) of each camera to check, in the detection order. A check with no code is not planned and gives no row: it
    is in `not_built` (3.6.1). A check of the camera block of `full` for a second unit of a model gives no row
    either (no `same-model`)."""
    unix = backend != "media-foundation"
    by_unit = [(lab, module, camera_names(lab, base, level, unix)) for lab, base, module in units]
    models = {}
    for lab, _, module in units:
        models.setdefault(lab.rsplit(".", 1)[0], module)
    out = [("detect", None)]
    for step in ("detect", "open", "ready", "settings"):
        out += [(name, module) for _, module, names in by_unit for name in names[step]]
    if units:
        out += [(name, None) for name in TAKE]
    for step in ("take", "clock", "close"):
        out += [(name, module) for _, module, names in by_unit for name in names[step]]
    out += [(f"{model}:units", module) for model, module in models.items()]
    if level == "full":
        out += [(f"{model}:gate{step}", module) for model, module in models.items()
                for step in [f":{s}" for s in GATE_STEPS] + [""]]
    return out


def not_built(level: str, units: list, backend: str) -> dict:
    """3.6.3 `details.not_built`: the names of the checks with no code, `camera` without `<label>:` and with `base`
    for the mode of `<base>`, `run` the group, system and self checks; each name one time, sorted."""
    run = set(QUICK_NOT_BUILT + SELF_QUICK) if units else set()
    camera = set()
    if level == "full":
        run.update(FULL_NOT_BUILT + SYSTEM_NOT_BUILT.get(backend, ()))
        for _, base, _ in units:
            camera.update(c.format(base="base") for c in FULL_CAMERA_NOT_BUILT if base or "{base}" not in c)
    return {"camera": sorted(camera), "run": sorted(run)}


def in_the_dark(result: tuple, luma) -> tuple:
    """4.6 [Q773]: a light-dependent check that fails while the mean grey value is below DARK_LUMA is `not-run`
    `too-dark`. A pass stays `pass`. With no brightness (no frame) the result stays."""
    if result[0] == "fail" and luma is not None and luma < DARK_LUMA:
        return ("not-run", "too-dark")
    return result


def image_effect(luma_m7, luma_m8, exposure_unit) -> tuple:
    """4.3, 4.6 [Q773]: (result, reason) of `settings-stick:image-effect`. No frame at -7 or -8 is `no-frame`; above
    BRIGHT_LUMA at -7 is `too-bright`; the image gets darker by the limit of the route, else the dark rule."""
    if luma_m7 is None or luma_m8 is None:
        return ("not-run", "no-frame")
    if luma_m7 > BRIGHT_LUMA:
        return ("not-run", "too-bright")
    limit = UNITLESS_RATIO if exposure_unit in UNITLESS else TIME_UNIT_RATIO
    if luma_m7 > 0 and luma_m8 / luma_m7 < limit:
        return ("pass", None)
    return in_the_dark(("fail", "no-image-effect"), luma_m7)


def seconds_estimate(level: str, cameras: int, models: int) -> int:
    """4.7 for quick (0 with no camera to check); 16 for full."""
    if level == "quick":
        return min(30, -(-(80 + cameras) // 4) + 10) if cameras else 0
    return 265 + 100 * models


# ----- the summary item and the gate (3.3, 3.4, 11.3) -----

def _label_of(unit: dict) -> str:
    """The label of the rows of one unit (a label holds no `:`; 3.1)."""
    return next(iter(unit)).split(":", 1)[0]


def _not_reached(unit: dict) -> dict | None:
    return unit.get(f"{_label_of(unit)}:not-reached")


def _suffix(name: str, unit_label: str) -> str:
    return name[len(unit_label) + 1:]


def _base_granted(unit: dict) -> str | None:
    """The name of the `modes:granted` check of `<base>`: the first one of the unit (the rows are in plan order)."""
    return next((name for name in unit if ":modes:granted" in name), None)


def _group(name: str, unit_label: str, unit: dict) -> str:
    """The item group of a check: only the mode check of `<base>` is in `modes:granted` (3.4, 11.3)."""
    return "modes:granted" if name == _base_granted(unit) else _suffix(name, unit_label)


def gaps_explained(gaps: int, replaced: int) -> bool:
    """4.5: each gap of the source frame numbers needs a replaced frame. The replaced count comes from a window that
    holds each row of the take and some frames more, so the rule is "not more gaps than replaced frames"."""
    return gaps <= replaced


def _ok(row: dict, unit: dict, unit_label: str) -> bool:
    """`pass`; the one not-run of the sequence pair counts as passed when the other check of the pair passed."""
    if row["result"] == "pass":
        return True
    suffix = _suffix(row["name"], unit_label)
    other = {"sequence": "time-gaps", "time-gaps": "sequence"}.get(suffix)
    expected = {"sequence": "no-sequence", "time-gaps": "has-sequence"}.get(suffix)
    if other and row["result"] == "not-run" and row["reason"] == expected:
        partner = unit.get(f"{unit_label}:{other}")
        return partner is not None and partner["result"] == "pass"
    return False


def item_result(units: list, unix: bool = False) -> str:
    """The summary item of a model from the rows of its units ({name: row} each), by the four rules of 3.4."""
    groups = set(ITEM) | (set(CLOCK) if unix else set())

    def busy(unit):
        row = unit.get(f"{_label_of(unit)}:opens") or {}
        return row.get("result") == "not-run" and row.get("reason") == "camera-in-use"

    if all(busy(unit) for unit in units):
        return "skipped"
    for unit in units:
        lab = _label_of(unit)
        if not busy(unit) and any(row["result"] == "fail" and _group(name, lab, unit) in FATAL
                                  for name, row in unit.items()):
            return "fail"
    for unit in units:
        lab = _label_of(unit)
        if busy(unit) or _not_reached(unit) is not None:  # 3.6.1: checks of the groups that did not run
            return "partial"
        for name, row in unit.items():
            if _group(name, lab, unit) in groups and not _ok(row, unit, lab):
                return "partial"
    return "pass"


def _roll_up(name: str, required: list, module: str | None) -> dict:
    if required and all(row["result"] == "pass" for row in required):
        return dict(name=name, result="pass", reason=None, module=module)
    if any(row["result"] == "fail" for row in required):
        return dict(name=name, result="fail", reason="gate-check-failed", module=module)
    return dict(name=name, result="not-run", reason="gate-check-not-run", module=module)


def gate_rows(model: str, units: list, module: str | None) -> list:
    """The roll-up checks of 11.3 for one model, from the rows of its units, and the ordinary check `no-hang`."""
    ran = [u for u in units if (u.get(f"{_label_of(u)}:opens") or {}).get("result") in ("pass", "fail")] or units

    def required(unit, step):
        lab = _label_of(unit)
        pick = {"opens": ("opens",), "mode": ("modes:granted",), "rate": ("rate",),
                "native-jpeg": tuple(c for c in ITEM if c.startswith("native-jpeg:")),
                "timestamps": CLOCK[:3], "records": tuple(c for c in FATAL if c.startswith("records:")) + (LIVE,)}.get(step)
        if step == "timestamps":  # Q585 of the user [Z7F3]: a source that cannot tell its clock needs the two others
            base = unit.get(f"{lab}:clock:base")
            pick = CLOCK[1:3] if base is not None and base["reason"] == "clock-unknown" else CLOCK[:3]
        if step == "sequence":
            sequence = unit.get(f"{lab}:sequence")
            pick = ("time-gaps",) if sequence is None or sequence["reason"] == "no-sequence" else ("sequence",)
        out = [row for name, row in unit.items() if _group(name, lab, unit) in pick]
        missing = _base_granted(unit) is None if step == "mode" else any(f"{lab}:{c}" not in unit for c in pick)
        if missing and _not_reached(unit) is not None:  # 3.6.1: a required check is in the `not-reached` row
            out.append(_not_reached(unit))
        return out

    rows = [_roll_up(f"{model}:gate:{step}", [row for unit in ran for row in required(unit, step)], module)
            for step in GATE_STEPS[:-1]]
    # 3.6.1 B1: each `fail` row of the model; a `device-removed` row does not fail it (the person removed the camera)
    hang = next((row["reason"] for unit in units for row in unit.values()
                 if row["result"] == "fail" and row["reason"] in HANG_REASONS), None)
    rows.append(dict(name=f"{model}:gate:no-hang", result="fail" if hang else "pass", reason=hang, module=module))
    rows.append(_roll_up(f"{model}:gate", rows, module))
    return rows


# ----- the local record camera_checks.json (2.5) -----

ROW_FIELDS = ("device", "backend", "os_key", "abi", "level", "item", "skellycam", "date")


def writes_row(item: str, opens_results: list) -> bool:
    """2.5: `pass` or `fail`, or `partial` with at least one unit whose `opens` judged."""
    return item in ("pass", "fail") or (item == "partial" and any(r in ("pass", "fail") for r in opens_results))


def control_result(readback: str, holds: str, image: dict) -> str | None:
    """2.5: `works`, `unproven` (the image check did not run), `no` (a check failed), or None (not judged)."""
    if "fail" in (readback, holds, image["result"]):
        return "no"
    if readback == holds == "pass":
        return "works" if image["result"] == "pass" else "unproven" if image["reason"] not in (
            "prior-check-failed", "prior-failure", "cancelled", "over-budget", "not-built") else None
    return None


def record_row(device, backend, os_key, abi, level, item, version, date, gate, controls) -> dict:
    row = dict(device=device, backend=backend, os_key=os_key, abi=abi, level=level, item=item, skellycam=version,
               date=date)
    if level == "full":
        row["gate"] = gate
    if controls:
        row["controls"] = controls
    return row


def write_record(path: Path, rows: list) -> None:
    """Replace the rows of the same key (device, backend, OS key, ABI, level); keep the other good rows. A damaged
    file or a row with a missing field counts as no row (2.5)."""
    path = Path(path)
    keys = {tuple(row[f] for f in ("device", "backend", "os_key", "abi", "level")) for row in rows}
    kept = [row for row in camera_checks.read_rows(path)
            if all(isinstance(row.get(f), str) for f in ROW_FIELDS)
            and tuple(row[f] for f in ("device", "backend", "os_key", "abi", "level")) not in keys]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps({"format": 1, "rows": kept + list(rows)}, indent=1), encoding="utf-8")
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


# ----- camera names (9.4) -----

_SERIAL = re.compile(r"(?i)(?:\b(?:s/?n|serial)\b[\s:#]*)?\b([A-Za-z0-9]{8,})\b")
_IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b")


def clean_name(name: str, device: str | None, private_terms) -> str:
    """The name cleaning of 9.4, steps 1 to 5. Never empty."""
    text = re.sub(r"^.*?['’]s\s+", "", name, count=1)  # 1: a possessive head
    terms = {term.lower() for term in private_terms if term}
    if any(word.strip("()[]{},.;:").lower() in terms for word in text.split()):  # 2: a user name or a host name
        return f"Camera {device}" if device else "Camera"
    text = _SERIAL.sub(lambda m: "" if sum(c.isdigit() for c in m.group(1)) >= 4 else m.group(0), text)  # 3
    text = re.sub(r"\(\s*\)|\[\s*\]", "", text)
    text = re.sub(r"(?i)\((?:r|tm)\)", "", text)  # 4
    for token in ("<", ">", "](", "]:", "://"):  # 5: the Markdown rules 17 and 20 of the contract
        text = text.replace(token, "")
    text = _IPV4.sub("", re.sub(r"(?i)www\.", "", text))
    text = " ".join(text.split())[:64].strip()
    return text or (f"Camera {device}" if device else "Camera")
