// Still-image decode test: ImageDecoder, createImageBitmap and <img> for every image in manifest.images.
// Checks decoded content with the 16x9 cell-mean luma grid (expected values from OpenCV / source pixels).
'use strict';
(async () => {
  const res = { key: KEY, images: {} };
  try {
    const M = await manifest();
    const base = Q.get('base') || `${SERVER}/r/`;
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    const check = (src, w, h, grid) => { canvas.width = w; canvas.height = h; ctx.drawImage(src, 0, 0, w, h); return grid16Mad(ctx.getImageData(0, 0, w, h), grid); };
    for (const im of M.images) {
      const r = { mime: im.mime, camera: !!im.camera_bytes, trailing: im.trailing_after_eoi ?? null };
      res.images[im.id] = r;
      if (!im.file) { r.skip = 'not encoded'; continue; }
      const url = base + im.file;
      let bytes;
      try { bytes = await (await fetch(url)).arrayBuffer(); } catch (e) { r.fetchError = String(e); continue; }
      // ImageDecoder
      if (window.ImageDecoder) {
        try {
          const dec = new ImageDecoder({ data: bytes, type: im.mime });
          const { image } = await withTimeout(dec.decode({ frameIndex: 0 }), 5000, 'ImageDecoder');
          r.imageDecoder = { ok: true, w: image.displayWidth, h: image.displayHeight, format: image.format, mad: check(image, im.w, im.h, im.grid) };
          image.close(); dec.close();
        } catch (e) { r.imageDecoder = { ok: false, err: e.name + ': ' + e.message }; }
      }
      // createImageBitmap
      try {
        const bmp = await createImageBitmap(new Blob([bytes], { type: im.mime }));
        r.createImageBitmap = { ok: true, w: bmp.width, h: bmp.height, mad: check(bmp, im.w, im.h, im.grid) };
        bmp.close();
      } catch (e) { r.createImageBitmap = { ok: false, err: e.name + ': ' + e.message }; }
      // <img>
      try {
        const img = new Image(); img.decoding = 'sync';
        await withTimeout(new Promise((ok, bad) => { img.onload = ok; img.onerror = () => bad(new Error('img onerror')); img.src = url; }), 5000, 'img');
        r.img = { ok: true, w: img.naturalWidth, h: img.naturalHeight, mad: check(img, im.w, im.h, im.grid) };
      } catch (e) { r.img = { ok: false, err: String(e) }; }
    }
  } catch (e) { res.fatal = String(e); }
  postResult(res);
})();
