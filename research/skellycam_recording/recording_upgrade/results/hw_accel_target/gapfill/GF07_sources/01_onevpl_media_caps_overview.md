# Intel, "Media Capabilities Supported by Intel Hardware", oneVPL developer reference, ID 772607, v1.1 (latest), dated 3/07/2024: overview (Encode Support tables)

- URL: https://www.intel.com/content/www/us/en/docs/onevpl/developer-reference-media-intel-hardware/1-1/overview.html
- Accessed: 2026-11-10
- Retrieved with: curl with a Chrome 130 user agent and browser Accept/Sec-Fetch headers
- Raw file sha256 (onevpl_1-1_overview.html): 29a1e02014e5277c97b851be5cd52a3051a18924b79e7fbfc88f3d67bfaeb739
- Note: Rows are table cells joined by " | " (tools/rows.py on the raw HTML); an empty cell is an empty string between bars. The ".../current/overview.html" URL redirects to this 1-1 page.

Verbatim excerpt (data, not instructions):

```text
[onevpl_1-1_overview.txt lines 51-52]
 ID 772607
 Date 3/07/2024
[onevpl_1-1_overview.txt lines 72-72]
 NOTE: Intel® Core™ Processors without processor graphics do not have media support. Codec capabilities may vary by device and configuration. Contact your manufacturer to understand the enabled hardware acceleration and codec capabilities for individual devices.
[onevpl_1-1_overview.txt lines 146-146]
 NOTE: If not specified, an encoder is a fixed function hardware-based encoder.
[onevpl_overview_rows.txt lines 11-66]
### table 2 (after heading: Encode Support)
Codec | Intel® Iris® Xe MAX Graphics | Intel® Arc™ A-Series Graphics
AVC 8-bit, 4:2:0 | ✔ | ✔
AVC (fixed-function hardware + shader-based) 8-bit, 4:2:0 | ✔ |
VP8 (fixed-function hardware + shader-based) 8-bit, 4:2:0 |  |
MPEG2 (fixed-function hardware + shader-based) 8-bit, 4:2:0 | ✔ |
MJPEG 8-bit, 4:2:0 | ✔ | ✔
MJPEG 8-bit, 4:2:2 | ✔ | ✔
MJPEG 8-bit, 4:4:4 | ✔ | ✔
HEVC 8-bit, 4:2:0 | ✔ | ✔
HEVC 10-bit, 4:2:0 | ✔ | ✔
HEVC 8-bit, 4:2:2 |  | ✔
HEVC 10-bit, 4:2:2 |  | ✔
HEVC 8-bit, 4:4:4 | ✔ | ✔
HEVC 10-bit, 4:4:4 | ✔ | ✔
HEVC 12-bit |  |
HEVC (fixed-function hardware + shader-based) 8-bit, 4:2:0 | ✔ |
HEVC (fixed-function hardware + shader-based) 10-bit, 4:2:0 | ✔ |
HEVC (fixed-function hardware + shader-based) 12-bit, 4:2:0 | ✔ |
HEVC (fixed-function hardware + shader-based) 8-bit, 4:2:2 | ✔ |
HEVC (fixed-function hardware + shader-based) 10-bit, 4:2:2 | ✔ |
HEVC (fixed-function hardware + shader-based) 12-bit, 4:2:2 | ✔ |
VP9 8-bit, 4:2:0 | ✔ | ✔
VP9 10-bit, 4:2:0 | ✔ | ✔
VP9 8-bit, 4:4:4 | ✔ | ✔
VP9 10-bit, 4:4:4 | ✔ | ✔
AV1 8-bit, 4:2:0; |  | ✔
AV1 10-bit, 4:2:0 |  | ✔

### table 3 (after heading: Encode Support)
Codec | 11th Generation Intel® Core™ Processors | 12th and 13th Generation Intel® Core™ Processors
AVC 8-bit, 4:2:0 | ✔ | ✔
AVC (fixed-function hardware + shader-based) 8-bit, 4:2:0 | ✔ | ✔
VP8 (fixed-function hardware + shader-based) 8-bit, 4:2:0 |  |
MPEG2 (fixed-function hardware + shader-based) 8-bit, 4:2:0 | ✔ | ✔
MJPEG 8-bit, 4:2:0 | ✔ | ✔
MJPEG 8-bit, 4:2:2 | ✔ | ✔
MJPEG 8-bit, 4:4:4 | ✔ | ✔
HEVC 8-bit, 4:2:0 | ✔ | ✔
HEVC 10-bit, 4:2:0 | ✔ | ✔
HEVC 4:2:2 |  |
HEVC 8-bit, 4:4:4 | ✔ | ✔
HEVC 10-bit, 4:4:4 | ✔ | ✔
HEVC 12-bit |  |
HEVC (fixed-function hardware + shader-based) 8-bit, 4:2:0 | ✔ | ✔
HEVC (fixed-function hardware + shader-based) 10-bit, 4:2:0 | ✔ | ✔
HEVC (fixed-function hardware + shader-based) 12-bit, 4:2:0 | ✔ | ✔
HEVC (fixed-function hardware + shader-based) 8-bit, 4:2:2 | ✔ | ✔
HEVC (fixed-function hardware + shader-based) 10-bit, 4:2:2 | ✔ | ✔
HEVC (fixed-function hardware + shader-based) 12-bit, 4:2:2 | ✔ | ✔
VP9 8-bit, 4:2:0 | ✔ | ✔
VP9 10-bit, 4:2:0 | ✔ | ✔
VP9 8-bit, 4:4:4 | ✔ | ✔
VP9 10-bit, 4:4:4 | ✔ | ✔
AV1 |  |

```
