"""Image metrics for CTRL-EFFECT checks on JPEG frames (needs Pillow and numpy; import fails cleanly otherwise).

    from common import imgmetrics as im
    im.luma_mean(jpeg)            # mean luma 0..255 (exposure / gain effect)
    im.rb_ratio(jpeg)             # mean R / mean B (white-balance temperature effect: higher K -> warmer -> larger)
    im.sharpness(jpeg)            # normalised Laplacian variance (focus effect with AF off)

``roi`` is (left, top, right, bottom) as fractions of the image (0..1), e.g. (0.25, 0.25, 0.75, 0.75) for the
centre; None = the whole frame. Frames show the user's room: compute metrics, never store full frames in the repo.

The suites declare ``pillow`` and ``numpy`` in their PEP 723 headers; ``available()`` says whether they import.
"""
from __future__ import annotations

import io
from typing import Any, Sequence


def available() -> dict[str, bool]:
    out = {}
    for mod in ("PIL", "numpy"):
        try:
            __import__(mod)
            out[mod] = True
        except Exception:
            out[mod] = False
    return out


def _open(jpeg: bytes, mode: str, draft_scale: int = 1):
    from PIL import Image
    img = Image.open(io.BytesIO(jpeg))
    if draft_scale > 1 and img.format == "JPEG":
        # libjpeg DCT scaling: decodes at 1/2, 1/4 or 1/8 size (fast, fine for means)
        img.draft("L" if mode == "L" else "RGB", (max(1, img.width // draft_scale), max(1, img.height // draft_scale)))
    return img.convert(mode)


def _crop(img, roi: Sequence[float] | None):
    if not roi:
        return img
    l, t, r, b = roi
    w, h = img.size
    box = (int(round(l * w)), int(round(t * h)), max(int(round(l * w)) + 1, int(round(r * w))),
           max(int(round(t * h)) + 1, int(round(b * h))))
    return img.crop(box)


def luma_mean(jpeg_bytes: bytes, roi: Sequence[float] | None = None, draft_scale: int = 4) -> float:
    """Mean of the decoded luma (Pillow 'L' = ITU-R 601 Y') over ``roi``; 0..255."""
    import numpy as np
    img = _crop(_open(jpeg_bytes, "L", draft_scale), roi)
    return float(np.asarray(img, dtype=np.float64).mean())


def rb_ratio(jpeg_bytes: bytes, roi: Sequence[float] | None = None, draft_scale: int = 4) -> float:
    """mean(R) / mean(B) over ``roi`` (B floored at 1e-6). Rises with the white-balance temperature setting."""
    import numpy as np
    a = np.asarray(_crop(_open(jpeg_bytes, "RGB", draft_scale), roi), dtype=np.float64)
    return float(a[..., 0].mean() / max(a[..., 2].mean(), 1e-6))


def rgb_means(jpeg_bytes: bytes, roi: Sequence[float] | None = None, draft_scale: int = 4) -> dict[str, float]:
    """{"r","g","b"} channel means over ``roi``."""
    import numpy as np
    a = np.asarray(_crop(_open(jpeg_bytes, "RGB", draft_scale), roi), dtype=np.float64)
    return {"r": float(a[..., 0].mean()), "g": float(a[..., 1].mean()), "b": float(a[..., 2].mean())}


def sharpness(jpeg_bytes: bytes, roi: Sequence[float] | None = None, draft_scale: int = 1) -> float:
    """Normalised Laplacian variance: var(4-neighbour Laplacian of luma) / mean(luma)^2 over ``roi``.
    Normalising by brightness keeps exposure changes from looking like focus changes. Full resolution by
    default (downscaling hides fine detail)."""
    import numpy as np
    y = np.asarray(_crop(_open(jpeg_bytes, "L", draft_scale), roi), dtype=np.float64)
    if y.shape[0] < 3 or y.shape[1] < 3:
        return 0.0
    lap = (y[1:-1, :-2] + y[1:-1, 2:] + y[:-2, 1:-1] + y[2:, 1:-1]) - 4.0 * y[1:-1, 1:-1]
    m = float(y.mean())
    return float(lap.var() / max(m * m, 1e-6))


def metrics(jpeg_bytes: bytes, roi: Sequence[float] | None = None) -> dict[str, Any]:
    """All three metrics plus the decoded size; {'error': ...} if the frame does not decode."""
    try:
        from PIL import Image
        w, h = Image.open(io.BytesIO(jpeg_bytes)).size
        return {"w": w, "h": h, "luma_mean": luma_mean(jpeg_bytes, roi), "rb_ratio": rb_ratio(jpeg_bytes, roi),
                "sharpness": sharpness(jpeg_bytes, roi)}
    except Exception as e:  # undecodable frame or missing dependency
        return {"error": f"{type(e).__name__}: {str(e)[:160]}"}
