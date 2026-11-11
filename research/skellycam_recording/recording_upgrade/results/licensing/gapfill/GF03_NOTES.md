# GF03 notes (2026-11-10)

Main report: `GF03_nvjpeg_licence_arch.md`. Source work only: no timing, no installs, no downloaded code executed.

## Files

| file | content |
|---|---|
| `GF03_nvjpeg_licence_arch.md` | quotes table, case (a)/(b) analysis, architecture table, superseded caveats, proposed replacement text |
| `GF03_quote_verification.json` | 72/72 quotes `found_verbatim: true`, with the sha256 of each source text |
| `GF03_fetch_log.json` | 33 downloads (URL, HTTP 200, bytes, sha256) plus gnu.org AGPL (HTTP 403) |
| `GF03_wheel_arch_facts.json` | wheel member lists and sha256, PyPI licence fields, CUDA redistrib libnvjpeg versions, SPDX OSI flags, fatbinary SM lists |
| `GF03_sources/` | short verbatim excerpts per source, plus `nvjpeg_h_12.4.0.76_lines.txt` (header lines with line numbers) |

Scripts are in `scripts/licensing/gapfill/`: `GF03_quotes.json`, `GF03_verify_quotes.py`, `GF03_collect_facts.py`, `GF03_fatbin_archs.py`, `GF03_html_to_text.py`, `GF03_list_wheel.py`, `GF03_extract_member.py`. All of them were run with `python -I`; downloaded files are passed as arguments.

## Reproduce

```
G=C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step3/GF03
S=scripts/licensing/gapfill; R=results/licensing/gapfill
# downloads: curl -sSL -o $G/dl/<file> <url> for each URL in $R/GF03_fetch_log.json; the GitHub tag files via
#   gh api "repos/NVIDIA/nvImageCodec/contents/LICENSE.txt?ref=v0.10.0" -H "Accept: application/vnd.github.raw"
python -I $S/GF03_extract_member.py $G/dl/<wheel> <member> $G/work/lic/<out>      # licence files, METADATA, nvjpeg.h
python -I $S/GF03_html_to_text.py $G/dl/<page>.html $G/work/txt/<page>.txt
python -I $S/GF03_verify_quotes.py --quotes $S/GF03_quotes.json --root $G --out $R/GF03_quote_verification.json --excerpts $R/GF03_sources
python -I $S/GF03_collect_facts.py $G $S/GF03_fatbin_archs.py $R/GF03_wheel_arch_facts.json
```

## Headline points

- source: `nvidia-nvjpeg-cu12==12.4.0.76` is CUDA 12.9 Update 1's libnvjpeg, not CUDA 12.4's (CUDA 12.4 ships 12.3.1.89).
- source: the nvImageCodec licence differs by channel. PyPI metadata and GitHub v0.10.0 say Apache-2.0; the wheel's LICENSE.txt and the docs page are the NVIDIA SLA (v. November 28, 2023).
- source: the nvjpeg wheel carries a 2018 CUDA EULA that lists nvJPEG as distributable on Linux only. The live 2026 EULA lists Windows `nvjpeg.dll` and adds a "develop and test" permission for OSI-licensed applications.
- source: the nvImageCodec SLA §2.11 bars disclosing benchmark results without NVIDIA's permission. That matters if the study's nvJPEG timings are published.
- measured (static): SASS present for sm_75/86/89/120 in `nvjpeg64_12.dll`. nvImageCodec kernels have SASS for sm_70/80/120.
- source: hardware JPEG encode exists on Jetson Thor (SM 10.1) only, so GeForce JPEG encode is the CUDA backend.
- source + inferred, not legal advice: an optional pip extra is low-risk for AGPL skellycam. Bundling the wheels in an installer needs legal review.
