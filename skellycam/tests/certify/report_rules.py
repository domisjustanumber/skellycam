"""The rules of a module report of `report-format.md` format 1.7.0 (repository `skellycertify`) that code can
check (specs/certify.md T-CERT-03, T-CERT-04, T-CERT-30, T-CERT-67, T-CERT-70). Test code only.

`problems(report)` gives one text for each broken rule; an empty list means that the report obeys each rule
below. The rules: the fields of C 3.1 and their forms (C 3.2, C 3.3), the check form of C 3.4 (name pattern,
unique names, one result, a reason for `fail` and `not-run`, flat `numbers`, `module` length), the summary items
of C 3.7 (group, name, device of the form `vvvv:pppp` for a camera, result, `reason` only for `skipped`, and
`not-installed` only for a `component`, `gate` names a roll-up check of the report, one `camera` item for each
`device`), `notices` of C 3.8, `cleanup` as `fail` check objects, `test_media` of C 3.9,
`host.gpus[].shared_memory_bytes` of C 3.3, `evidence` of C 7.1 (with the reasons that the package fields give),
and the privacy rules 1 to 7, 9, 10 and 19 of C 6 on each string of the JSON object (format 1.7.0: the `name` of an
item of `test_media` is exempt from rule 7). The Markdown rules (8, 17, 20)
apply to the report file, which the app writes; `markdown_problems(text)` checks rules 17 and 20 on a value that
the Markdown part shows.
"""

import functools
import json
import re
from pathlib import Path

SCHEMA = "skellycertify.report/1.7.0"
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}$")
REASON = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
RESULTS = ("pass", "fail", "not-run", "record-only")
ITEM_RESULTS = ("pass", "fail", "record-only", "partial", "skipped")
GROUPS = ("ep", "gpu-jpeg", "camera", "benchmark", "component")
DEVICE = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{4}$")
ROLL_UP_REASONS = (None, "gate-check-failed", "gate-check-not-run")
CREATED = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
PATH = re.compile(r"(?:\b[A-Za-z]:[\\/]|\\\\[^\\\s]|/(?:home|Users|root)/|~[\\/])")
PCI = re.compile(r"\b(?:[0-9a-fA-F]{4}:)?[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]\b")
MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MEDIA = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".mp4", ".avi", ".mkv", ".mov", ".webm", ".wav",
         ".mp3", ".flac")
KEYS = {"hostname", "host_name", "node", "user", "username", "user_name", "email", "serial", "serial_number", "uuid",
        "mac", "mac_address", "bus_id", "pci_bus_id", "luid", "ip", "ip_address"}
IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b")
EXCEPTION_CLASS = re.compile(r"^[A-Z][A-Za-z0-9]*$")  # certify.md 15 `<ExceptionClass>`


@functools.cache
def known_codes() -> frozenset:
    """The codes of the tables of `skellycam/REASON_CODES.md` (T-CERT-30, C 5.4)."""
    import skellycam
    text = (Path(skellycam.__file__).parent / "REASON_CODES.md").read_text(encoding="utf-8")
    return frozenset(re.findall(r"^\| `([^`<]+)` \|", text, flags=re.MULTILINE))


def _known(code, exception_class=False) -> bool:
    """A code of the file; for a reason (not a notice code, C 3.8) also the class name of an exception (15: "any")."""
    return not isinstance(code, str) or code in known_codes() or (exception_class and bool(EXCEPTION_CLASS.match(code)))


def _strings(value, keys):
    if isinstance(value, dict):
        for key, item in value.items():
            keys.append(key)
            yield key
            yield from _strings(item, keys)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item, keys)
    elif isinstance(value, str):
        yield value


def _check(check, where, out):
    if not isinstance(check, dict):
        out.append(f"{where}: not an object")
        return
    name = check.get("name")
    if not isinstance(name, str) or not NAME.match(name):
        out.append(f"{where}: name {name!r} does not match C 3.4")
    if check.get("result") not in RESULTS:
        out.append(f"{where} {name}: result {check.get('result')!r}")
    if "reason" not in check:
        out.append(f"{where} {name}: no reason field")
    reason = check.get("reason")
    if check.get("result") in ("fail", "not-run") and reason is None:
        out.append(f"{where} {name}: {check.get('result')} with no reason")
    if reason is not None and (not isinstance(reason, str) or not REASON.match(reason)):
        out.append(f"{where} {name}: reason {reason!r} does not match C 5.2")
    module = check.get("module")
    if module is not None and (not isinstance(module, str) or not 1 <= len(module) <= 80):
        out.append(f"{where} {name}: module {module!r}")
    numbers = check.get("numbers", {})
    if not isinstance(numbers, dict):
        out.append(f"{where} {name}: numbers is not an object")
        return
    for key, value in numbers.items():
        ok = value is None or isinstance(value, (bool, int, float, str)) or (
            isinstance(value, list) and all(isinstance(v, str) and REASON.match(v) for v in value))
        if not ok:
            out.append(f"{where} {name}: numbers.{key} is not flat: {value!r}")


def problems(report) -> list[str]:
    out = []
    for field in ("schema", "package", "kind", "created_utc", "host", "checks", "evidence"):
        if field not in report:
            out.append(f"no required field {field}")
    if report.get("schema") != SCHEMA:
        out.append(f"schema {report.get('schema')!r}")
    if "id" in report and not (isinstance(report["id"], str) and UUID4.match(report["id"])):
        out.append(f"id {report.get('id')!r} is not a version 4 UUID")
    package = report.get("package") or {}
    if not isinstance(package.get("name"), str) or package.get("name") != package.get("name", "").lower():
        out.append("package.name")
    commit = package.get("commit")
    if commit is not None and not re.fullmatch(r"[0-9a-f]{40}", str(commit)):
        out.append("package.commit")
    if package.get("tree_modified") not in (True, False, None):
        out.append("package.tree_modified")
    if report.get("kind") not in ("quick", "full"):
        out.append(f"kind {report.get('kind')!r}")
    if not CREATED.match(str(report.get("created_utc"))):
        out.append("created_utc")
    host = report.get("host")
    if not isinstance(host, dict):
        out.append("host is not an object")
    else:
        for key in ("os", "cpu"):
            if key in host and host[key] is not None:
                if not isinstance(host[key], dict) or not all(
                        v is None or isinstance(v, (str, int, float)) for v in host[key].values()):
                    out.append(f"host.{key} has another form")
        if host.get("memory_bytes") is not None and not (isinstance(host["memory_bytes"], int)
                                                         and host["memory_bytes"] >= 0):
            out.append("host.memory_bytes")
        if "gpus" in host and host["gpus"] is not None and not isinstance(host["gpus"], list):
            out.append("host.gpus")
        for gpu in host.get("gpus") or []:
            shared = gpu.get("shared_memory_bytes") if isinstance(gpu, dict) else None
            if shared is not None and not (isinstance(shared, int) and not isinstance(shared, bool) and shared >= 0):
                out.append("host.gpus[].shared_memory_bytes")
    checks = report.get("checks") or []
    names = [c.get("name") for c in checks if isinstance(c, dict)]
    for i, check in enumerate(checks):
        _check(check, f"checks[{i}]", out)
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        out.append(f"names not unique: {duplicates}")
    for i, check in enumerate(report.get("cleanup") or []):
        _check(check, f"cleanup[{i}]", out)
        if check.get("result") != "fail":
            out.append(f"cleanup[{i}]: a cleanup row is `fail`")
    media = report.get("test_media", [])
    if not isinstance(media, list) or len(media) > 50:
        out.append("test_media")
    for i, item in enumerate(media if isinstance(media, list) else []):
        ok = (isinstance(item, dict) and isinstance(item.get("name"), str) and 1 <= len(item["name"]) <= 120
              and not PATH.search(item["name"]) and isinstance(item.get("sha256"), str)
              and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) and isinstance(item.get("bytes"), int)
              and not isinstance(item.get("bytes"), bool) and item["bytes"] >= 0
              and item.get("source") in ("bundled", "shared"))
        if not ok:
            out.append(f"test_media[{i}]: form of C 3.9")
    items = report.get("summary") or []
    item_names = set()
    devices = []
    for i, item in enumerate(items):
        if item.get("group") not in GROUPS:
            out.append(f"summary[{i}]: group {item.get('group')!r}")
        name = item.get("name")
        if not isinstance(name, str) or not 1 <= len(name) <= 80:
            out.append(f"summary[{i}]: name {name!r}")
        item_names.add(name)
        device = item.get("device")
        if device is not None and (not isinstance(device, str) or len(device) > 40):
            out.append(f"summary[{i}]: device {device!r}")
        if item.get("group") == "camera":
            devices.append(device)
            if device is not None and not DEVICE.match(str(device)):
                out.append(f"summary[{i}]: camera device {device!r} is not vvvv:pppp")
        if item.get("result") not in ITEM_RESULTS:
            out.append(f"summary[{i}]: result {item.get('result')!r}")
        if item.get("result") == "skipped":
            allowed = ("busy", "reviewed", "not-installed") if item.get("group") == "component" else ("busy", "reviewed")
            if item.get("reason") not in allowed:
                out.append(f"summary[{i}]: skipped with reason {item.get('reason')!r}")
        elif item.get("reason") is not None:
            out.append(f"summary[{i}]: a reason for {item.get('result')}")
        if "gate" in item:
            gate = item["gate"]
            target = next((c for c in checks if c.get("name") == gate), None)
            if not isinstance(gate, str) or not NAME.match(gate) or target is None:
                out.append(f"summary[{i}]: gate {gate!r} is not a check of the report")
            elif target.get("reason") not in ROLL_UP_REASONS or target.get("result") not in ("pass", "fail", "not-run"):
                out.append(f"summary[{i}]: gate {gate!r} is not a roll-up check")
    camera_devices = [d for d in devices if d is not None]
    if len(camera_devices) != len(set(camera_devices)):
        out.append("two camera items for one device")
    for check in checks:
        name = str(check.get("name"))
        if name.startswith("cam.") and check.get("module") is not None and check["module"] not in item_names:
            out.append(f"{name}: module {check.get('module')!r} is not the name of a summary item")
    notices = report.get("notices") or []
    if not isinstance(notices, list) or len(notices) > 50:
        out.append("notices")
    for i, notice in enumerate(notices):
        if not isinstance(notice.get("code"), str) or not REASON.match(notice["code"]):
            out.append(f"notices[{i}]: code")
        values = notice.get("values", {})
        if not isinstance(values, dict) or len(values) > 8 or not all(
                isinstance(v, (int, float)) or (isinstance(v, str) and len(v) <= 80) for v in values.values()):
            out.append(f"notices[{i}]: values")
    evidence = report.get("evidence") or {}
    reasons = evidence.get("reasons")
    if not isinstance(reasons, list) or not all(isinstance(r, str) and REASON.match(r) for r in reasons):
        out.append("evidence.reasons")
    elif evidence.get("valid") is not (not reasons):
        out.append("evidence.valid is not 'no reasons'")
    else:  # C 7.1: the reasons that the package fields and the checks give
        version = str(package.get("version"))
        needed = {"no-version": not SEMVER.match(version),
                  "no-commit": not (isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit)),
                  "modified-tree": package.get("tree_modified") is not False,
                  "cancelled": any(c.get("reason") == "cancelled" for c in checks if isinstance(c, dict))}
        for reason, due in needed.items():
            if due and reason not in reasons:
                out.append(f"evidence.reasons lacks {reason}")
    # T-CERT-30: each reason, notice code and evidence reason of skellycam is in skellycam/REASON_CODES.md
    rows = [c.get("reason") for c in [*checks, *(report.get("cleanup") or [])] if isinstance(c, dict)]
    rows += reasons if isinstance(reasons, list) else []  # a refused run gives the class name of a lock error
    codes = [n.get("code") for n in notices if isinstance(n, dict)]
    unknown = {c for c in rows if not _known(c, exception_class=True)} | {c for c in codes if not _known(c)}
    for code in sorted(unknown, key=str):
        out.append(f"the code {code!r} is not in skellycam/REASON_CODES.md")
    keys = []
    # 1.7.0: the name of a test media file is exempt from rule 7; the same string elsewhere is not
    media_names = set()
    if isinstance(media, list):
        media_names = {item["name"] for item in media if isinstance(item, dict) and isinstance(item.get("name"), str)}
    media_names -= set(_strings({k: v for k, v in report.items() if k != "test_media"}, []))
    for text in _strings(report, keys):
        if PATH.search(text):
            out.append(f"rule 1: a path in {text!r}")
        if PCI.search(text):
            out.append(f"rule 3: a PCI address in {text!r}")
        if MAC.search(text):
            out.append(f"rule 4: a MAC address in {text!r}")
        if EMAIL.search(text):
            out.append(f"rule 5: an email address in {text!r}")
        if len(text) > 2000:
            out.append("rule 6: a string over 2000 characters")
        if text.lower().endswith(MEDIA) and text not in media_names:
            out.append(f"rule 7: a media file name {text!r}")
        if "Traceback (most recent call last)" in text:
            out.append("rule 10: a traceback")
    for key in keys:
        if key.lower() in KEYS:
            out.append(f"rule 2: the key {key!r}")
    try:
        json.loads(json.dumps(report), object_pairs_hook=_no_duplicates)
    except ValueError as error:
        out.append(f"rule 19: {error}")
    return out


def _no_duplicates(pairs):
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError(f"a key two times in one object: {keys}")
    return dict(pairs)


def markdown_problems(text: str) -> list[str]:
    """Rules 17 and 20 of C 6 for a value that the Markdown part shows (a camera name)."""
    out = [f"rule 17: {token!r} in {text!r}" for token in ("<", ">", "](", "]:", "://") if token in text]
    if "www." in text.lower():
        out.append(f"rule 17: www. in {text!r}")
    if IPV4.search(text):
        out.append(f"rule 20: an IPv4 address in {text!r}")
    return out


def assert_valid(report):
    found = problems(report)
    assert not found, "\n".join(found)
