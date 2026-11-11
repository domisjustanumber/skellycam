# jellyfin_ffmpeg: provenance verification of the draft FINDINGS

Verifier, 2026-11-09, machine Gerald. Lens: does each claim's cited evidence exist, and does it say exactly that? No jellyfin-ffmpeg binary was downloaded or run, and nothing was timed. No previous `VERIFY_provenance.md` existed, so there was nothing to rename.

**What was checked**
- Every file in `J/`.
- The fetched sources in the scratchpad: `.../scratchpad/jellyfin_ffmpeg/`, including `patches/`, `up_*.c`, `jf_index.md`, `gpl-faq.html` and the PyAV changelog.
- The cross-topic files at the cited lines.
- Re-queries via `gh api`: FFmpeg tag objects, the release `published_at`, the tag commit, the repo description and licence, and the builder variants listing.
- One WebFetch of the Jellyfin hardware-acceleration docs page (three quotes present).

## 1. Claims confirmed against evidence

| Claim | Evidence checked | Result |
|---|---|---|
| F1 release, date, commit | `gh api` re-query: 2026-11-03T17:49:24Z, commit 7250de83... | confirmed |
| F2 VERSION/RELEASE 8.1.3 | scratch `VERSION`, `RELEASE`; `build_config_excerpts.txt:206-208` | confirmed |
| F3 9.0.2 / 63.1.102 | `sw_encoders_pyav19_win_amd64.json` keys | confirmed (line cite drifted, see §3) |
| F4 tag dates | `gh api` tag objects: n9.0 2026-08-03T21:21:22Z, n9.0.2 2026-09-18T00:40:57Z, n8.1.3 2026-09-21T00:46:52Z | confirmed |
| F6 README, description | scratch `README.md` line 1-4; `gh api`: description matches, licence NOASSERTION | confirmed |
| F7, F8 Jellyfin quotes + line numbers | `jf_index.md:12,28-44,50,74` (jellyfin.org@4acfc64a); WebFetch of the live page | confirmed, quotes exact |
| F10, F11 106 patches, hdr_lines=0 | `patch_index.txt`: 106 entries, all `hdr_lines=0`; `series` has 106 | confirmed |
| F12 29 names, 2 encoders, transpose_cuda | `grep '^+extern const (FFCodec\|FFFilter\|FFBitStreamFilter)'` over patches = 9 codecs + 19 filters + 1 bsf = 29; `upstream_presence.txt` | confirmed |
| F14-F16 patch 0047 lines | `0047...patch` lines 46, 81-85, 98, 109-126 (long name at 111, CAP_HARDWARE at 115, color_ranges at 119) | confirmed |
| F17 | `upstream_spotcheck*.txt`: 0 | confirmed |
| F18 | `gpu_encode/wheel_hw_codecs.md:7-8` | confirmed |
| F20 | `debian/rules:54-56`; vulkan-loader/libplacebo `ffbuild_enabled` skip `mac*` | confirmed |
| F22 | `gpu_encode/NOTES.md:27,130` | confirmed |
| F23 | `wheel_hw_codecs.md:10` short names include h264_qsv, hevc_qsv, mjpeg_qsv | confirmed (the long-name column has only AV1/VP9 QSV, so "measured" applies only to the short names; hedging is adequate) |
| F24 | patch 0096 lines 9-10; upstream `vaapi_encode_mjpeg.c:586` | confirmed |
| F27, F28 | patch 0097 lines 30-35, 441-442, 458; upstream `mf_utils.c:575,580`, 0 matches | confirmed |
| F29, F30, F32, F34 | `NOTES_functional.md:94`, `:15`, `:91-92`, `:126` | confirmed |
| F33 patch 0013 | lines 9-10 | confirmed |
| F36, F38 | `debian/rules:9-72`; patch 0026; configure n8.1.3:2004-2007; LICENSE.md quote | confirmed |
| F37 | `defaults-gpl.sh:6`; `up_LICENSE_n8.1.3.md:61-64` | confirmed ("binaries are GPLv3" is a short inference from these) |
| F40 sizes | `releases.txt:2-17` (25.5-53.4 MB debs; 68.5/55.8/60.7/54.1/38.1/32.9 MB portable) | confirmed |
| F41 | `default-install.sh:7-11`; `defaults-mac.sh:9`; `.install` | confirmed |
| F42 | PyAV `installation.rst:27`; `setup.py:56-76,123-131` | confirmed (note: setup.py falls back to the dir itself if `include/` or `lib/` is missing, so "expects" is slightly strong) |
| F44 | `sources_excerpts.txt:82-94` | confirmed |
| F46 | `up_demuxers_n9.0.2.texi`, framerate at 1040-1041 | confirmed |
| F47, F48 | `crash_resilience/sfn26_pipe.md` rows | confirmed |
| F51 | `releases.txt:40-60`: 21 releases, 7 prereleases | confirmed |
| §3.1 distribution sizes, wheel tags | `pyav_19.0.2_pypi_files.txt` | confirmed |
| GPL FAQ quote | `gpl-faq.html` (text extracted) | confirmed, exact |
| AGPL code cites | `LICENSE:1`, `LICENSE:553-559`, `pyproject.toml:15` | confirmed |
| F19, F25, F26 cross-topic lines | `NOTES_sources_amd_apple_cpu.md:33,92,119,136`; `NOTES_sources_nvidia_intel.md:38`; `gpu_encode/NOTES.md:17,20,61,69` | confirmed |

## 2. Refuted

| Claim | Why | Correction |
|---|---|---|
| F49, and the §3.1 row "Startup data loss: Up to the 5 MB probe buffer lost if the child dies early (measured, F49)" | `crash_resilience/FINDINGS.md` §2.10 says two source limits fit both runs and were not separated: `probesize` 5000000 and `analyzeduration`, which becomes 5 s (`options_table.h:56`, `demux.c:2638-2641`). It also says "The boundary between 75 and 300 frames was not bisected. The bound is **NOT VERIFIED**." The measurement is only "75 frames, 4.3 MB, killed: no file". | F49: "measured: with 75 frames (4.3 MB) fed, killing ffmpeg left no file. inferred: still probing; probesize (5 MB) or analyzeduration (5 s) could explain it, and they were not separated. Bound NOT VERIFIED (`R/crash_resilience/FINDINGS.md` §2.10)." Table cell: "≥75 frames (4.3 MB) lost when killed early (measured); upper bound NOT VERIFIED". |
| §7: "`J/upstream_spotcheck.txt` ... (commands in `J/NOTES.md`; files saved by `fetch_sources.sh`)" | `J/NOTES.md` has no grep commands. Neither script writes `upstream_spotcheck.txt`, so the file cannot be reproduced from what is cited. | Add the greps (0017 `has_b_frames`/`GopRefDist`, 0071 low-power string, `kCMVideoCodecType_JPEG`, `color_ranges` line, configure 2004-2008, LICENSE.md 117-127) to a script, or quote them in §7. Until then, mark it "commands not recorded". |

## 3. Weak (true or partly true, but the evidence or label needs a fix)

| Claim | Why | Fix |
|---|---|---|
| F50 and §3.1 "Crash behaviour: in-process, MJPEG `nut+fp` 150/150 after kill" vs child killed 0/246/293 | Those 150/150 and 149/150 figures are `drained` mode: kill after all frames were muxed and the encoder drained, before `close()`, "deterministic by construction" (`crash_resilience/FINDINGS.md` §2.1). The subprocess numbers are live kills mid-stream. Like for like, the PyAV 19 live kill is MJPEG mkv+fp **74/75 fed** (`verify_method_pyav19_checks.json` → `rt`, same section). | Say "drained mode" in F50 and add the live-kill row (74/75). Compare live with live in §3.1. |
| F47-F49 labelled "measured" | HANDOFF §1 req. 5: the CLI may be used to inspect files, "not as the implementation under test". F26 already labels CLI results **background**, and crash_resilience calls them "reference only". | Label F47-F49 "background (ffmpeg 9.0.2 CLI stand-in)" to match F26. |
| §3.1 "Per-frame timestamps: Standard (inferred, F46, F50)" | The evidence this row cites points the other way. `R/python_integration/NOTES.md:17-20` (bottom line 3): "For FreeMoCap the video file must be CFR, with the real timestamps kept in a sidecar". So the sidecar a pipe would need is what the plan recommends anyway. | Change it to Tie, or say the advantage applies only if container PTS must carry the real timestamps, citing the python_integration line. |
| §3.1 cadence "FFmpeg 9 adopted 57 days after release" (F52) | Only 19.0.2 is measured to bundle 9.0.2. `releases.txt` and the PyAV v19.0.0 changelog "Major" section (scratch `pyav_CHANGELOG_v19.0.2.rst`) do not say that v19.0.0 moved to FFmpeg 9. v18.1.0 (2026-08-12) also came out after n9.0. | "v19.0.0 was released 57 days after n9.0. Whether it already bundled 9.0.x: NOT VERIFIED (19.0.2 does, F3)." |
| §3.2 `ffv1_vulkan` row: "Shares the 12-session NVENC pool (measured, `gpu_encode/NOTES.md:21`)" | Line 21 tested an extra `h264_vulkan` (Vulkan Video, which uses NVENC). `ffv1_vulkan` is a compute shader and was not tested against the pool. | Limit the caveat to `h264/hevc_vulkan`. For `ffv1_vulkan`: NOT VERIFIED. |
| F13 "nvJPEG stays outside FFmpeg/PyAV (measured, `gpu_encode/NOTES.md` §6)" | §6 shows that nvImageCodec works. It does not show that FFmpeg lacks nvJPEG. Verifier check: upstream n9.0.2 `allcodecs.c` has 0 case-insensitive matches for `nvjpeg` (scratch `up_allcodecs_n9.0.2.c`), and `wheel_hw_codecs.md` lists no nvjpeg name. | Cite those two instead. |
| F31 "QSV encoders open with defaults, with no need for it" | `NOTES_functional.md:15` shows only that they open and work. "No need for 0071" is inferred. Also, 0071 sets `LowPower = MFX_CODINGOPTION_UNKNOWN` (patch line 13), not "off". The log text says "disabled". | Mark "no need" as inferred. Describe it as "retries with LowPower reset to UNKNOWN (driver default)". |
| F45 "self-built `gpl-shared` ... on every OS" | Builder variants at v8.1.3-2 (`gh api .../builder/variants?ref=v8.1.3-2`) include `win64-gpl-shared.sh`, `linux64-gpl-shared.sh` and `linuxarm64-gpl-shared.sh`, but **no mac gpl-shared**, and `defaults-mac.sh:9` forces `--disable-shared`. `windows-install-shared.sh` packages `include/`, `lib/*.lib|*.dll.a` and `.pc` files, which is the layout `setup.py --ffmpeg-dir` expects. | Say gpl-shared exists for Windows and Linux (and packages headers and libs), but not for macOS, where a different build is needed. |
| F19 (Apple hardware JPEG) misses code evidence | 0047's `allow_sw` defaults to 0. Upstream `videotoolboxenc.c:1702-1705` (n9.0.2) then sets `kVTVideoEncoderSpecification_RequireHardwareAcceleratedVideoEncoder = true`. | Add "code: with defaults the encoder *requires* a VT hardware encoder. inferred: if `mjpeg_videotoolbox` opens with `allow_sw=0`, VT reported a hardware JPEG encoder. Still NOT VERIFIED (not run)." |
| F3 / F39 line cites `R/licensing/FINDINGS.md:80`, `:80-82` | In the current file these facts are at lines 83 (FFmpeg 9.0.2, LGPLv3+) and 85 (x264/x265 DLLs). Line 92 is correct. The file is being revised. | Cite by section (§2.5) plus the probe JSON names (`probe_pyav_19.0.2.json`, `revise_pyav_strip_gpl_control_19.0.2.json`). |
| §3.1 "Encoders added over upstream: None; stock upstream codecs (measured, `wheel_hw_codecs.md`)" | The wheel scan lists names. It does not show "stock upstream". pyav-ffmpeg applies `patches/ffmpeg.patch` (`R/licensing/FINDINGS.md` §2.5, line 88). | Label "inferred". Note the licensing patch. |
| §7 reproducibility of the fetch | `fetch_sources.sh` does not fetch these cited inputs: builder `scripts.d` 25-openssl, 45-opencl, 50-dav1d/libvpx/mfx/schannel/svtav1/x264/x265, `50-libplacebo`; the v8.1.3-1 notes; the PyAV release list; the FFmpeg tag dates; the `gh search` / PyPI 404 queries; the GPL FAQ; the PyAV changelog. `upstream_presence.txt` n8.1.3 omits `bitstream_filters.c`, so `trim_bsf n8.1.3=0` is an artifact. The header of `upstream_spotcheck_mf_vt.txt` does not match what `spotcheck_mf_vt.sh` writes. | Add the missing fetches. Mark the n8.1.3 trim_bsf cell "not checked". Regenerate the spotcheck file with the script. |
| §3.1 platform floor "macOS target 12.0 (source, `defaults-mac.sh`)" | True at `defaults-mac.sh:25` (`MACOSX_DEPLOYMENT_TARGET="12.0"`), but `J/build_config_excerpts.txt` copies only lines 1-9 and 30. | Cite line 25 and add it to the excerpt. |
| F21 citation list | `av1_vaapi` is claimed, but its line (`allcodecs.c:860`) is not in the cite list. | Add 860. |
| F25 label "source + code" | It cites another topic's notes file, not a primary source or a file:line in this repo. | Label "measured/source via `R/hw_accel_target/NOTES_sources_amd_apple_cpu.md:33,92,119`". |
| F35 grouping | 0016 (NVDEC) is decode-side, and 0036/0059 are runtime-init patches. They are listed as "encoder-side". | Re-word as "other QSV/NVENC/NVDEC/AMF/VAAPI patches". |

## 4. Verdict

The draft is mostly well sourced. Release, patch, build-config, licence, Jellyfin-doc and cross-topic numbers match their files and re-queried sources, and every quote checked is exact. Two claims are refuted:
- the "up to 5 MB" startup-loss bound, which crash_resilience marks NOT VERIFIED, with analyzeduration as a second explanation;
- §7's statement that the `upstream_spotcheck.txt` commands are in `NOTES.md`.

The main weak points are comparisons that are not like for like, or that the cited evidence does not support:
- the crash row compares in-process drained-mode results with live subprocess kills;
- the timestamp row ignores the plan's own recommendation of CFR video plus a sidecar;
- "FFmpeg 9 adopted in 57 days" is not shown;
- the 12-session caveat is applied to `ffv1_vulkan`;
- CLI results are labelled "measured" in F47-F49 but "background" in F26.

None of these changes the recommendation in §4.1.
