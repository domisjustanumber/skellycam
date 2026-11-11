# Intel, "Media Capabilities Supported by Intel Hardware" v1.1: Features and Formats (Encode Features tables)

- URL: https://www.intel.com/content/www/us/en/docs/onevpl/developer-reference-media-intel-hardware/1-1/details.html
- Accessed: 2026-11-10
- Retrieved with: curl with a Chrome 130 user agent and browser Accept/Sec-Fetch headers
- Raw file sha256 (onevpl_1-1_details.html): bd828dd6c5336fe03fe231ea1bc28bf6aa70e8593051e3041795cdf8ef6b4b34
- Note: Table 2 columns: Iris Xe MAX | Arc A-Series. Table 3 column: 11th, 12th and 13th Gen Core.

Verbatim excerpt (data, not instructions):

```text
[onevpl_details_rows.txt lines 11-13]
### table 2 (after heading: Encode Features)
 | Format/Feature | Intel® Iris® Xe MAX Graphics | Intel® Arc™ A-Series Graphics
AVC | 8-bit, 4:2:0 (NV12) | ✔4k | ✔4k
[onevpl_details_rows.txt lines 44-56]
MJPEG Encode | 4:2:0 (NV12) | ✔16k | ✔16k
 | 4:2:2 (YUY2) | ✔ 16K | ✔16k
 | 4:2:2(UYVY) | ✔16k | ✔16k
 | 4:4:4 (AYUV) | ✔16k | ✔16k
 | ABGR | ✔16k | ✔16k
 | Y8 | ✔16k | ✔16k
HEVC | 8-bit, 4:2:0 (NV12) | ✔16k | ✔16k
 | 10-bit, 4:2:0 (P010) | ✔16k | ✔16k
 | 8-bit, 4:2:2 (YUY2) |  | ✔16k (Windows Only)
 | 10-bit, 4:2:2 (Y210) |  | ✔16k (Windows Only)
 | 8-bit, 4:4:4 (AYUV) | ✔16k | ✔16k
 | 10-bit, 4:4:4 (Y410) | ✔16k | ✔16k
 | I frame | ✔16k | ✔16k
[onevpl_details_rows.txt lines 61-67]
HEVC (fixed-function hardware + shader-based) | 8-bit, 4:2:0 (NV12) | ✔8k |
 | 10-bit, 4:2:0 (P010) | ✔8k |
 | 12-bit, 4:2:0 (P016) | ✔8k |
 | 8-bit, 4:2:2 (YUY2) | ✔4k |
 | 10-bit, 4:2:2 (Y210) | ✔4k |
 | 12-bit, 4:2:2 (Y216) | ✔4k |
 | Sliding window | ✔ |
[onevpl_details_rows.txt lines 94-96]
### table 3 (after heading: Encode Features)
Codec | Format/Feature | 11th, 12th, and 13th Generation Intel® Core™
AVC | 8-bit, 4:2:0 (NV12) | ✔4k
[onevpl_details_rows.txt lines 126-147]
MJPEG Encode | 4:2:0 (NV12) | ✔16k
 | 4:2:2 (YUY2) | ✔16k
 | 4:2:2(UYVY) | ✔16k
 | 4:4:4 (AYUV) | ✔16k
 | ABGR | ✔16k
 | Y8 | ✔16k
HEVC | 8-bit, 4:2:0 (NV12) | ✔16k
 | 10-bit, 4:2:0 (P010) | ✔16k
 | 8-bit, 4:4:4 (AYUV) | ✔16k
 | 10-bit, 4:4:4 (Y410) | ✔16k
 | I frame | ✔16k
 | Low Delay B | ✔
 | Random access B | ✔
 | Screen Content Coding (SCC) | ✔
 | BRC modes | CBR VBR LA LA_ICQ LA_EXT LA_HRD QVBR
HEVC (fixed-function hardware + shader-based) | 8-bit, 4:2:0 (NV12) | ✔8k
 | 10-bit, 4:2:0 (P010) | ✔8k
 | 12-bit, 4:2:0 (P016) | ✔8k
 | 8-bit, 4:2:2 (YUY2) | ✔4k
 | 10-bit, 4:2:2 (Y210) | ✔4k
 | 12-bit, 4:2:2 (Y216) | ✔4k
 | Sliding window | ✔
```
