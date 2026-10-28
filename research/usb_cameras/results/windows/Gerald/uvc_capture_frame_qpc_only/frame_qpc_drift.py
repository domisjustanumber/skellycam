# verifier helper: per host controller, residual of frame_qpc_ns vs a pure (usb_frame*8+uframe)*125 us model
# anchored at the first sample; prints segments where the residual changes (re-anchoring) and causality violations.
import json,sys
rows=[json.loads(l) for l in open(sys.argv[1]) if l.strip()]
for hc in sorted({x['hc'] for x in rows}):
    r=[x for x in rows if x.get('hc')==hc and 'usb_frame' in x]
    if not r: continue
    u=lambda x:x['usb_frame']*8+x['uframe']
    res=[(x['frame_qpc_ns']-r[0]['frame_qpc_ns'])-(u(x)-u(r[0]))*125000 for x in r]
    span=(r[-1]['call_before_ns']-r[0]['call_before_ns'])/1e9
    first_nz=next((i for i,v in enumerate(res) if v),None)
    print(f"hc{hc} n={len(r)} span_s={span:.1f} first_nonzero_idx={first_nz} t_first_nonzero_s={(r[first_nz]['call_before_ns']-r[0]['call_before_ns'])/1e9 if first_nz is not None else None} residual_us min={min(res)/1e3:.1f} max={max(res)/1e3:.1f} last={res[-1]/1e3:.1f} frame_qpc_after_call_after={sum(x['frame_qpc_ns']>x['call_after_ns'] for x in r)} acc={sorted({x['accuracy_us'] for x in r})} gen={sorted({x['generation'] for x in r})}")
