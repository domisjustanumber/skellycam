# Tabulate flash_analyze.py results (vs_ground_truth offset/std per source, per camera, per run) + cross-camera diffs.
import json,sys
from pathlib import Path
T=Path(sys.argv[1]); runs=sys.argv[2:]
srcs=['host_arrival','os_timestamp','uvc_pts_mapped_direct','uvc_pts_via_scr_envelope','uvc_pts_via_scr_lsq_envelope']
for cam in ('pid_085c','pid_0843'):
    print('=== camera',cam,'  columns: run | E_ms | ref | per source: GT offset ms / GT std us (fit corr)')
    for r in runs:
        f=T/r; d=json.load(open(f))
        for c in d['cameras']:
            if cam not in c['camera_key'] or 'sources' not in c: continue
            row=[f"{r.split('/')[-2]+'/'+Path(r).name:58s}",f"E={c['E_ms_used']:.2f}",f"ref={c['ground_truth_reference_source'][4:20]}"]
            for s in srcs:
                g=c['sources'][s]['vs_ground_truth']; row.append(f"{s[:14]}:{g['offset_ms']:7.2f}/{g['err_std_us']:6.0f}({c['sources'][s]['corr']:.3f})")
            print('  '.join(row))
print('=== cross-camera offset diff (C930e - C922) per source, ms')
for r in runs:
    d=json.load(open(T/r)); cc=d.get('cross_camera',{})
    if cc: print(f"{r.split('/')[-2]:28s}", '  '.join(f"{k.split('|')[2][:20]}={v['offset_diff_ms']:+.3f}" for k,v in sorted(cc.items())))
