"""Why does the synthetic JPEG payload deflate ~45%? Check JPEG-only bytes. Run with skellycam venv python."""
import zlib, cv2, numpy as np, logging, sys
from ui_tap_bench import synthetic_image
for h, w in [(720,1280),(1080,1920)]:
    img = synthetic_image(h, w, 0)
    r = cv2.resize(img, (w//2, h//2), interpolation=cv2.INTER_LINEAR)
    ok, j = cv2.imencode(".jpg", r, [int(cv2.IMWRITE_JPEG_QUALITY), 60]); jb = j.tobytes()
    enc = zlib.compressobj(wbits=-15); z = enc.compress(jb) + enc.flush(zlib.Z_SYNC_FLUSH)
    print(f"{w}x{h} -> {w//2}x{h//2} jpeg {len(jb)} B, deflated {len(z)} B ({100*(1-len(z)/len(jb)):.1f}% smaller); "
          f"resized-image std={r.astype(float).std():.1f}")
    # natural-ish texture: blurred random noise (higher entropy than gradient)
    rng = np.random.default_rng(1); n = rng.integers(0,255,(h//2,w//2,3),dtype=np.uint8); n = cv2.GaussianBlur(n,(5,5),0)
    ok, j2 = cv2.imencode(".jpg", n, [int(cv2.IMWRITE_JPEG_QUALITY), 60]); jb2=j2.tobytes()
    enc = zlib.compressobj(wbits=-15); z2 = enc.compress(jb2) + enc.flush(zlib.Z_SYNC_FLUSH)
    print(f"   blurred-noise image: jpeg {len(jb2)} B, deflated {len(z2)} B ({100*(1-len(z2)/len(jb2)):.1f}% smaller)")
