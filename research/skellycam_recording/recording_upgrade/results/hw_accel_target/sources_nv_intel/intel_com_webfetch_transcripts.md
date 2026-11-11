# intel.com pages: WebFetch transcripts (2026-11-09)

intel.com returns HTTP 403 to curl (both URLs below tried with a browser User-Agent: `403 511` and `403 561` bytes).
These pages were therefore read with the WebFetch tool, which renders the page and answers a prompt with a small model.
Cell values below are that tool's transcription, asked for verbatim. They are lower-fidelity than a saved raw page:
treat any single checkmark as "source (transcribed)" and re-check on the live page before relying on it alone.

## 1. Media Capabilities Supported by Intel Hardware (oneVPL developer reference, doc 772607, v1.1, dated 3/07/2024)

URL: https://www.intel.com/content/www/us/en/docs/onevpl/developer-reference-media-intel-hardware/1-1/overview.html
Covers: Iris Xe MAX, Arc A-Series, 11th Gen, 12th and 13th Gen, 10th Gen. Does NOT cover Meteor Lake, Lunar Lake, Arrow Lake or Arc B-series.
Quoted note: "Codec capabilities may vary by device and configuration." / "If not specified, an encoder is a fixed function hardware-based encoder."

Encode summary table (transcribed):

| Codec | Iris Xe MAX | Arc A-Series | 11th Gen | 12th and 13th Gen | 10th Gen (Ice Lake) | 10th Gen (other) |
|---|---|---|---|---|---|---|
| AVC 8-bit, 4:2:0 | Y | Y | Y | Y | Y | Y |
| HEVC 8-bit, 4:2:0 | Y | Y | Y | Y | Y | |
| HEVC 10-bit, 4:2:0 | Y | Y | Y | Y | Y | |
| HEVC 8-bit, 4:2:2 | | Y | | | | |
| HEVC 10-bit, 4:2:2 | | Y | | | | |
| HEVC 8-bit, 4:4:4 | Y | Y | Y | Y | Y | |
| HEVC 10-bit, 4:4:4 | Y | Y | Y | Y | Y | |
| AV1 8-bit, 4:2:0 | | Y | | | | |
| AV1 10-bit, 4:2:0 | | Y | | | | |
| VP9 8-bit, 4:2:0 | Y | Y | Y | Y | Y | |
| VP9 10-bit, 4:2:0 | Y | Y | Y | Y | Y | |
| MJPEG 8-bit, 4:2:0 | Y | Y | Y | Y | Y | Y |

Decode summary table (transcribed): AVC 8-bit 4:2:0, HEVC 8/10-bit 4:2:0, 4:2:2 and 4:4:4, VP9 8/10-bit 4:2:0 and 4:4:4,
MJPEG 8-bit 4:2:0 checked for all of Iris Xe MAX, Arc A, 11th Gen, 12th/13th Gen. AV1 8/10-bit 4:2:0 decode checked for
Iris Xe MAX, Arc A, 11th Gen, 12th/13th Gen; not for 10th Gen.

Details page (https://www.intel.com/content/www/us/en/docs/onevpl/developer-reference-media-intel-hardware/1-1/details.html), transcribed rows:

- ENCODE-11-12 (11th, 12th, 13th Gen Core), MJPEG Encode: "4:2:0 (NV12) | ✔16k", "4:2:2 (YUY2) | ✔16k", "4:2:2(UYVY) | ✔16k", "4:4:4 (AYUV) | ✔16k", "ABGR | ✔16k", "Y8 | ✔16k"
- ENCODE-11-12, HEVC (fixed-function + shader-based): "8-bit, 4:2:2 (YUY2) | ✔4k", "10-bit, 4:2:2 (Y210) | ✔4k", "12-bit, 4:2:2 (Y216) | ✔4k". No 4:2:2 rows in the plain (fixed-function) HEVC encode table.
- ENCODE-11-12 max res: AVC "8-bit, 4:2:0 (NV12) | ✔4k"; HEVC "8-bit, 4:2:0 (NV12) | ✔16k"; VP9 "8-bit, 4:2:0 (NV12) | ✔8k"; no AV1 encode rows.
- ENCODE-DISCRETE (Iris Xe MAX | Arc A): HEVC "8-bit, 4:2:2 (YUY2) | | ✔16k (Windows Only)", "10-bit, 4:2:2 (Y210) | | ✔16k (Windows Only)"; AV1 "8-bit, 4:2:0 (NV12) | | ✔8k"; VP9 "8-bit, 4:2:0 (NV12) | ✔8k | ✔8k"; AVC "✔4k | ✔4k"; MJPEG 4:2:2 (YUY2) "✔ 16K | ✔16k".
- DECODE-11-12 and DECODE-DISCRETE, MJPEG Decode: "4:2:2, 8-bit → 4:2:2H | ✔16k", "4:2:2, 8-bit → 4:2:2V | ✔16k", "4:2:0/4:2:2H/4:2:2V (inter) → NV12 | ✔16k", "4:2:0/4:2:2H (inter) → YUY2 / UYVY | ✔16k".
- Session limits: WebFetch reported "no statement about concurrent sessions or session limits" on the details page.

## 2. Intel ark (product specification pages)

| SKU | URL | Launch Date | Code name | GPU section (transcribed) |
|---|---|---|---|---|
| Core i7-14700K | https://www.intel.com/content/www/us/en/products/sku/236783/intel-core-i7-processor-14700k-33m-cache-up-to-5-60-ghz/specifications.html | "Q4'23" | (not asked) | "GPU Name‡": "Intel® UHD Graphics 770"; "Multi-Format Codec Engines": "2"; "Intel® Quick Sync Video": "Yes"; "Device ID": "0xA780" |
| Core i7-14700KF | https://www.intel.com/content/www/us/en/products/sku/236789/intel-core-i7-processor-14700kf-33m-cache-up-to-5-60-ghz/specifications.html | "Q4'23" | (not asked) | Processor Graphics / Quick Sync fields not present |
| Core Ultra 7 265KF | https://www.intel.com/content/www/us/en/products/sku/241062/intel-core-ultra-7-processor-265kf-30m-cache-up-to-5-50-ghz/specifications.html | "Q4'24" | "Products formerly Arrow Lake" | GPU Specifications section exists: Graphics Output "n/a", Xe-cores "0", "Intel® Quick Sync Video" "No", # of Displays "0" |
| Core i5-12400F | https://www.intel.com/content/www/us/en/products/sku/134587/intel-core-i512400f-processor-18m-cache-up-to-4-40-ghz/specifications.html | "Q1'22" | "Products formerly Alder Lake" | no GPU section (headings: Essentials, CPU Specifications, Supplemental Information, Memory Specifications, Expansion Options, Package Specifications, Advanced Technologies, Security & Reliability) |
| Core i9-11900KF | https://www.intel.com/content/www/us/en/products/sku/212321/intel-core-i911900kf-processor-16m-cache-up-to-5-30-ghz/specifications.html | "Q1'21" | "Products formerly Rocket Lake" | no GPU section |
| Core i5-10400F | https://www.intel.com/content/www/us/en/products/sku/199278/intel-core-i510400f-processor-12m-cache-up-to-4-30-ghz/specifications.html | "Q2'20" | "Products formerly Comet Lake" | no GPU section |
| Arc B580 Graphics | https://www.intel.com/content/www/us/en/products/sku/241598/intel-arc-b580-graphics/specifications.html | "Q4'24" | Microarchitecture "Xe2" | "H.264 Hardware Encode/Decode": "Yes"; "H.265 (HEVC) Hardware Encode/Decode": "Yes"; "AV1 Encode/Decode": "Yes"; "Multi-Format Codec Engines": "2"; no VP9 or JPEG field |

None of the F/KF pages contains text saying a discrete GPU is required (WebFetch answer for each).
