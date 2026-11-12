# Handoff 2026-11-12 (evening): skellyfileformat, spec first, and the spec draft

Written for a fresh agent that continues this work. The owner is "Dom". Use they/them for anyone not named. Paths: `<sc>` = `~\GitHub\freemocap\skellycam` (branch `dom/research`), `<sff>` = `~\GitHub\freemocap\skellyfileformat` (branch `main`), `<p1>` = `~\GitHub\freemocap\skellycam-phase1`.

## 1. State in one paragraph
Today set a **spec-first** process and created **skellyfileformat**, a public repo for the recording format. The format decisions are now ADRs in `<sff>/decisions/`. Two desk tests closed open items: external `TerminateProcess` kills of the FLAC writer, and rotation flags in players. Two sub-agent reviews settled who owns which file fields. A third sub-agent compiled every input for the spec draft into one digest. **Next is step 5: put the open choices from the digest to Dom, then draft `spec/SPEC.md` and `spec/conformance.md`, then stop for Dom's review (gate 1).** Everything is committed and pushed, except this handoff and the digest (local, see §7).

## 2. Read first
1. `<sff>/AGENTS.md` (rules for that repo; §4 spec first, §6 git rules) and `<sff>/README.md` (normative: scope, compatibility, versioning, conformance).
2. `<sff>/decisions/README.md` (Active ADRs) and `<sff>/decisions/open-work.md`.
3. `<sc>/research/CAPTURE_AND_RECORDING_PLAN.md` **rev 3.10**: revision history (top), D20–D26 in §6, row 1.5 (writer), row 1.9 (player), §3.1 (now a phase-2 item, D26).
4. `<sc>/research/skellycam_recording/docs/spec_inputs_digest.md`: the inputs for the draft, by spec section, ending with **"Decisions Dom must still make" (22 items)**.
5. The older handoffs give background only: `research/HANDOFF_20261111_capture_recording.md`, and the morning handoff of 2026-11-12 (a temp file, not in the repo).

## 3. What was decided today (pointers)
**Process (plan D22, `<sff>` ADR-5PP8 items 6–12, `<sff>/AGENTS.md` §4):**
- For each interface: spec text + written conformance list → **gate 1** (Dom reviews) → runnable failing tests + golden files → **gate 2** (Dom reviews) → implementation. No implementation code before gate 2.
- A decision (for example "option C") is not a go-ahead to build. A bug fix needs only a failing test first.
- Requirement IDs `SFF-NNN`, test IDs `SFT-NNN` in `spec/conformance.md`; `tools/check_spec_traceability.py` checks them (ids in number order, each requirement tested, each test cites existing requirements).

**skellyfileformat** (plan D23; `<sff>` ADR-5PP8):
- Public on `domisjustanumber`; Apache-2.0 code, CC-BY-4.0 spec text. Commit straight to `main` until v2.0.0; ask Dom before every push.
- **It describes a whole synchronised recording**, not only each file (ADR-5PP8, supersedes CD4G and 83Y4). Each file's sidecar header holds the recording facts and is authoritative; the spec also defines a **derived recording manifest** (written at finalisation; readers must work without it; headers win). skellycam's info JSON stays skellycam's file. Legacy stays in skellycam.
- Active format ADRs: 69YS (64 B record), 0YV1 (fitted time), CA03 (FLAC), 77Z3 (embed, verify, delete), VJ14 (one package + spec), 5K7G (no overlays), X7FT (read old, write new), M4DF (versioning), 5PP8 (whole recording + repo rules), CE4D (rotation).

**Plan decisions (rev 3.8–3.10):**
- D20: the player's protocol serves only recordings the page opened (option C). The early `skrec://` code is a prototype patch only: `research/skellycam_recording/recording_upgrade/scripts/range_transport/prototype_skrec.patch`.
- D21: one semver for all of skellycam; format version = `major.minor` of the skellycam release that last changed the format; u16 `major`/`minor`/`prerelease` in each sidecar header; a writer string.
- D24: the agents-and-ADR kit (from `../project/agents-and-adr-process`) goes into both repos. Done for `<sff>`; **not started for skellycam** (§6).
- D25 / ADR-CE4D: **rotation is stored only in the sidecar header** (`display_rotation`); frames stay as the camera sent them; no container flag. General players show sensor orientation.
- D26: **freemocap will not use skellycam until phase 2 is complete.** Phase 1 need not keep freemocap working; §3.1 and T-FMC move to phase 2. D19 still applies (new skellycam reads old recordings).

## 4. Evidence added today
| File (under `<sc>/research/skellycam_recording/`) | What it settles |
|---|---|
| `recording_upgrade/results/flac_skau/FINDINGS.md` §7 + `terminate_kill.json`, script `scripts/flac_skau/terminate_kill.py` | 40 external kills: no torn records, no CRC failures; at most one timing record and one whole FLAC frame without a packet record; recovery an exact prefix 40/40 |
| `recording_upgrade/results/rotation_flag/FINDINGS.md` + JSON, scripts `scripts/rotation_flag/` | VLC 3.0.24 honours no MKV rotation flag; PyAV 19.0.2 can write `Projection/ProjectionPoseRoll` (`set_display_rotation`); OpenCV/PyAV/VLC disagree |
| `docs/recording_folder_files.md` | Every file skellycam writes today: fields, what defines them (code only, no schema, no versions), who reads them |
| `docs/manifest_field_review.md` | No manifest is needed to play if headers carry the recording facts; verdict per field; candidate header fields MUST 1–7 / SHOULD 8–11 |
| `docs/spec_inputs_digest.md` | The spec-draft inputs and the 22 open choices |

## 5. Next step: step 5, the spec draft
1. **Put the open choices to Dom first.** Use the 22 items at the end of the digest. Use the `mattpocock-skills:grilling` format (numbered rounds, a recommendation per question, ask only the questions whose prerequisites are settled). Highlights: requirement numbering (blocks per section, e.g. §5 = SFF-200…), the recording manifest (name, fields, when written), fixed binary vs a JSON block, `display_rotation` direction, camera identity (`camera_label` + hashed `camera_key`), flag bits, record extensibility (`record_size`), CRC failure handling, frames without records at recovery, sidecar integrity hash, interrupted embed, embedded vs separate precedence, clock ids, S6 names, version values for prerelease builds.
2. **These questions from earlier today are still unanswered** (they overlap with the digest list; ask them in the same rounds):
   - the header field list (MUST 1–7, SHOULD 8–11) as the basis of the draft;
   - camera key form: 64-bit truncated SHA-256, raw serials only in skellycam's local cache;
   - `camera_label` collisions: today's id is a 16-bit hash (~0.2 % collision chance at 16 cameras); refuse duplicates in one take now, lengthen later;
   - skellycam-side items for skellycam's own spec: write `<rec>_info.json` at record start and update at finalisation; add `info_version`; stop writing the absolute `recording_directory`.
3. **Then draft** `<sff>/spec/SPEC.md` and `<sff>/spec/conformance.md` from the digest and the answers. Also update `<sff>/README.md` Scope (it still lists only per-file formats; ADR-5PP8 widened it). Mark provisional parts (open-work.md). Run `uv run pytest` and the checks.
4. **Stop at gate 1.** Commit locally; ask Dom before pushing. After gate 1: absorb the ADRs whose rules the spec now states (open-work.md item 1).

## 6. Other open items
- **Tonight's 4-camera run** (`research/usb_cameras/suite/windows/HANDOFF_4CAM_20261112.md`) runs in a separate session at 23:00. Its write-up is expected as `research/usb_cameras/docs/windows_results_20261113.md`. Do not run camera commands or heavy work while it runs.
- **skellycam kit branch (plan step 7):** a branch from `upstream/development` on Dom's fork, modules `skellycam/` and `skellycam-ui/`; D1–D14 and D20 become ADRs; the private-data check allows the username-path pattern only inside `research/` (3,754 tracked files there have it; Dom chose to keep them). Upstream PR only after Dom talks to the maintainers.
- **Transport spec (step 8)** for D20, then the other skellycam specs (capture interface, writer, freemocap contract, recording-folder files), drafted in `research/specs/` until the kit branch exists.
- **D26 open:** freemocap pins skellycam `branch = "main"`; phase 1 reaches freemocap when it merges unless freemocap pins an exact revision first.
- **S10b:** correct the 9–74 ms early audio of old recordings in playback? (Dom.)
- **skellysync open decisions** D-Q, D-FPS, D-HDR, D-DRIFT (its own session); the skellysync camera sidecar header stays provisional until then.
- **Phase-1 worktree** `<p1>` is clean at `7d06ba2e1` (package 1.0 only; 7 commits not pushed, by design). It does not build: TypeScript 6.0.3 rejects the deprecated `baseUrl`, and `src/store/index.ts` imports a missing `./slices/connection`. `@rollup/rollup-win32-x64-msvc` is still `^4.60.4` (not an exact pin). Electron is not downloaded in that worktree.

## 7. Uncommitted / unpushed right now
- `<sc>`: this handoff and `docs/spec_inputs_digest.md` (commit locally; push only when Dom says).
- Everything else is pushed: `<sc>` `dom/research` at `12efe7354`; `<sff>` `main` at `359b579` (CI green: Doc checks, Secret scan).

## 8. Gotchas learned today
- **skellyfileformat tools:** run them with `uv run` from that repo, never from another Python (a parent Python 3.12 leaks into the child 3.13: "SRE module mismatch"). `unset VIRTUAL_ENV` first (the skellycam venv is often active). Run `git fetch` before `tools/check_decision_log.py --new`, or it fails.
- **Decision log rules that bit:** an index row's Decision cell is limited to 160 characters; a change to any rule of an accepted entry needs a new entry that supersedes the old one **in full** (restate the rules that stay); status line form `superseded by [ID](ID-slug.md), date (source)`; commit subjects end with `(ADR-<ID>)`; one commit per entry.
- **Private data:** `<sff>/.private-terms` (untracked) blocks the machine name, Dom's personal email, camera/peripheral serials and the telemetry id. Never print or publish Dom's email; commits use the GitHub noreply address (checked: all commits so far). When checking emails, print counts only.
- **No AI attribution** in commits or PRs (kit rule, Dom agreed); the commit-msg hook warns.
- **Sub-agents:** they cannot write `.md` reports; ask for text, check key numbers against their JSON/code, then save with a provenance line. Ban network commands explicitly in the brief (one ran `git fetch --dry-run`). Large reports arrive as a saved tool-result file; navigate it by headings.
- **VLC orientation:** the scene filter and rc `snapshot` save the picture before VLC applies orientation; only a screen grab of the window shows it (`scripts/rotation_flag/vlc_window.py`).
- **Kill tests:** an unpaced writer can finish before a random kill lands; loop the source until killed and count only trials with a non-zero exit code.
- The morning handoff's gotchas still hold (PyAV fixed `Fraction(1, fps)` time base; VLC headless via PowerShell `Start-Process` with `WaitForExit`; Electron 35.7.5 is in the main checkout's `skellycam-ui/node_modules`, 45.2.3 in an old scratchpad; unset `ELECTRON_RUN_AS_NODE`; `skellylogs` needs `python -X utf8` under `-I`; never kill Dom's `OpenMMLab-Exporter` job).

## 9. Suggested skills
- `mattpocock-skills:grilling` — for the 22 open choices before the draft.
- `mattpocock-skills:domain-modeling` — a glossary for the spec (recording, take, sidecar, `.skau`, Segment UID, live/final offset, fitted time, `write_index`).
- `mattpocock-skills:tdd` — at gate 2 (runnable failing tests and golden files).
- `mattpocock-skills:code-review` — on the `<sff>` tools and, later, the implementation.
