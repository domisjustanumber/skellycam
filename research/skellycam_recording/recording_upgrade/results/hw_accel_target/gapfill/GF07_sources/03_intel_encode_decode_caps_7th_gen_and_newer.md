# Intel Developer Zone, "Encode and Decode Capabilities for 7th Generation Intel(R) Core(TM) Processors and Newer", "Updated 6/8/2021" (support KB 000055741 points to it)

- URL: https://www.intel.com/content/www/us/en/developer/articles/technical/encode-and-decode-capabilities-for-7th-generation-intel-core-processors-and-newer.html
- Accessed: 2026-11-10
- Retrieved with: curl with a Chrome 130 user agent and browser Accept/Sec-Fetch headers
- Raw file sha256 (encdec_article.html): d53ee0ddac95262ffc521577be12071ee136be1be94190796519fac000b02f71
- Note: Newest platform in the table is 11th Gen / Iris Xe MAX.

Verbatim excerpt (data, not instructions):

```text
[encdec_article.txt lines 50-50]
 Updated 6/8/2021
[encdec_article.txt lines 61-62]
7th generation Intel® Core™ processors and newer implement various media codecs in hardware as well as a rich set of processing algorithms. Table 1 provides the supported video codecs for these processors.
Table 1. Media codec support
[encdec_article.txt lines 100-104]
Notes:
 1 Stereoscopic 3D (S3D) supported on native HDMI 1.4 or HDMI 2.0 ports. S3D is not supported if LSPCON is used.
 2 HEVC encode supports Low Delay B-frame (LDB) and Random Access Hierarchical B-frame (HB). P-frame is not supported.
 3 Encode supported only on Linux
 For all processor graphics listed here, there is no limitation on the number of concurrent sessions to transcode.
[encdec_article_rows.txt lines 2-9]
### table 1 (after heading: Table 1. Media codec support)
Processor Graphics | JPEG | MJPEG | MPEG-2 (H.262) | MPEG-4 AVC1 (H.264) 8-bit 4K | MVC (H.265) | HEVC1,2 (H.265) 8 bit 4:2:0 | HEVC1,2 (H.265) 10 bit 4:2:0 | HEVC (H.265) 12 bit | VC1 | VP8 | VP9 8 bit 4:2:0 | VP9 10 bit 4:2:0 | VP9 12 bit | AV1
Intel® Discrete Graphics
Intel® Iris® Xe MAX Graphics | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Decode only | Decode only | Yes | Yes | Yes | No | Decode only
11th Generation Intel® Core™ Processors
Intel® Iris® Xe Graphics | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Decode only | Decode only | Yes | Yes | Yes | No | Decode only
Intel® UHD Graphics for 11th Gen | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Decode only | Decode only | Yes | Yes | Yes | No | Decode only
Intel® UHD Graphics 750 | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Decode only | Decode only | Yes | Yes | Yes | No | Decode only
```
