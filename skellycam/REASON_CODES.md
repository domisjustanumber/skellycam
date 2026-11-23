# Reason codes of skellycam

This file is the list of the reason codes and the notice codes of the certify run of skellycam. The contract
`report-format.md` of the repository `skellycertify` (section 5.4) requires it. The spec is
[`specs/certify.md`](../specs/certify.md) (sections 3, 8.3 and 15). Each code has one sentence of meaning. A
notice code also has its text for the person. `<name>` is the cleaned camera name of `values.camera`.

The common codes of the contract keep the meaning of the contract (section 5.3): `timed-out`, `crashed`,
`bad-output`, `hung-at-exit`, `cancelled`, `cameras-busy`, `not-built`, `over-budget`, `no-version`, `no-commit` and
`modified-tree`.

## Common codes

| Code | Meaning |
|---|---|
| `timed-out` | The check or its child process ran longer than its time limit. |
| `crashed` | The child process or the camera process ended with no result. `numbers.exit_code` holds its exit code when it is known. |
| `bad-output` | The child process gave output that is not a result. |
| `hung-at-exit` | The session child gave its result and did not end. Certify stopped it. |
| `cancelled` | The caller set `cancel` or `abandon`, so the check did not run to its end. |
| `cameras-busy` | A camera group of skellycam was open in the calling process, or another certify run held the run lock, so certify refused the run. |
| `not-built` | The check, or the source fact that it reads, does not exist in this version of skellycam. |
| `over-budget` | The check did not run because the time limit of the quick run was used up. |
| `no-version` | `package.version` is not a SemVer version. |
| `no-commit` | `package.commit` is not known. |
| `modified-tree` | `package.tree_modified` is not `false`. |

## Codes of skellycam

| Code | Meaning |
|---|---|
| `backend-missing` | The capture backend is not on this system. |
| `no-camera` | The run found no real camera. The camera part of the report reads "not checked". |
| `same-model` | Another camera of the same model had these checks in this run. |
| `ring-lapped` | The frame ring no longer held the frames that the check compares. |
| `no-mjpg-mode` | The camera has no MJPG mode at 30 fps or more. |
| `camera-in-use` | Another program holds the camera. |
| `hung` | A bounded call of the camera did not return. The camera process ended hard. |
| `rate-low` | The frame rate is more than 3 % below the mode rate. Camera is slow. Try adding more light. |
| `rate-high` | The frame rate is more than 3 % above the mode rate. |
| `too-dark` | The frame is too dark to judge the check. |
| `too-bright` | The frame is too bright to judge the check. |
| `readback-differs` | A set value reads back as a different value. |
| `setting-reverted` | A set value changed back to another value later. |
| `no-image-effect` | The image did not change as the set value requires. |
| `no-native-jpeg` | The frames are not the camera's own JPEG frames, or skellycam encoded frames. |
| `jpeg-damaged` | A frame is not a complete JPEG, or its bytes differ from the bytes of the same frame in another place. |
| `jpeg-size-differs` | The JPEG size of a frame is not the size of the mode. |
| `mode-not-granted` | The granted format, size or rate is not the requested one. |
| `take-not-finished` | The take did not start, or its manifest is not `finished`. |
| `take-error` | The manifest of the take holds a `take_error`. |
| `rows-differ` | A timing sidecar does not have the frame count of the take as its row count. |
| `missing-rows` | A camera has a `missing` row, or the take has a `camera_dead` or `camera_file_short` warning. |
| `gaps-unexplained` | The gaps of the source frame numbers are not equal to the replaced frames of the camera. |
| `group-rate-off` | The frame rate of the take is more than 1 % from the mode rate. |
| `too-few-frames` | The take has fewer than 80 % of the frames of 3 seconds at the mode rate. |
| `frame-not-decodable` | A block of the camera file does not decode. |
| `fat-disk` | The recording folder is on a FAT disk, so the take cannot start. |
| `disk-stall` | A write of the take did not make progress within the stall limit. |
| `write-error` | A write of the take failed. |
| `clock-base-differs` | The time of a frame is not on the clock of its arrival time. |
| `clock-unknown` | The source cannot tell the clock of its frame times, so the check of the clock base cannot run. |
| `sample-after-arrival` | A sample time is later than its arrival time. |
| `sample-too-early` | The 95th percentile of the sample time minus the arrival time is more than 200 ms from zero. |
| `sequence-unreliable` | A long interval between two frames has no gap of the sequence number. |
| `no-sequence` | The source gives no sequence number, so `time-gaps` judges the gaps. |
| `has-sequence` | The source gives a sequence number, so `sequence` judges the gaps. |
| `frame-gaps` | The count of long intervals between arrivals went up during the take. |
| `gate-check-failed` | A check that the roll-up check requires is `fail`. |
| `gate-check-not-run` | A check that the roll-up check requires is `not-run`. |
| `no-manual-exposure` | The camera has no manual exposure, so skellycam cannot set its exposure. |
| `prior-failure` | The camera hung, crashed or was removed earlier in the run, so certify does not open it again. |
| `prior-check-failed` | A check that this check needs did not pass. |
| `not-deleted` | The work folder of the run could not be deleted. |
| `not-found` | The camera was gone at the open. |
| `no-access` | The process has no access to the camera. |
| `no-permission` | The application has no camera permission. |
| `usb-bandwidth` | The USB controller refused the stream for bandwidth. |
| `no-mode` | The camera does not declare this mode. |
| `below-floor` | The nearest mode is below 30 fps. |
| `open-failed` | The open failed for another cause. |
| `first-frame-timeout` | No first frame came in 5 seconds. |
| `not-ready` | The camera was not ready in 15 seconds. |
| `control-failed` | A set call of a control failed. |
| `device-removed` | The camera was removed. |
| `stalled` | The camera gave no frame for 2 seconds. |
| `previous-process-alive` | An earlier camera process still holds the camera. |
| `stream-error` | The stream gave an error. |
| `format-changed` | The format changed during the stream. |
| `<ExceptionClass>` | A step raised an exception of this class. The report never holds the message. |

## Notice codes

| Code | Meaning | Text for the person |
|---|---|---|
| `camera-wedged` | The camera hung, its process ended, or its open after the run failed. | Camera <name>: wedged, please replug |
| `camera-not-restored` | A setting of the camera is not as it was before the run. | Camera <name>: a setting is not as it was before the run. Open the camera in SkellyCam and set it again. |
