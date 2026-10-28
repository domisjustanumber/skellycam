import json,sys,collections,statistics
for p in sys.argv[1:]:
    rows=[json.loads(l) for l in open(p)]
    rows=rows[30:]
    def ts(r):
        if r.get('implied_sample_time_ns'): return r['implied_sample_time_ns']
        if 'os_timestamp_source' in r and 'QPC' in (r['os_timestamp_source'] or ''): return r['os_timestamp_ns']
        return r.get('os_timestamp_ns')
    t=[ts(r) for r in rows]; h=[r['host_arrival_ns'] for r in rows]
    iv=[(b-a)/1e6 for a,b in zip(t,t[1:])]
    hv=[(b-a)/1e6 for a,b in zip(h,h[1:])]
    lat=sorted((x-y)/1e6 for x,y in zip(h,t))
    c=collections.Counter(round(x) for x in iv)
    hc=collections.Counter(round(x) for x in hv)
    # residue of ts mod 15.625? check the grid: ts differences mod 16ms
    print(p, 'n_iv',len(iv),'os_iv_hist',sorted(c.items()),'\n   host_iv_hist(top)',hc.most_common(6),'\n   lat p0 p50 p99', round(lat[0],2), round(lat[len(lat)//2],2), round(lat[int(.99*(len(lat)-1))],2), 'lat hist', sorted(collections.Counter(round(x) for x in lat).items())[:12])
    # fine resolution: are os ts differences multiples of exactly 16.0 ms or 15.625?
    fr=collections.Counter(round(x,1) for x in iv).most_common(5); print('   fine',fr)
