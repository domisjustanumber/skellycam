import json,glob,collections,os
base='research/skellycam_recording/recording_upgrade/results/intra_playback/functional/'
for b in ('e35','e45','c156'):
  n=0;hist=collections.Counter();notone=0;skipped=0
  for f in glob.glob(base+b+'/seek_*.json'):
    d=json.load(open(f))
    for e in d['result']:
      c=e['config']
      if not str(c.get('path','')).startswith('webcodecs'): continue
      s=(e.get('result') or {}).get('summary') or {}
      dh=s.get('decoded_hist')
      if dh is None: skipped+=1; continue
      n+=1
      if set(dh.keys())!={'1'}: notone+=1; print(b,c,dh)
  print(b,'wc configs with hist',n,'not-one',notone,'no-hist',skipped)
