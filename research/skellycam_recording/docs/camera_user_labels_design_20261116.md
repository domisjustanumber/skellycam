# User-given camera labels: design research (read-only; nothing edited, no camera touched)

Source marks: [C] code, [R] research file, [S] spec repo, [D] public documentation, [I] my inference.

## Recommendation in short

Keep the typed name as display metadata, never as identity and never in a file name. The name's real job is to be the handle the user recognises when the program asks "which remembered camera is this?". Replace the drafted session-scoped last resort with a program-assigned ID, so a camera with no stable identifier keeps one key across sessions. The file format needs one new member (`key_origin`, three values), one new identity form, and a relaxed recompute test.

## 1. The user's problem and workflow

What exists today:

| Fact | Source |
|---|---|
| Camera id is 2 bytes of SHA-256 over the OS device path, or over `vid_pid_index`. | [C] `skellycam/core/device_detection/detect_cameras_devices.py:44-54` |
| Detection reads no serial: `CameraDeviceInfo` has index, name, vendor ID, product ID, path and backend only. | [C] same file `:35-42` |
| `camera_name` is the OS device name, defaulting to `Camera-<id>`. | [C] `skellycam/core/camera/config/camera_config.py:73-74, 127-128` |
| The UI only displays `camera.name`; my grep found no rename control. | [C] `skellycam-ui/src/components/camera-config-tree-view/CameraTreeItem.tsx:95`; [R] `research/skellycam_recording/docs/camera_info_placement_20261115.md` finding 5 |
| Per-camera settings persist in browser localStorage under `skellycam-camera-settings`, keyed by camera id, and are deleted when the camera is not detected. | [C] `skellycam-ui/src/store/slices/cameras/camera-settings-storage.ts:3-11`, `cameras-thunks.ts:52-61` |
| The backend has a per-user folder `~/skellycam_data`. | [C] `skellycam/system/default_paths.py:5, 30-34` |
| freemocap binds calibration by exact camera id, then by OS index, all or nothing. | [C] `freemocap/core/tasks/calibration/shared/calibration_camera_binding.py:144-232` |
| Only 1 of the 4 research cameras has a serial (the C922). The C930e, the Kiyo Pro and the generic camera rely on the port path. | [R] `research/usb_cameras/docs/usb_camera_report.md:100-107` |
| "Two identical serial-less cameras can only be told apart by port, and swapping their cables is undetectable." | [R] same file `:100` |
| OS friendly names are useless: the Kiyo Pro shows as "USB Video Device". | [R] same file `:116` |
| Reboot, physical replug, port move and two identical cameras were never tested on hardware. | [R] same file `:118` |

When the user must tell cameras apart:

| Moment | What the program knows | What the user must do |
|---|---|---|
| First setup | Nothing | Learn which preview is which physical camera; optionally name each one |
| Reboot or replug, same port | Serial or port key matches ([R] `:114` for re-enumeration; reboot untested) | Nothing |
| Port move, new hub, or another computer | The port key changes; vendor ID and model match a remembered camera | Confirm (decided today) |
| Two identical serial-less cameras with cables swapped | Nothing looks wrong | Only the user, or a geometry check, can notice [I] |
| No stable identifier at all | Model at most | Pick from the remembered list every session |

How a person can physically tell which is which, in order of cost [I]:
1. **Live preview grid.** It already exists; the user looks at what each camera sees.
2. **Cover a lens or wave at one camera.** The program could detect the stream that goes dark and bind it without a click. Auto-exposure may fight this; untested.
3. **A sticker on the camera** carrying the user's name. Professional systems show the number on the camera itself.
4. **"Identify" by streaming one camera** so that only its activity LED is lit. I do not recommend it: it needs open/close cycling, which is the Kiyo Pro wedge trigger.

Comparable tools:

| Tool | What it does | Source |
|---|---|---|
| OptiTrack Motive | Camera numbers by location, by serial or custom. The number shows on the camera's front LED panel, and selecting a camera lights its ring. | [D] docs.optitrack.com/motive-ui-panes/settings/settings-general |
| Qualisys QTM | The front display shows the camera number. A "Reorder" tool lets the user click cameras in the wanted order, and the docs suggest pointing at a camera while watching the 2D views. Oqus cameras store the number in the camera. | [D] docs.qualisys.com/qtm/content/system_setup/ordering_cameras.htm and techref/oqus_camera.htm |
| OBS | No persistent identity for identical webcams. Forum users report sources swapping after a reboot, and their workarounds are plug order or mixed models. | [D] obsproject.com forum threads 136620, 163469, 167670 (user reports, not official) |
| Anipose | The camera name is a user-chosen token parsed from the video file name by `cam_regex`. Calibration reuse depends on the user keeping names consistent. | [D] anipose.readthedocs.io/en/latest/start3d.html and params.html |
| Lightning Pose | Camera names must be substrings of file names, and no name may be a substring of another. | [D] lightning-pose.readthedocs.io, Lightning Pose 3D |
| Linux udev | Identical serial-less webcams are named by a port-match rule plus `SYMLINK`. The name is lost when the camera moves port. | [D] wiki.archlinux.org/title/Udev, linuxfromscratch.org "Managing Devices"; [R] `usb_camera_report.md:120` |
| Browser and video-call pickers | They list OS labels, so identical cameras show identical labels and the user picks by preview. | From memory of the MediaDevices API; not fetched |

Two patterns come out of this [I]. Systems with real hardware IDs put a number on the device and in the UI. Systems without them (OBS, udev, Anipose) fall back on port or on the user's discipline, and they fail silently. skellycam can do better than the second group only by asking the user at the moment of ambiguity and remembering the answer.

## 2. What the user label should be

- (a) `user_name` stays display metadata; a local store maps camera to name.
- (b) A stored ID of its own (`user:<uuid>` or similar) becomes an identity form, re-attached by the user's choice.
- (c) The typed label replaces the hex `camera_label` in file names.

| Effect on | (a) metadata only | (b) stored ID as identity form | (c) label in file names |
|---|---|---|---|
| Key stability across sessions | As today's forms: good for serial, port-bound otherwise, none for the last resort | A no-identifier camera keeps one key, provided the user re-attaches it | Unchanged, unless the key is also derived from the name, which is worse |
| Two cameras sharing a key | Port-key hazards remain (see below) | A random ID cannot collide; a wrong pick by the user is the remaining risk | Two rigs with a camera called "left" would share a key if the name were hashed |
| File names | Unchanged | Unchanged (hex of the new key) | Needs SFF-715-style character rules and a collision rule; TOML table keys, Parquet `camera:<label>`, Blender `Capture_<label>` and SFF-753 `bad_label` all change |
| Calibration reuse | Works while the key holds | Works for every camera the user re-attaches | A rename breaks every by-label lookup |
| Privacy | The name sits in two listed fields and can be stripped | Same; the hashed ID is random, not personal | The name is in every file name and cannot be stripped without renaming, which SFF-717 forbids |
| Rename | Store only; old takes keep the old name | Same; the key does not change | The same camera gets different file names across takes |
| Take moved to another computer | Self-describing | Self-describing | Self-describing, but the names may be illegal on the other file system |

Verdict:
- **(c) is rejected.** It is also against the earlier research recommendation: "Never in CSV headers or file names" ([R] `camera_info_placement_20261115.md` section 5, item 5).
- **(a) is right for the name.**
- **(b) is right only for the ID, not the typed text, and only where no hardware form applies.** Recommended design: (a) plus a narrow (b).

One hazard in today's decision needs a rule. Camera A moves from port 1 to port 2 and keeps its old key, hash(port 1). Later an identical camera B is plugged into port 1 and computes the same hash. So matching must go by a stored locator, not by the recomputed hash. After a confirmation the store updates A's locator to port 2. A computed key that equals a remembered key whose locator differs is then "unknown, same model" (ask the user), never a silent match. [I]

## 3. Assigning and re-attaching

**Store entry (program state, not format):** `camera_key`, locator (serial, port path, OS device ID or none), vendor ID, product ID, model, `user_name`, last seen.

**First time:** a detected camera matches nothing, so it is new. The key comes from the first identity form that applies. The name is optional and can be edited inline in the camera list beside the preview.

**Default when the user gives no name:** `user_name` is null in the file. The UI shows `<model> · <camera_label>`. Do not write invented names into the file.

**Each session:**
1. Match automatically by serial, then by stored locator.
2. One unknown device and one unconnected remembered camera of the same vendor ID and model: a single yes/no prompt with a live preview and the remembered name.
3. Several: one screen with the live previews of the unknown devices. Each has a list of candidate names plus "new camera". Cover-the-lens binding is an optional speed-up.
4. Never guess between identical candidates.
5. A skipped prompt means "new camera". Recording is not blocked. freemocap's all-or-nothing binding already keeps a calibration off a set that does not match ([C] `calibration_camera_binding.py:15-18`).

**Uniqueness (program rules):**
- One key is bound to at most one connected camera.
- Names are unique among remembered cameras after trim, NFC and case-fold; the program refuses a duplicate at entry.

**Conflicts between the user and the OS:**

| Situation | Winner | Action |
|---|---|---|
| A usable serial identifies remembered camera X; the user says it is Y | Serial | Refuse the attach and offer a rename instead |
| Vendor ID or product ID differs from the remembered camera | OS | Refuse; offer "new camera" |
| The port matches remembered X; the user says it is the identical camera Y (swapped cables) | User | Rebind; the port is weak evidence; `key_origin` becomes `confirmed_by_user` |
| The computed key is already bound to another connected camera | Neither | Give the newcomer an assigned key |

A wrong confirmation cannot be repaired in past takes, because the keys are in the files and SFF-717 forbids renames. The UI needs a "these two are swapped" action for future takes. freemocap's `GEOMETRY` match kind is the natural detector ([C] `calibration_camera_binding.py:44-45` defines the enum value; I did not check that the check is implemented).

## 4. Storage

- **Where:** one backend-owned JSON file under `~/skellycam_data`, per OS user and per machine. It must not stay in localStorage, which is per browser profile, invisible to freemocap's embedded backend, and pruned for unplugged cameras today ([C] `cameras-thunks.ts:54-61`). That pruning must stop for identity data.
- **Moving a rig:** "import cameras from a take folder" reads `camera_configs` (key, `user_name`, model, IDs) into the store. Any take is the export, so no separate rig-file format is needed. On the new machine every serial-less camera needs one confirmation, because port paths differ.
- **In the take:** what is already there (`camera_key`, `camera_label`, `user_name`, `device`, and the summary's label-to-name table) plus `key_origin`. Nothing else. The remembered list itself stays out, as decided.

## 5. Proposals for the spec editor

1. **SFF-752, identity string: the first form that applies.**
   - (1) `<vendor_id>:<product_id>:serial:<serial>`
   - (2) `<vendor_id>:<product_id>:port:<port_path>`
   - (3) `<vendor_id>:<product_id>:device:<os_device_id>`
   - (4) `<vendor_id>:<product_id>:assigned:<uuid>`, where `<uuid>` is 32 lowercase hexadecimal characters of a random UUID that the capture program makes once and remembers. This replaces the drafted `session:<uuid>:<os_index>`. A program that cannot remember simply makes a new one each session.
   - Add: "A capture writer MAY write the remembered `camera_key` of a camera in place of the computed one, when the user confirmed that the device is that camera."
2. **Camera config, new member `key_origin`** after `user_name`. It is a JSON string, or null when `camera_key` is 0.

   | Value | Meaning |
   |---|---|
   | `"computed"` | The key is the hash of form 1, 2 or 3 built from this file's `device` values |
   | `"confirmed_by_user"` | A remembered key, attached because the user confirmed the camera in this or an earlier session |
   | `"assigned"` | Form 4, made in this session and confirmed by nobody |

3. **`device`: add `os_device_id`** (string or null). Form 3, decided today, needs it. Add a privacy row `/camera_configs/<key>/device/os_device_id`, kind `device_path`.
4. **`user_name`: tighten the text.** Null, or 1 to 128 bytes of UTF-8 in NFC, with no control character and no leading or trailing space. A writer SHOULD NOT give two cameras of a take the same non-null `user_name`. No reader rule.
5. **`camera_label`, file names, SFF-720, SFF-753, SFF-873, SFF-728, SFF-881 `user_name` rows:** no change.
6. **Tests and records to change.**
   - SFT-717 (`spec/conformance.md:531-536`): recompute the key from `device` only when `key_origin` is `computed`; otherwise check 16 hexadecimal characters, not 0.
   - The capture-info member-order test (`conformance.md:713`) and SFF-800: add `key_origin` and `os_device_id`.
   - Golden takes that hold a capture info JSON (G1, G3 and the privacy golden G16): add the new members.
   - Add one vector with `confirmed_by_user` where `device.port_path` does not reproduce the key.
   - SFT-766/767: the new privacy row.
   - A new ADR supersedes DM9S item 16a (`decisions/entries/DM9S-spec-v2-details-part-7.md:38-42`); close `decisions/open-work.md:25-26`.

## 6. Recommendation, decisions, program work, unverified

**One design.** Identity forms in the order serial, port, OS device ID, assigned ID. The typed name is display metadata, held in a backend store and copied into each take. Matching is by stored locator. The user confirms at every ambiguity, picking by name and live preview. `key_origin` records which case applied.

**Owner's decisions:**

| # | Decision | Recommended | Alternative |
|---|---|---|---|
| 1 | Last-resort form | `assigned:<uuid>`, remembered and re-attached by the user | Session-scoped as drafted; calibration then never carries over for such cameras |
| 2 | Values of `key_origin` | Three: `computed`, `confirmed_by_user`, `assigned` | Two as drafted, with `assigned` folded into `computed`; SFT-717 then cannot tell them apart |
| 3 | Store the hashed identity string in the take (a member `identity`) | No. No reader needs it, and it is one more private field. | Yes; SFT-717 then stays a pure recompute for every origin, at the cost of a new privacy row whose kind depends on the form |
| 4 | Serial-less cameras | Keep the port form (decided today); it gives zero prompts for a rig that never moves and needs no store | Give every serial-less camera an assigned ID at first sight, with the port as locator only. Cleaner, with no port-key hazard, but it reverses today's decision and loses identity if the store is lost |
| 5 | Unique names | Program rule in the store; SHOULD in the spec | MUST in the spec with a reader check |
| 6 | Label in file names | No | Yes (option c above) |
| 7 | Name on the device | Recommend stickers in the user docs | Nothing |

**skellycam and freemocap program work (outside the format):**
- Read serial, port path and OS device ID. cv2_enumerate_cameras does not give them; `research/usb_cameras/naming/camera_identity.py` has the scheme, Windows-tested only.
- The backend remembered-cameras store, with locator matching and the collision rule.
- Rename UI, the confirm and identify screen, and the "swapped" action.
- Import cameras from a take.
- Stop pruning settings for unplugged cameras.
- freemocap: bind calibration by `camera_key` and drop the index fallback.

**Not verified:**
- Reboot, replug, port move and two identical cameras on real hardware ([R] `usb_camera_report.md:118`); the Linux and macOS identity code is draft.
- Whether cover-the-lens detection works under auto-exposure.
- Whether the research cameras have an activity LED.
- That freemocap's geometry check exists beyond the enum value.
- Which base folder freemocap's embedded skellycam uses.
- The browser-picker and DeepLabCut behaviour (from memory).
- The OBS evidence is forum reports only.
- The skellycam code was read on the working tree of branch `dom/research`, not on `development-streaming`.
- I did not read every UI component, or the conformance goldens beyond the lines cited.

Skipped: an export format for the store, a title tag in the MKV, a repair tool for wrongly confirmed past takes, and the cover-the-lens flow as a requirement. Add them only if asked.

Risk: with identical serial-less cameras a wrong user pick, or an unnoticed cable swap, silently gives one camera another's calibration. Only a geometry check catches it.
