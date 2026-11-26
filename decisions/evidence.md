# Decision log: evidence entries

<!-- kit:evidence-intro -->
These entries are `evidence`: measurements. They are not in the read path. Scan these rows before
you make a measurement, and read the entries that apply ([Rules](README.md#rules)). An entry that an
accepted entry uses, or that a later measurement replaces, is in [historical.md](historical.md).
<!-- /kit -->

### Evidence

| # | Decision | Status |
|---|----------|--------|
| [ETJ1](entries/ETJ1-measurements-m5-to-m7-of-the-bgr-ring.md) | Measurements M5 to M7 of the BGR ring: CRC-32 cost, decode thread CPU and skip rate, capture jitter and the GIL (Windows) | evidence |
| [8RES](entries/8RES-r11-measurements-of-the-5a-recorder.md) | R11 measurements of the 5a recorder: disk stalls, kills with a full queue, fsync cost with 1 to 16 writers, the GIL (Windows) | evidence |
| [953T](entries/953T-r11-measurements-after-the-review-fixes.md) | R11 measurements again after the review fixes and D1; the kill window that loses a second frame | evidence |
| [HDC9](entries/HDC9-measurements-m-prv-1-to-m-prv-5-of-the-preview-sender.md) | M-PRV-1 to M-PRV-5 of the preview sender: uvicorn deflate compresses each JPEG (16.9 against 0.23 ms at 1080p); targets met with it off (Windows) | evidence |
| [3TYP](entries/3TYP-timings-of-the-small-parts-of-the-frame-path.md) | Timings of the small parts of the frame path on synthetic JPEGs: check, hash, parse, puts, mean, pickle, clock read (Windows) | evidence |
| [0ZKW](entries/0ZKW-first-run-of-the-step-4b-preview-benchmarks.md) | First clean run of T-PRV-51 and T-PRV-52: B-1a 0.996 at 30 fps, B-1b 52.5 of 53.1 at 60 fps; B-2 and B-3 met | evidence |
