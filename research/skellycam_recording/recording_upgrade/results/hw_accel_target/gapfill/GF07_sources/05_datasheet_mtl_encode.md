# Intel, Core Ultra (Series 1) Datasheet Vol. 1 of 2 (Meteor Lake U/H/U-Type4), ID 792044, 05/09/2025, rev 008, Public: "Hardware Accelerated Video Encode"

- URL: https://edc.intel.com/content/www/us/en/design/products/platforms/details/meteor-lake-u-p/core-ultra-processor-datasheet-volume-1-of-2/hardware-accelerated-video-encode/
- Accessed: 2026-11-10
- Retrieved with: curl with a Chrome 130 user agent and browser Accept/Sec-Fetch headers
- Raw file sha256 (mtl_ds_encode.html): 7f1a6f2578dbe66891e6e923e2a4514db314deec568b182575ce065e869a9571

Verbatim excerpt (data, not instructions):

```text
[mtl_ds_encode_rows.txt lines 3-4]
ID | Date | Version | Classification
792044 | 05/09/2025 | 008 007 006 003 002 001 | Public
[mtl_ds_encode_rows.txt lines 6-13]
### table 2 (after heading: Hardware Accelerated Video Encode)
Codec | Profile | Level | Maximum Resolution
AVC/H264 | High Main Constrained Baseline | L5.2 | 4K@60
JPEG |  |  | 16Kx16K
HEVC/H265 | Main10 422 - 8b/10b | L5.2 | 4K@60
Main Main10 420, 444 - 8b/10b SCC 420 444 - 8b/10b | L6.1 | 4320p(8K) @60 16Kx12K
VP9 | 0 (420 8b) 1 (444 8b) 2 (420 10b) 3 (444 10b) | — | 8K @30
AV1 | Main (4:2:0 8b, 10b) | L6 | 8K@30
[mtl_ds_encode.txt lines 1068-1074]
The HW encode is exposed by the graphics driver using the following APIs:
Direct3D12 Video API
Intel®one VPL
MFT (Media Foundation Transform) filters [Only for AVC/HEVC/JPEG/AV1 Encoder]
Xe supports full HW accelerated video encoding for AVC/HEVC/VP9/JPEG/AV1.
Hardware Accelerated Video Encode
 |
```
