# Intel, Core Ultra 200V Datasheet Vol. 1 of 2 (Lunar Lake), ID 829568, 05/27/2025, rev 004, classification shown on the page: "Confidential": "Hardware Accelerated Video Encode"

- URL: https://edc.intel.com/content/www/us/en/secure/design/confidential/products/platforms/details/lunar-lake-mx/core-ultra-200v-series-processors-datasheet-volume-1-of-2/hardware-accelerated-video-encode/
- Accessed: 2026-11-10
- Retrieved with: curl with a Chrome 130 user agent and browser Accept/Sec-Fetch headers
- Raw file sha256 (lnl_ds_encode.html): a7a2c5375836aee0ee373d553978c4bf2b08545d09ff498a0dd2aee239b31525
- Note: CAUTION: the page carries the classification "Confidential" although it was served to an anonymous request (no sign-in, no cookies) on 2026-11-10. Only this short excerpt is kept; the raw page stays in the scratchpad. Dom should decide whether PLAN.md may cite it.

Verbatim excerpt (data, not instructions):

```text
[lnl_ds_encode_rows.txt lines 3-4]
ID | Date | Version | Classification
829568 | 05/27/2025 | 004 | Confidential
[lnl_ds_encode_rows.txt lines 6-11]
### table 2 (after heading: Hardware Accelerated Video Encode)
Codec | Profile | Level | Maximum Resolution
AVC/H264 | High Main Constrained Baseline | L5.2 | 4K @ 60
JPEG |  |  | 16Kx16K
HEVC/H265 | Main Main10 420, 444 - 8b/10b SCC 420 444 - 8b/10b | L6.1 | 4320p(8K) @60 16Kx12K
AV1 | Main (4:2:0 8b, 10b) | L6 | 8K @ 30
[lnl_ds_encode.txt lines 970-976]
The HW encode is exposed by the graphics driver using the following APIs:
Direct3D12 Video API
Intel®one VPL
MFT (Media Foundation Transform) filters [Only for AVC/HEVC/JPEG/AV1 Encoder]
Xe2 supports full HW accelerated video encoding for AVC/HEVC/JPEG/AV1.
Hardware Accelerated Video Encode
 |
```
