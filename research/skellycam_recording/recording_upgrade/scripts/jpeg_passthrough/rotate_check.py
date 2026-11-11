# /// script
# requires-python = "==3.12.*"
# dependencies = ["jpeglib==1.0.2", "numpy==2.2.6", "PyTurboJPEG==2.6.1"]
# ///
"""(f) Lossless JPEG rotation in Python, as skellycam-rust jpeg_transform.rs does it (tjTransform, options=0).

Rotates real camera JPEGs with libjpeg-turbo's tj3Transform via ctypes (same call the Rust code makes) and with
jpegtran.exe, then proves losslessness three ways:
  1. DCT domain: dequantized coefficients of the rotated file == the exact block/coefficient permutation (+ sign flips)
     of the original's (read with jpeglib 1.0.2). This is the real losslessness criterion.
  2. Native-resolution planes: decode both to YUV planes (PyTurboJPEG decode_to_yuv_planes), compare rotated planes.
  3. RGB pixels: np.rot90(decode(original)) vs decode(rotated) (chroma upsampling direction differs, so small diffs allowed).
Also checks TJXOPT_PERFECT (fails if any partial iMCU edge would be dropped/left untransformed).

Run (repo root; uv builds an isolated env, nothing is installed into .venv):
  uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/rotate_check.py ^
     --lib <scratchpad>/jpeg_passthrough/ljt321/bin/turbojpeg.dll --jpegtran <scratchpad>/jpeg_passthrough/ljt321/bin/jpegtran.exe
libjpeg-turbo 3.2.1 Windows build: https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/3.2.1/libjpeg-turbo-3.2.1-vc-x64.exe
(sha256 1f05bc3ed1585e6b12a8b0c24c8c5f07b1f6d90d01b4b709b331bedc9d6e5838), extracted with 7-Zip.
"""
from __future__ import annotations

import argparse
import ctypes as ct
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import jpeglib
import numpy as np
from turbojpeg import TurboJPEG, TJPF_RGB

CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")
RESULTS = Path(__file__).resolve().parents[2] / "results/jpeg_passthrough"
SETS = ["c930e_720p_flash", "c922_720p_flash", "c922_1080p", "c930e_1080p", "c922_1600x896", "c922_720p60", "generic_1080p"]

TJINIT_TRANSFORM = 2
TJXOP = {"rot90": 5, "rot180": 6, "rot270": 7}  # turbojpeg.h TJXOP_ROT90/180/270 (same values as jpeg_transform.rs)
TJXOPT_PERFECT = 1
TJERR_WARNING = 0  # turbojpeg.h enum TJERR { TJERR_WARNING = 0, TJERR_FATAL }
JPEGTRAN_ARG = {"rot90": "90", "rot180": "180", "rot270": "270"}


class TJRegion(ct.Structure):
    _fields_ = [("x", ct.c_int), ("y", ct.c_int), ("w", ct.c_int), ("h", ct.c_int)]


class TJTransform(ct.Structure):
    _fields_ = [("r", TJRegion), ("op", ct.c_int), ("options", ct.c_int), ("data", ct.c_void_p), ("customFilter", ct.c_void_p)]


class TJ:
    def __init__(self, lib: str):
        self.l = ct.CDLL(lib)
        self.l.tj3Init.restype = ct.c_void_p
        self.l.tj3Init.argtypes = [ct.c_int]
        self.l.tj3Transform.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_int, ct.POINTER(ct.c_void_p),
                                        ct.POINTER(ct.c_size_t), ct.POINTER(TJTransform)]
        self.l.tj3Free.argtypes = [ct.c_void_p]
        self.l.tj3Destroy.argtypes = [ct.c_void_p]
        self.l.tj3GetErrorStr.restype = ct.c_char_p
        self.l.tj3GetErrorStr.argtypes = [ct.c_void_p]
        self.l.tj3GetErrorCode.argtypes = [ct.c_void_p]
        self.l.tjInitTransform.restype = ct.c_void_p
        self.l.tjTransform.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_ulong, ct.c_int, ct.POINTER(ct.c_void_p),
                                       ct.POINTER(ct.c_ulong), ct.POINTER(TJTransform), ct.c_int]
        self.l.tjFree.argtypes = [ct.c_void_p]
        self.l.tjDestroy.argtypes = [ct.c_void_p]
        self.h = self.l.tj3Init(TJINIT_TRANSFORM)

    def transform(self, jpeg: bytes, op: int, options: int = 0) -> tuple[bytes | None, str | None]:
        """tj3Transform. rc != 0 with error code TJERR_WARNING (0) still yields a complete output: keep it, report the warning."""
        src = ct.create_string_buffer(jpeg, len(jpeg))
        dst = ct.c_void_p()
        dsz = ct.c_size_t()
        x = TJTransform(TJRegion(0, 0, 0, 0), op, options, None, None)
        rc = self.l.tj3Transform(self.h, src, len(jpeg), 1, ct.byref(dst), ct.byref(dsz), ct.byref(x))
        msg = None
        if rc != 0:
            msg = self.l.tj3GetErrorStr(self.h).decode()
            code = self.l.tj3GetErrorCode(self.h)
            if code != TJERR_WARNING or not dst or dsz.value == 0:
                if dst:
                    self.l.tj3Free(dst)
                return None, f"error(code {code}): {msg}"
            msg = f"warning(code {code}): {msg}"
        out = ct.string_at(dst, dsz.value)
        self.l.tj3Free(dst)
        return out, msg

    def legacy_transform_like_rust(self, jpeg: bytes, op: int) -> tuple[int, int]:
        """Exactly the call in skellycam-rust jpeg_transform.rs: tjInitTransform + tjTransform(..., options 0, flags 0);
        Windows unsigned long = 32 bit. Returns (return code, output size). Rust keeps the output only when rc == 0."""
        h = self.l.tjInitTransform()
        dst = ct.c_void_p()
        dsz = ct.c_ulong()
        x = TJTransform(TJRegion(0, 0, 0, 0), op, 0, None, None)
        src = ct.create_string_buffer(jpeg, len(jpeg))
        rc = self.l.tjTransform(h, src, ct.c_ulong(len(jpeg)), 1, ct.byref(dst), ct.byref(dsz), ct.byref(x), 0)
        n = dsz.value
        if dst:
            self.l.tjFree(dst)
        self.l.tjDestroy(h)
        return rc, n


def dct_transform(B: np.ndarray, op: str) -> np.ndarray:
    """B[block_row, block_col, u(vertical freq), v(horizontal freq)] -> coefficients of the rotated image."""
    u = (-1) ** np.arange(8)
    if op == "rot90":  # transpose then horizontal flip  (np.rot90(img, -1) == fliplr(img.T))
        T = B.transpose(1, 0, 3, 2)
        return T[:, ::-1, :, :] * u[None, None, None, :]
    if op == "rot270":  # transpose then vertical flip   (np.rot90(img, 1) == flipud(img.T))
        T = B.transpose(1, 0, 3, 2)
        return T[::-1, :, :, :] * u[None, None, :, None]
    if op == "rot180":
        return B[::-1, ::-1, :, :] * u[None, None, :, None] * u[None, None, None, :]
    raise ValueError(op)


def dequant(d) -> list[np.ndarray]:
    comps = [d.Y, d.Cb, d.Cr]
    return [c.astype(np.int32) * d.qt[d.quant_tbl_no[i]].astype(np.int32)[None, None] for i, c in enumerate(comps)]


def read_dct_bytes(b: bytes, tmpdir: Path, name: str):
    p = tmpdir / name
    p.write_bytes(b)
    return jpeglib.read_dct(str(p))


def np_rot(a: np.ndarray, op: str) -> np.ndarray:
    return {"rot90": np.rot90(a, -1), "rot180": np.rot90(a, 2), "rot270": np.rot90(a, 1)}[op]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", required=True)
    ap.add_argument("--jpegtran", required=True)
    ap.add_argument("--n", type=int, default=5, help="frames per set")
    ap.add_argument("--out", default=str(RESULTS / "rotation.json"))
    a = ap.parse_args()
    tj = TJ(a.lib)
    ptj = TurboJPEG(lib_path=a.lib)
    tmp = Path(tempfile.mkdtemp())
    rows = []
    for s in SETS:
        files = sorted((CORPUS / s).glob("frame_*.jpg"))[: a.n]
        for f in files:
            src = f.read_bytes()
            d0 = read_dct_bytes(src, tmp, "src.jpg")
            deq0 = dequant(d0)
            rgb0 = ptj.decode(src, pixel_format=TJPF_RGB)
            yuv0 = ptj.decode_to_yuv_planes(src)
            for op in TJXOP:
                row = {"set": s, "frame": f.name, "op": op, "src_bytes": len(src)}
                out, err = tj.transform(src, TJXOP[op], 0)  # options 0, as jpeg_transform.rs
                outp, errp = tj.transform(src, TJXOP[op], TJXOPT_PERFECT)
                rc_legacy, n_legacy = tj.legacy_transform_like_rust(src, TJXOP[op])
                row["rust_equivalent_legacy_rc"] = rc_legacy
                row["rust_equivalent_keeps_rotation"] = rc_legacy == 0
                row["tj3_message"] = err
                row["tj_options0_ok"] = out is not None
                row["tj_perfect_ok"] = outp is not None
                row["tj_perfect_error"] = errp
                if out is None:
                    row["error"] = err
                    rows.append(row)
                    continue
                row["out_bytes"] = len(out)
                row["perfect_equals_options0"] = outp == out
                jt = subprocess.run([a.jpegtran, "-rotate", JPEGTRAN_ARG[op], "-perfect", "-copy", "all"], input=src, capture_output=True)
                row["jpegtran_rc"] = jt.returncode
                row["jpegtran_bytes_equal_tj"] = jt.stdout == out
                w, h, sub, cs = ptj.decode_header(out)
                row["out_w_h_subsamp"] = [w, h, int(sub)]
                # 1. DCT domain
                d1 = read_dct_bytes(out, tmp, "rot.jpg")
                deq1 = dequant(d1)
                comp_ok, comp_maxdiff = [], []
                for c0, c1 in zip(deq0, deq1):
                    exp = dct_transform(c0, op)
                    if exp.shape != c1.shape:
                        comp_ok.append(False)
                        comp_maxdiff.append(f"shape {exp.shape} vs {c1.shape}")
                        continue
                    comp_ok.append(bool(np.array_equal(exp, c1)))
                    comp_maxdiff.append(int(np.abs(exp - c1).max()))
                row["dct_dequant_equal_per_component"] = comp_ok
                row["dct_max_abs_diff"] = comp_maxdiff
                # wrong-mapping control: plain np.rot90 of block grid without coefficient permutation must NOT match
                ctrl = np_rot(deq0[0], op)
                row["control_blockgrid_only_matches"] = bool(ctrl.shape == deq1[0].shape and np.array_equal(ctrl, deq1[0]))
                # 2. native-resolution planes
                yuv1 = ptj.decode_to_yuv_planes(out)
                pl = []
                for p0, p1 in zip(yuv0, yuv1):
                    r0 = np_rot(p0, op)
                    pl.append(int(np.abs(r0.astype(np.int16) - p1.astype(np.int16)).max()) if r0.shape == p1.shape else f"shape {r0.shape} vs {p1.shape}")
                row["yuv_plane_max_abs_diff"] = pl
                # 3. RGB pixels
                rgb1 = ptj.decode(out, pixel_format=TJPF_RGB)
                r0 = np_rot(rgb0, op)
                if r0.shape == rgb1.shape:
                    dif = np.abs(r0.astype(np.int16) - rgb1.astype(np.int16))
                    row["rgb_max_abs_diff"] = int(dif.max())
                    row["rgb_frac_pixels_differing"] = round(float((dif.max(axis=2) > 0).mean()), 6)
                else:
                    row["rgb_shape_mismatch"] = [list(r0.shape), list(rgb1.shape)]
                rows.append(row)
        print(s, "done", flush=True)
    summary = {}
    for r in rows:
        k = (r["set"], r["op"])
        sm = summary.setdefault(f"{k[0]}|{k[1]}", {"n": 0, "tj_ok": 0, "perfect_ok": 0, "dct_equal_all_components": 0, "yuv_planes_exact": 0,
                                                   "rgb_max_abs_diff_max": 0, "jpegtran_equal": 0, "control_matches": 0, "out_w_h_subsamp": None})
        sm["n"] += 1
        sm["tj_ok"] += r.get("tj_options0_ok", False)
        sm["rust_equiv_rotated"] = sm.get("rust_equiv_rotated", 0) + r.get("rust_equivalent_keeps_rotation", False)
        sm["tj3_warnings"] = sm.get("tj3_warnings", 0) + bool(r.get("tj3_message"))
        sm["perfect_ok"] += r.get("tj_perfect_ok", False)
        sm["dct_equal_all_components"] += all(r.get("dct_dequant_equal_per_component", [False]))
        sm["yuv_planes_exact"] += all(x == 0 for x in r.get("yuv_plane_max_abs_diff", [1]))
        sm["rgb_max_abs_diff_max"] = max(sm["rgb_max_abs_diff_max"], r.get("rgb_max_abs_diff", 0))
        sm["jpegtran_equal"] += r.get("jpegtran_bytes_equal_tj", False)
        sm["control_matches"] += r.get("control_blockgrid_only_matches", False)
        sm["out_w_h_subsamp"] = r.get("out_w_h_subsamp")
    res = {"meta": {"date": time.strftime("%Y-%m-%dT%H:%M:%S"), "python": sys.version, "jpeglib": "1.0.2", "PyTurboJPEG": "2.6.1",
                    "libjpeg_turbo": a.lib, "jpegtran": a.jpegtran, "numpy": np.__version__,
                    "tjsamp_note": "TJSAMP: 0=444 1=422 2=420 3=gray 4=440 5=411 6=441"},
           "summary": summary, "rows": rows}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=1))
    for k, v in summary.items():
        print(k, v)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
