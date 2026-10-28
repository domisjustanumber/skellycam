# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python-headless==4.10.0.84", "numpy<2.3", "pillow==11.3.0"]
# ///
"""Count libjpeg 'Corrupt JPEG data' warnings per frame (OpenCV imdecode prints them to fd 2).
Mode 'control': take frame 100 of the given run, cut 3072 bytes from its middle (= one lost
alt-11 microframe), and check whether Pillow accepts it and whether libjpeg warns.
Usage: libjpeg_warn.py run <run_dir> <raw> | control <run_dir> <raw>"""
import io, json, os, sys, tempfile
from pathlib import Path
import cv2, numpy as np
from PIL import Image

def frames(d, raw):
    rows=[json.loads(l) for l in next(Path(d).glob("frames_*.jsonl")).read_text().splitlines() if l.strip()]
    data=Path(raw).read_bytes(); off=0
    for r in rows:
        n=r["payload_bytes"]; yield r["seq"], data[off:off+n]; off+=n

def decode_capture(b):
    # redirect fd 2 to a temp file around imdecode
    tf=tempfile.TemporaryFile(); old=os.dup(2); os.dup2(tf.fileno(),2)
    try: im=cv2.imdecode(np.frombuffer(b,np.uint8), cv2.IMREAD_COLOR)
    finally:
        os.dup2(old,2); os.close(old)
    tf.seek(0); msg=tf.read().decode(errors="replace"); tf.close()
    return im, msg

mode, d, raw = sys.argv[1:4]
if mode=="run":
    n=warn=fail=0; ex=[]
    for seq,b in frames(d,raw):
        im,msg=decode_capture(b); n+=1
        if im is None: fail+=1
        if "Corrupt" in msg or "Premature" in msg or "premature" in msg:
            warn+=1
            if len(ex)<3: ex.append((seq,msg.strip()[:120]))
    print(json.dumps({"run":Path(d).name,"frames":n,"cv2_fail":fail,"libjpeg_warn_frames":warn,"examples":ex}))
else:
    fr=list(frames(d,raw)); seq,b=fr[min(100,len(fr)-1)]
    mid=len(b)//2; cut=b[:mid]+b[mid+3072:]
    try:
        im=Image.open(io.BytesIO(cut)); im.load(); pil="decoded_ok"
    except Exception as e: pil="error "+repr(e)[:100]
    im2,msg=decode_capture(cut)
    _,msg0=decode_capture(b)
    print(json.dumps({"control_frame_seq":seq,"orig_bytes":len(b),"cut_bytes":len(cut),"pillow_on_cut":pil,"cv2_on_cut_ok":im2 is not None,"libjpeg_msg_on_cut":msg.strip()[:200],"libjpeg_msg_on_original":msg0.strip()[:200]}))
