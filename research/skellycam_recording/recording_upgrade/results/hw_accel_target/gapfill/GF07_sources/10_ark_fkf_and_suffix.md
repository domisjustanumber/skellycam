# Intel ark: F/KF desktop SKUs (no processor graphics), i7-14700K contrast, and the processor-number suffix table

- URLs: https://www.intel.com/content/www/us/en/products/sku/<id>/.../specifications.html (ids below); https://www.intel.com/content/www/us/en/processors/processor-numbers.html
- Accessed: 2026-11-10
- Retrieved with: curl with a Chrome 130 user agent and browser Accept/Sec-Fetch headers

Verbatim field/value pairs (label line, then value line, from the page text; data, not instructions). "GPU Specifications" heading count and "Quick Sync" count are grep counts on the downloaded page (measured).

## Core i5-10400F (sku 199278; raw sha256 26418e5ebc7f6afbe225bad05bac7afde919e4bbab7f6b2093f3cb08f7bffc27)
```text
Code Name | Products formerly Comet Lake
Launch Date | Q2'20
```
- "GPU Specifications" in page text: 0; "Quick Sync" in raw HTML: 0

## Core i9-11900KF (sku 212321; raw sha256 ed6e1ec55a2d13ab0e4efa76dc8fcc10efa69f7316c68f7d6656f8017fb1e493)
```text
Code Name | Products formerly Rocket Lake
Launch Date | Q1'21
```
- "GPU Specifications" in page text: 0; "Quick Sync" in raw HTML: 0

## Core i5-12400F (sku 134587; raw sha256 6522953f2de99f096e7912e72451f49af098fad5bb01d05fb69f7bc4cc8dc8b4)
```text
Code Name | Products formerly Alder Lake
Launch Date | Q1'22
```
- "GPU Specifications" in page text: 0; "Quick Sync" in raw HTML: 0

## Core i7-14700KF (sku 236789; raw sha256 25d0ccd585c449ec7aef16ea11e8bda33e230f8879eac1b7d9b63697f3f408d6)
```text
Code Name | Products formerly Raptor Lake
Launch Date | Q4'23
```
- "GPU Specifications" in page text: 0; "Quick Sync" in raw HTML: 0

## Core Ultra 7 265KF (sku 241062; raw sha256 4bac06acf426ddbb5241c587a5c65f9a75a14da53d79aea9284cb0a6c0a1e497)
```text
Code Name | Products formerly Arrow Lake
Launch Date | Q4'24
Graphics Output | n/a
Xe-cores | 0
Intel® Quick Sync Video | No
```
- "GPU Specifications" in page text: 2; "Quick Sync" in raw HTML: 6

## Core i7-14700K (contrast) (sku 236783; raw sha256 8f3240d99de78e728a5f501be0207a443e1de74c0f48b222e142bb9bf0baac69)
```text
Code Name | Products formerly Raptor Lake
Launch Date | Q4'23
GPU Name‡ | Intel® UHD Graphics 770
Graphics Output | eDP 1.4b, DP 1.4a, HDMI 2.1
Multi-Format Codec Engines | 2
Intel® Quick Sync Video | Yes
```
- "GPU Specifications" in page text: 2; "Quick Sync" in raw HTML: 6

## Processor numbers page (raw sha256 f8cf659abd9b5700c24979d125fa49fa801a0ef7c4248b26ca76c10037533c72)
```text
### table 1 (after heading: Suffixes for Intel Core Ultra and Intel Core Processors)
Form/Function Type/Segment | Suffix | Optimized/Designed for
Desktop | K | High performance, unlocked
 | F | Requires discrete graphics
```

## oneVPL media capabilities overview (see 01_onevpl_media_caps_overview.md)
```text
NOTE: Intel® Core™ Processors without processor graphics do not have media support. Codec capabilities may vary by device and configuration. Contact your manufacturer to understand the enabled hardware acceleration and codec capabilities for individual devices.
```
