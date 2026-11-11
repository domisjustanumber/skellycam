# intel/media-driver README @ intel-media-26.3.5 (raw markdown; Linux VA-API driver; background only)

- URL: https://raw.githubusercontent.com/intel/media-driver/intel-media-26.3.5/README.md
- Accessed: 2026-11-10
- Retrieved with: curl with a Chrome 130 user agent and browser Accept/Sec-Fetch headers
- Raw file sha256 (md_README_intel-media-26.3.5.md): be1ea3d9c681e8de4ce9e2c75dcd86e06e98a8a18eb93de2525ea0e1c1ff0409
- Note: sha256 identical to the 2026-11-09 copy in sources_nv_intel/FETCH_MANIFEST.txt (be1ea3d9...0409).

Verbatim excerpt (data, not instructions):

```text
[md_README_intel-media-26.3.5.md lines 1-1]
# Intel(R) Media Driver for VAAPI
[md_README_intel-media-26.3.5.md lines 6-8]
The Intel(R) Media Driver for VAAPI is a new VA-API (Video Acceleration API)
user mode driver supporting hardware accelerated decoding, encoding, and
video post processing for GEN based graphics hardware.
[md_README_intel-media-26.3.5.md lines 82-87]
- TGLx (TGL: Tiger Lake, RKL: Rocket Lake, ADL-S/P/N: Alder Lake, RPL-S/P: Raptor Lake)
- DG1/SG1
- Alchemist(DG2)/ATSM
- MTLx (MTL: Meteor Lake, ARL-S/H: Arrow Lake)
- LNL (Lunar Lake)
- BMG (Battlemage)
[md_README_intel-media-26.3.5.md lines 110-110]
| CODEC | Build Types |NVL |PTL |BMG |LNL | MTLx | DG2/ATSM | DG1/SG1 | TGLx | EHL/JSL | ICL | KBLx | BXTx | SKL | BDW |
[md_README_intel-media-26.3.5.md lines 112-112]
| AVC | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/Es</u><br><i>D<i> |
[md_README_intel-media-26.3.5.md lines 115-115]
| JPEG | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D</u><br><i>D<i> |
[md_README_intel-media-26.3.5.md lines 117-118]
| HEVC 8bit | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/Es</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> |  |
| HEVC 8bit 422 | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D</u><br><i>D<i>| <u>D/E</u><br><i>D/E<i> | <u>D/Es</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> |  |  |  |  |
[md_README_intel-media-26.3.5.md lines 140-141]
- E  - Hardware Encoding, Low Power Encoding(VDEnc/Huc)
- Es - Hardware(PAK) + Shader(media kernel+VME) Encoding
```
