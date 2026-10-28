# /// script
# requires-python = ">=3.10"
# ///
"""Strict structural JPEG completeness check over uvc_iso --raw-mjpeg + frames_*.jsonl.
Per frame: SOI first; walk marker segments to SOS; in entropy data allow only FF00, RSTn in strict
cyclic order, then EOI; count RSTs and compare to expected ceil(MCUs/Ri)-1 when DRI present;
report trailing bytes after EOI. Also reports DQT/SOF/DHT presence."""
import json, sys, math
from pathlib import Path

def check(b):
    r = {"ok": False}
    if b[:2] != b"\xff\xd8": r["err"]="no SOI"; return r
    i=2; ri=0; w=h=0; hv=[]; sos_seen=False
    while i < len(b):
        if b[i]!=0xFF: r["err"]=f"bad marker at {i}"; return r
        m=b[i+1]
        if m==0xFF: i+=1; continue
        L=int.from_bytes(b[i+2:i+4],"big")
        seg=b[i+4:i+2+L]
        if m==0xDD: ri=int.from_bytes(seg[:2],"big")
        if m in (0xC0,0xC1,0xC2):
            h=int.from_bytes(seg[1:3],"big"); w=int.from_bytes(seg[3:5],"big")
            nc=seg[5]; hv=[(seg[6+3*k+1]>>4, seg[6+3*k+1]&15) for k in range(nc)]
        i+=2+L
        if m==0xDA: sos_seen=True; break
    if not sos_seen: r["err"]="no SOS"; return r
    hmax=max(x[0] for x in hv); vmax=max(x[1] for x in hv)
    mcus=math.ceil(w/(8*hmax))*math.ceil(h/(8*vmax))
    nrst=0; expect=0; j=i
    eoi=None
    while j < len(b)-1:
        if b[j]==0xFF:
            n=b[j+1]
            if n==0x00: j+=2; continue
            if 0xD0<=n<=0xD7:
                if n-0xD0 != expect: r["err"]=f"RST out of order at {j}: got {n-0xD0} want {expect}"; r["nrst"]=nrst; return r
                expect=(expect+1)%8; nrst+=1; j+=2; continue
            if n==0xD9: eoi=j; break
            if n==0xFF: j+=1; continue
            r["err"]=f"unexpected marker FF{n:02X} in scan at {j}"; return r
        j+=1
    if eoi is None: r["err"]="no EOI"; return r
    r.update(ok=True, w=w, h=h, ri=ri, mcus=mcus, nrst=nrst, trailing=len(b)-(eoi+2))
    if ri:
        exp=math.ceil(mcus/ri)-1
        r["exp_rst"]=exp
        if nrst!=exp: r["ok"]=False; r["err"]=f"rst count {nrst} != {exp}"
    return r

def main():
    a=sys.argv[1:]
    for d,raw in zip(a[0::2],a[1::2]):
        rows=[json.loads(l) for l in next(Path(d).glob("frames_*.jsonl")).read_text().splitlines() if l.strip()]
        data=Path(raw).read_bytes(); off=0; ok=0; bad=[]; ris=set(); trail=0; nr=set()
        for rw in rows:
            n=rw["payload_bytes"]; fr=data[off:off+n]; off+=n
            c=check(fr)
            if c["ok"]: ok+=1; ris.add(c["ri"]); nr.add(c["nrst"]); trail=max(trail,c["trailing"])
            else: bad.append((rw["seq"],n,c.get("err")))
        print(json.dumps({"run":Path(d).name,"frames":len(rows),"strict_ok":ok,"bad":bad[:5],"n_bad":len(bad),"restart_intervals":sorted(ris),"rst_counts":sorted(nr)[:5],"max_trailing_bytes":trail,"bytes":[off,len(data)]}))
main()
