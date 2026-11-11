# Intel, 13th Gen / 14th Gen Core Datasheet Vol. 1 of 2 (Raptor Lake), ID 743844, 05/30/2025, rev 015, Public: "Hardware Accelerated Video Encode"

- URL: https://edc.intel.com/content/www/us/en/design/products/platforms/details/raptor-lake-s/13th-generation-core-processors-datasheet-volume-1-of-2/hardware-accelerated-video-encode/
- Accessed: 2026-11-10
- Retrieved with: curl with a Chrome 130 user agent and browser Accept/Sec-Fetch headers
- Raw file sha256 (rpls_ds_encode.html): 318bb1b98b37240de218c750695470cfedbd052fe1b14e0b87f259d5c3b4d6c0

Verbatim excerpt (data, not instructions):

```text
[rpls_ds_encode_rows.txt lines 3-4]
ID | Date | Version | Classification
743844 | 05/30/2025 | 015 014 011 010 009 008 007 006 005 004 003 002 | Public
[rpls_ds_encode_rows.txt lines 6-11]
### table 2 (after heading: Hardware Accelerated Video Encode)
Codec | Profile | Level | Maximum Resolution
AVC/H264 | High Main | L5.1 | 2160p(4K)
JPEG | Baseline | — | 16Kx16K
HEVC/H265 | Main Main10 Main 4:2:2 10 Main 4:4:4 Main 4:4:4 10 | L5.1 | 4320p(8K) 16Kx4K @higher freq
VP9 | 0 (4:2:0 Chroma 8 bit) 1 (partial: 4:4:4 8 bit) 2 (partial: 4:2:0 10 bit) 3 (partial: 4:4:4 10 bit) | — | 4320p(8K) 16Kx4K @higher freq
[rpls_ds_encode.txt lines 599-605]
The HW encode is exposed by the graphics driver using the following APIs:
Intel® Media SDK
MFT (Media Foundation Transform) filters
Xe supports full HW accelerated video encoding for AVC/HEVC/VP9/JPEG.
Hardware Accelerated Video Encode
 |
Codec |
```
