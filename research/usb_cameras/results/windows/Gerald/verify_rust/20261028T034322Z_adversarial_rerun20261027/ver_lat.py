import json,sys,statistics as st
from collections import Counter
for f in sys.argv[1:]:
    rows=[json.loads(l) for l in open(f,encoding='utf-8') if l.strip()]
    r=rows[30:]
    if not r: print(f, "no frames"); continue
    lat=[(x['host_arrival_ns']-x['implied_sample_time_ns'])/1e6 for x in r]
    seq=[(round(l/16))%9 for l in lat]
    low=sum(1 for l in lat if l<8)
    # pattern of low/high
    pat=''.join('L' if l<8 else 'H' for l in lat[:60])
    print(f.split('/')[-2][:30], len(rows), 'low',low,'/',len(lat),'p50 %.2f'%st.median(lat),'mean %.2f'%st.mean(lat))
    if low and low<len(lat): print('  low-mode lat p50 %.2f max %.2f; high-mode p50 %.2f'%(st.median([l for l in lat if l<8]),max(l for l in lat if l<8),st.median([l for l in lat if l>=8])))
    print('  ',pat)
    ar=[x['host_arrival_ns'] for x in rows]
    iv=Counter(round((b-a)/1e6) for a,b in zip(ar[30:],ar[31:]))
    print('   arrival intervals', dict(sorted(iv.items())))
