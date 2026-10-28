import json, sys, glob, os, statistics as st, collections
run = sys.argv[1]
s = json.load(open(os.path.join(run, 'summary.json')))
for c in s['cameras']:
    f = os.path.join(run, c.get('frames_file') or 'none')
    rows = [json.loads(l) for l in open(f)] if os.path.exists(f) else []
    print('==', c.get('human_name'), c.get('actual_format'), 'frames', c.get('frames'), 'soi', c.get('frames_with_soi'), 'eoi', c.get('frames_with_eoi'),
          'dec', c.get('decode_ok'), '/', c.get('decode_attempted'), 'err', c.get('read_errors'), (c.get('errors_sample') or [''])[:1], c.get('open_error', ''))
    if len(rows) < 40:
        continue
    r = rows[30:]
    dur = (r[-1]['host_arrival_ns'] - r[0]['host_arrival_ns']) / 1e9
    lat = [(x['host_arrival_ns'] - x['implied_sample_time_ns']) / 1e6 for x in r if x.get('implied_sample_time_ns')]
    iv = [(b['implied_sample_time_ns'] - a['implied_sample_time_ns']) / 1e6 for a, b in zip(r, r[1:])]
    hv = [(b['host_arrival_ns'] - a['host_arrival_ns']) / 1e6 for a, b in zip(r, r[1:])]
    seqgap = sum(1 for a, b in zip(r, r[1:]) if b['seq'] != a['seq'] + 1)
    print('   fps_host %.3f valid %d/%d median_bytes %d seqgaps %d' % ((len(r) - 1) / dur, sum(x['is_valid_jpeg'] for x in r), len(r), st.median(x['payload_bytes'] for x in r), seqgap))
    print('   lat host-sample ms: median %.2f p05 %.2f p95 %.2f hist %s' % (st.median(lat), sorted(lat)[len(lat)//20], sorted(lat)[len(lat)*19//20], sorted(collections.Counter(round(v) for v in lat).items())))
    print('   sample-time interval ms hist', sorted(collections.Counter(round(v) for v in iv).items()), 'mean %.3f' % st.mean(iv))
    print('   host interval ms hist', sorted(collections.Counter(round(v / 4) * 4 for v in hv).items())[:10])
    print('   sample_time mod 1ms frac (ns): ', collections.Counter((x['implied_sample_time_ns'] % 1000000) // 100000 for x in r).most_common(5))
