"""Encoder simulation with each camera's own quantization tables and chroma subsampling (baseline, standard Huffman
tables, no restart markers), on a ladder of content from benign to adversarial. Prints bytes per pixel."""
import io, json, os, sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jpeg_inspect import inspect

HERE = os.path.dirname(os.path.abspath(__file__))
H = json.load(open(os.path.join(HERE, 'headers.json')))
rng = np.random.default_rng(12345)

# camera encoder profiles: tables from the camera's own largest frame; subsampling from its SOF0
CAMS = {}
for cam, key in (('C922', 'C922 1280x720'), ('C930e', 'C930e 1280x720'), ('Kiyo Pro', 'Kiyo Pro 1280x720'), ('generic', 'generic 1280x720')):
    x = H[key]['max']
    tabs = [x['dqt'][k] for k in sorted(x['dqt'], key=int)]
    hs, vs = x['sof']['comps'][0][1], x['sof']['comps'][0][2]
    CAMS[cam] = dict(qtables=tabs, subsampling={(1, 1): 0, (2, 1): 1, (2, 2): 2}[(hs, vs)], dri=x['dri'],
                     label=f"q~{x['ijg_q']['0'][0]} {'4:2:2' if (hs, vs) == (2, 1) else '4:2:0'}")


def encode(img, cam, verify=False):
    p = CAMS[cam]
    buf = io.BytesIO()
    img.save(buf, 'JPEG', qtables=p['qtables'], subsampling=p['subsampling'], optimize=False)
    b = buf.getvalue()
    if verify:
        h = inspect(b)
        got = [h['dqt'][k] for k in sorted(h['dqt'])]
        assert got == p['qtables'], (cam, 'DQT not reproduced')
        samp = (h['sof']['comps'][0][1], h['sof']['comps'][0][2])
        assert {(1, 1): 0, (2, 1): 1, (2, 2): 2}[samp] == p['subsampling']
    n = len(b)
    if p['dri']:  # camera adds RSTn every dri MCUs: 2 bytes + avg 0.5 byte bit padding each
        mw, mh = {0: (8, 8), 1: (16, 8), 2: (16, 16)}[p['subsampling']]
        mcus = -(-img.width // mw) * -(-img.height // mh)
        n += int(2.5 * (mcus // p['dri']))
    return n


def blur(a, s):
    """separable Gaussian blur (float HxWxC), reflect edges."""
    if s <= 0:
        return a
    r = int(np.ceil(3 * s))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / s) ** 2)
    k /= k.sum()
    for ax in (0, 1):
        pad = [(0, 0)] * a.ndim
        pad[ax] = (r, r)
        ap = np.pad(a, pad, mode='reflect')
        out = np.zeros_like(a)
        for i, kv in enumerate(k):
            sl = [slice(None)] * a.ndim
            sl[ax] = slice(i, i + a.shape[ax])
            out += kv * ap[tuple(sl)]
        a = out
    return a


def to_img(a):
    return Image.fromarray(np.clip(np.rint(a), 0, 255).astype(np.uint8), 'RGB')


def bayer_demosaic(rgb):
    """RGGB mosaic of a full-res RGB scene then bilinear demosaic (what a cheap ISP does)."""
    h, w, _ = rgb.shape
    m = np.zeros((h, w))
    m[0::2, 0::2] = rgb[0::2, 0::2, 0]
    m[0::2, 1::2] = rgb[0::2, 1::2, 1]
    m[1::2, 0::2] = rgb[1::2, 0::2, 1]
    m[1::2, 1::2] = rgb[1::2, 1::2, 2]
    return demosaic(m)


def demosaic(m):
    h, w = m.shape
    masks = np.zeros((h, w, 3))
    masks[0::2, 0::2, 0] = 1
    masks[0::2, 1::2, 1] = 1
    masks[1::2, 0::2, 1] = 1
    masks[1::2, 1::2, 2] = 1
    kern = {0: np.array([[.25, .5, .25], [.5, 1, .5], [.25, .5, .25]]), 2: np.array([[.25, .5, .25], [.5, 1, .5], [.25, .5, .25]]),
            1: np.array([[0, .25, 0], [.25, 1, .25], [0, .25, 0]])}
    out = np.zeros((h, w, 3))
    for c in range(3):
        src = np.pad(m * masks[..., c], 1, mode='reflect')
        acc = np.zeros((h, w))
        for dy in range(3):
            for dx in range(3):
                acc += kern[c][dy, dx] * src[dy:dy + h, dx:dx + w]
        out[..., c] = acc
    return out


def pink(h, w, alpha):
    """isotropic 1/f^alpha amplitude-spectrum colour noise scaled to 0..255 (natural images: alpha ~ 1)."""
    out = np.zeros((h, w, 3))
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.rfftfreq(w)[None, :]
    f = np.sqrt(fx ** 2 + fy ** 2)
    f[0, 0] = 1
    lum = None
    for c in range(3):
        spec = (rng.normal(size=f.shape) + 1j * rng.normal(size=f.shape)) / f ** alpha
        spec[0, 0] = 0
        x = np.fft.irfft2(spec, s=(h, w))
        x = (x - x.mean()) / x.std()
        lum = x if lum is None else lum
        out[..., c] = 0.8 * lum + 0.2 * x  # mostly-correlated channels, like real scenes
    out = (out - out.mean()) / out.std()
    return 128 + 50 * out


def unsharp(a, s=1.0, amount=1.0):
    return a + amount * (a - blur(a, s))


def ladder(h, w):
    L = []
    binary = rng.integers(0, 2, size=(h, w, 1)) * 255.0 * np.ones((1, 1, 3))      # B/W printed noise, 1 px cells
    binary_c = rng.integers(0, 2, size=(h, w, 3)) * 255.0                         # colour printed noise
    uni = rng.uniform(0, 255, size=(h, w, 3))
    b2 = np.kron(rng.integers(0, 2, size=(h // 2 + 1, w // 2 + 1, 1)), np.ones((2, 2, 1)))[:h, :w] * 255.0 * np.ones((1, 1, 3))
    nat = pink(h, w, 1.0)
    L.append(('natural-like 1/f (alpha=1.0)', nat))
    L.append(('detailed 1/f (alpha=0.7)', pink(h, w, 0.7)))
    L.append(('natural 1/f + sensor noise sd 2', nat + rng.normal(0, 2, nat.shape)))
    L.append(('natural 1/f + sensor noise sd 4', nat + rng.normal(0, 4, nat.shape)))
    L.append(('natural 1/f + sensor noise sd 8', nat + rng.normal(0, 8, nat.shape)))
    L.append(('natural 1/f + Bayer sensor noise sd 8 (demosaiced)', demosaic(bayer_mosaic(nat) + rng.normal(0, 8, (h, w)))))
    for s in (2.0, 1.5, 1.0, 0.7, 0.5):
        L.append((f'B/W 1px noise target, lens blur sd {s}', blur(binary, s)))
    L.append(('B/W 2px noise target (monitor test), blur sd 1.0', blur(b2, 1.0)))
    L.append(('B/W 1px noise, blur 1.0, then ISP unsharp (1.0 px, x1)', unsharp(blur(binary, 1.0))))
    L.append(('colour 1px noise target, blur sd 0.7', blur(binary_c, 0.7)))
    L.append(('colour 1px noise, blur 0.7, Bayer+demosaic', bayer_demosaic(blur(binary_c, 0.7))))
    for sd in (2, 4, 8, 16):
        L.append((f'B/W noise blur 1.0 + sensor noise sd {sd}', blur(binary, 1.0) + rng.normal(0, sd, binary.shape)))
    L.append(('B/W noise blur 1.0 + Bayer sensor noise sd 8 (demosaiced)', demosaic(bayer_mosaic(blur(binary, 1.0)) + rng.normal(0, 8, (h, w)))))
    L.append(('B/W noise blur 1.0 + Bayer sensor noise sd 16 (demosaiced)', demosaic(bayer_mosaic(blur(binary, 1.0)) + rng.normal(0, 16, (h, w)))))
    L.append(('mid-grey + sensor noise sd 16 (dark scene, max gain)', 128 + rng.normal(0, 16, uni.shape)))
    L.append(('mid-grey + sensor noise sd 32', 128 + rng.normal(0, 32, uni.shape)))
    L.append(('B/W 1px noise, no blur (ceiling: luma only)', binary))
    L.append(('uniform RGB per-pixel noise (ceiling)', uni))
    return L


def bayer_mosaic(rgb):
    h, w, _ = rgb.shape
    m = np.zeros((h, w))
    m[0::2, 0::2] = rgb[0::2, 0::2, 0]
    m[0::2, 1::2] = rgb[0::2, 1::2, 1]
    m[1::2, 0::2] = rgb[1::2, 0::2, 1]
    m[1::2, 1::2] = rgb[1::2, 1::2, 2]
    return m


def calibrate():
    """re-encode each camera's own frames (decoded straight to YCbCr) with its tables: how close is the simulator?"""
    print('\n# calibration: camera frame -> decode to YCbCr -> re-encode with the camera tables')
    for key, rec in H.items():
        cam = key.split(' 1')[0].split(' 3')[0].split(' 6')[0].split(' 9')[0]
        cam = 'Kiyo Pro' if key.startswith('Kiyo Pro') else key.split()[0]
        if cam not in CAMS:
            continue
        for tag in ('max', 'median'):
            x = rec.get(tag) or {}
            if 'file' not in x:
                continue
            im = Image.open(x['file'])
            im.draft('YCbCr', im.size)
            im = im.convert('YCbCr') if im.mode != 'YCbCr' else im
            im.load()
            n = encode(im, cam)
            print(f'{key:22s} {tag:6s} camera={x["size"]:7d}  re-encoded={n:7d}  ratio={n / x["size"]:.3f}')


def main():
    for cam in CAMS:
        print(cam, CAMS[cam]['label'], 'dri', CAMS[cam]['dri'])
    calibrate()
    res = {}
    for (w, h) in ((1280, 720), (1920, 1080)):
        print(f'\n# {w}x{h}: bytes per pixel by content (columns: camera tables)')
        print(f"{'content':58s}" + ''.join(f'{c:>10s}' for c in CAMS))
        for name, arr in ladder(h, w):
            img = to_img(arr)
            row = {c: encode(img, c, verify=(name.startswith('natural-like'))) for c in CAMS}
            res[f'{w}x{h} {name}'] = row
            print(f'{name:58s}' + ''.join(f'{row[c] / (w * h):10.3f}' for c in CAMS))
    json.dump(res, open(os.path.join(HERE, 'sim.json'), 'w'), indent=1)
    # resolution dependence of the per-pixel ceiling-type content
    print('\n# resolution dependence (C922 tables): bytes and bytes/pixel')
    for (w, h) in ((160, 90), (320, 240), (640, 480), (1280, 720), (1920, 1080), (3840, 2160)):
        b = blur(rng.integers(0, 2, size=(h, w, 1)) * 255.0 * np.ones((1, 1, 3)), 1.0)
        nb = encode(to_img(b + rng.normal(0, 8, b.shape)), 'C922')
        nu = encode(to_img(rng.uniform(0, 255, size=(h, w, 3))), 'C922')
        flat = encode(to_img(np.full((h, w, 3), 128.0)), 'C922')
        print(f'{w}x{h}: flat grey {flat} B; noise blur1+sd8 {nb} B ({nb / (w * h):.3f}/px); uniform noise {nu} B ({nu / (w * h):.3f}/px)')


if __name__ == '__main__':
    main()
