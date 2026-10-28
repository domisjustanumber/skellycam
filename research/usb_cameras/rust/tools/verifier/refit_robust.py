"""Refit the 60 s runs' clock rates with the stale startup frame(s) excluded (|resid|>5 ms / 5 frames,
iterated) to measure the OLS bias in scr_sof_qpc_map.py / uvc_iso device_clock_fit."""
import json, sys
from pathlib import Path
def linfit(xs, ys):
    n=len(xs); mx=sum(xs)/n; my=sum(ys)/n
    sxx=sum((x-mx)**2 for x in xs); b=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/sxx
    return my-b*mx,b
def robust(xs,ys,thr):
    keep=list(range(len(xs)))
    for _ in range(5):
        a,b=linfit([xs[i] for i in keep],[ys[i] for i in keep])
        nk=[i for i in range(len(xs)) if abs(ys[i]-(a+b*xs[i]))<thr]
        if nk==keep: break
        keep=nk
    res=[ys[i]-(a+b*xs[i]) for i in keep]
    return a,b,len(xs)-len(keep),min(res),max(res)
for run in sys.argv[1:]:
    run=Path(run); s=json.loads((run/"summary.json").read_text()); cb=s["sof_calibration_before"]
    qf=cb["qpc_frequency"]; f0,q0=cb["first"]["frame"],cb["first"]["qpc"]
    rows=[json.loads(l) for l in next(run.glob("frames_*.jsonl")).read_text().splitlines() if l.strip()]
    rows=[r for r in rows if r.get("uvc_scr_sof") is not None]
    # packet-arrival STC fit
    base=0; last=None; xs=[]; ys=[]; ts=[]; fs=[]
    for r in rows:
        stc=r["uvc_scr_stc"]
        if last is not None and stc<last and last-stc>1<<31: base+=1<<32
        last=stc; xs.append(base+stc); ys.append(r["first_packet_est_host_ns"])
        t=r["first_packet_est_host_ns"]; fp=f0+cb["fit_intercept_frames"]+(t*qf/1e9-q0)/qf*1000.0
        ts.append((t*qf/1e9-q0)/qf); sof=r["uvc_scr_sof"]; fs.append(sof+2048*round((fp-sof)/2048))
    _,b_all=linfit(xs,ys); _,b_r,nx,rmin,rmax=robust(xs,ys,5e6)
    _,ib_all=linfit(ts,fs); _,ib_r,nx2,_,_=robust(ts,fs,5.0)
    hz=30e6
    print(json.dumps({"run":run.name,
      "stc_pkt_fit_ppm_OLS_all":round((1e9/b_all/hz-1)*1e6,2),"stc_pkt_fit_ppm_robust":round((1e9/b_r/hz-1)*1e6,2),"excluded":nx,"robust_resid_ms":[round(rmin/1e6,3),round(rmax/1e6,3)],
      "usbframe_instream_ppm_OLS_all":round((ib_all/1000-1)*1e6,2),"usbframe_instream_ppm_robust":round((ib_r/1000-1)*1e6,2),"excluded2":nx2}))
