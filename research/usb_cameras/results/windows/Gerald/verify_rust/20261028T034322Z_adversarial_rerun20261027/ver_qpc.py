import json,sys,statistics as st
d=json.load(open(sys.argv[1],encoding='utf-8'))
for it in d['interfaces']:
    s=it.get('samples') or []
    if not s:
        print(it['kind'], it.get('start_tracking_error'), {k:v for k,v in it.items() if k not in('samples','path')}.__repr__()[:200]); continue
    f0=s[0]['CurrentUSBFrameNumber']; q0=s[0]['CurrentQueryPerformanceCounter']
    res=[(x['CurrentQueryPerformanceCounter']-q0)-(x['CurrentUSBFrameNumber']-f0)*1250 for x in s]
    mod=all(x['CurrentUSBFrameNumber']%2048==x['CurrentHardwareFrameNumber'] for x in s)
    lat=[(x['qpc_after']-x['qpc_before'])/10 for x in s]
    anom=sum(1 for x in s if x['CurrentQueryPerformanceCounter']>x['qpc_after'])
    print(it['kind'],len(s),'res',set(res),'mod2048',mod,'acc',{x['PredictedAccuracyInMicroSeconds'] for x in s},'lat_med_us %.1f'%st.median(lat),'qpc>after',anom, {k:v for k,v in it.items() if k.startswith('input') or k.startswith('query')}.__repr__()[:400])
