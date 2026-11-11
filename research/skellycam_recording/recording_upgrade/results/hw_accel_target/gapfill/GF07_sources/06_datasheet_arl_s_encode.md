# Intel, Core Ultra 200S/200HX Datasheet Vol. 1 of 2 (Arrow Lake-S), ID 832586, 03/17/2026, rev 007, Public: "Hardware Accelerated Video Encode" and "API Support (Windows*)"

- URL: https://edc.intel.com/content/www/us/en/design/products/platforms/details/arrow-lake-s/core-ultra-200s-series-processors-datasheet-volume-1-of-2/hardware-accelerated-video-encode/ and .../api-support-windows/
- Accessed: 2026-11-10
- Retrieved with: curl with a Chrome 130 user agent and browser Accept/Sec-Fetch headers
- Raw file sha256 (arls_ds_encode.html): a905ae573d3c90525b345024308a58682a2ce61158be99c7229ce0136971c2db
- Note: api-support-windows raw sha256 is in GF07_manifest.json (arls_ds_apiwin.html).

Verbatim excerpt (data, not instructions):

```text
[arls_ds_encode_rows.txt lines 3-4]
ID | Date | Version | Classification
832586 | 03/17/2026 | 007 006 005 004 003 002 001 | Public
[arls_ds_encode_rows.txt lines 6-13]
### table 2 (after heading: Hardware Accelerated Video Encode)
Codec | Profile | Level | Maximum Resolution
AVC/H264 | High Main Constrained Baseline | L5.2 | 4K@60
JPEG |  |  | 16Kx16K
HEVC/H265 | Main10 422 - 8b/10b | L5.2 | 4K@60
Main Main10 420, 444 - 8b/10b SCC 420 444 - 8b/10b | L6.1 | 4320p(8K) @60 16Kx12K
VP9 | 0 (420 8b) 1 (444 8b) 2 (420 10b) 3 (444 10b) | — | 8K @30
AV1 | Main (4:2:0 8b, 10b) | L6 | 8K@30
[arls_ds_encode.txt lines 1-1]
 Hardware Accelerated Video Encode - 007 - ID:832586 | Intel® Core™ Ultra 200S, Intel® Core™ Ultra 200S Plus ,Intel® Core™ Ultra 200HX and 200HX Plus Series Processors
[arls_ds_encode.txt lines 687-692]
Xe implements a low-power low-latency fixed function encoder which supports AVC, HEVC, VP9 and AV1.
The HW encode is exposed by the graphics driver using the following APIs:
Direct3D12 Video API
Intel®one VPL
MFT (Media Foundation Transform) filters [Only for AVC/HEVC/JPEG/AV1 Encoder]
Xe supports full HW accelerated video encoding for AVC/HEVC/VP9/JPEG/AV1.
[arls_ds_apiwin.txt lines 686-687]
 API Support (Windows*)
Direct3D* 2015, Direct3D 12, Direct3D 11.2, Direct3D 11.1, Direct3D 9, Direct3D 10, Direct2D
```
